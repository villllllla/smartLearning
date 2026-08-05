"""Three-way line-based merge with conflict hunks (PRD §6.1.2).

Why hand-rolled instead of git: the corpus is per-document, single user, no
binary blobs — a small, deterministic, dependency-free merge keeps the bar
low for testing and lets us return structured conflict regions to the UI
(rather than `<<<<<<<` markers the user has to parse by hand).

Algorithm:
  1. Compute a Longest Common Subsequence on (base, ours) and (base, theirs)
     using ``difflib.SequenceMatcher``.
  2. Walk both opcode streams jointly along the *base* axis to extract
     "hunks": ranges in base where at least one side changed.
  3. A hunk is **conflict-free** when:
        - only one side changed (the other matches base), OR
        - both sides made the *exact same* change (``ours == theirs``).
     Otherwise it is a **conflict** and both candidate texts are surfaced
     for the user to choose from in the 3-pane UI.
  4. Auto-merge concatenates: shared base prefix → resolved hunk → shared
     base middle → … → shared base suffix.

Returned ``MergePlan`` is JSON-serializable so the API can hand it directly
to the frontend.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Literal

HunkKind = Literal["clean", "conflict"]


@dataclass
class Hunk:
    """One contiguous range in the *base* document where ours/theirs may differ.

    For ``kind = "clean"`` the merged text is in ``resolved`` and the UI does
    not need user input. For ``kind = "conflict"`` ``resolved`` is None and
    the UI presents ``ours_text`` / ``theirs_text`` / ``base_text`` (any may
    be empty if a side deleted that block).

    Indices are line-based, half-open ``[start, end)`` over the base lines.
    """

    kind: HunkKind
    base_start: int
    base_end: int
    base_text: str
    ours_text: str
    theirs_text: str
    resolved: str | None  # populated for clean hunks
    # Stable id within a plan; lets UI track which choice maps to which hunk.
    id: int = 0


@dataclass
class MergePlan:
    base: str
    ours: str
    theirs: str
    hunks: list[Hunk] = field(default_factory=list)
    auto_merged: str | None = None  # populated when no conflicts remain

    @property
    def has_conflict(self) -> bool:
        return any(h.kind == "conflict" for h in self.hunks)

    @property
    def conflict_count(self) -> int:
        return sum(1 for h in self.hunks if h.kind == "conflict")


def _split_lines(text: str) -> list[str]:
    """Keep trailing newline on each line so reassembly is loss-less."""
    if not text:
        return []
    return text.splitlines(keepends=True)


def _opcodes(a: list[str], b: list[str]) -> list[tuple[str, int, int, int, int]]:
    return SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes()


def _index_map(opcodes: list[tuple[str, int, int, int, int]]) -> dict[int, tuple[int, int]]:
    """For each base line index, return (b_start, b_end) range it maps into.

    ``equal`` and ``replace``/``delete`` are all handled. For pure insertions
    after base index N (``insert`` block with i1 == i2 == N), they are
    associated with the *boundary* by being attached to the next non-equal
    walk step.
    """
    out: dict[int, tuple[int, int]] = {}
    for tag, i1, i2, j1, j2 in opcodes:
        if tag == "equal":
            for k in range(i2 - i1):
                out[i1 + k] = (j1 + k, j1 + k + 1)
        elif tag == "delete":
            for k in range(i1, i2):
                out[k] = (j1, j1)
        elif tag == "replace":
            # Map proportionally; for our hunk grouping below we only consult
            # boundary positions, so a coarse mapping is OK.
            for k in range(i1, i2):
                out[k] = (j1, j2)
    return out


def _changed_base_indices(
    opcodes: list[tuple[str, int, int, int, int]], base_len: int
) -> set[int]:
    """Set of base line indices touched by a non-equal opcode.

    Insertions (i1 == i2) are attributed to *both* boundary indices so the
    surrounding hunk swallows them.
    """
    changed: set[int] = set()
    for tag, i1, i2, _j1, _j2 in opcodes:
        if tag == "equal":
            continue
        if i1 == i2:
            # pure insertion at boundary
            if i1 - 1 >= 0:
                changed.add(i1 - 1)
            if i1 < base_len:
                changed.add(i1)
        else:
            for k in range(i1, i2):
                changed.add(k)
    return changed


def _slice_text(lines: list[str], start: int, end: int) -> str:
    return "".join(lines[start:end])


def _opcodes_overlapping(
    opcodes: list[tuple[str, int, int, int, int]], lo: int, hi: int
) -> tuple[int, int]:
    """Return the side-axis range covering all base indices in [lo, hi).

    Handles boundary insertions whose i1 == i2 == lo or == hi.
    """
    j_lo: int | None = None
    j_hi: int | None = None
    for tag, i1, i2, j1, j2 in opcodes:
        # Touches the base range if its base interval intersects [lo, hi),
        # or it's a pure insertion exactly at lo (anchor before) or hi (anchor after).
        intersects = not (i2 <= lo or i1 >= hi)
        if i1 == i2 and (i1 == lo or i1 == hi):
            intersects = True
        if not intersects:
            continue
        if tag == "equal":
            # We only want the *changed* portion clipped to [lo, hi).
            # equal opcodes do *not* contribute to our hunk text — the hunk
            # text is what the side replaces the base sub-range with.
            # However, when a side has only equal opcodes spanning [lo, hi),
            # its text equals base. We capture that by reading the equal
            # opcode's j1 + (lo - i1) … j1 + (hi - i1).
            local_j_lo = j1 + max(0, lo - i1)
            local_j_hi = j1 + min(i2, hi) - i1
            if local_j_hi < local_j_lo:
                local_j_hi = local_j_lo
            j_lo = local_j_lo if j_lo is None else min(j_lo, local_j_lo)
            j_hi = local_j_hi if j_hi is None else max(j_hi, local_j_hi)
        else:
            j_lo = j1 if j_lo is None else min(j_lo, j1)
            j_hi = j2 if j_hi is None else max(j_hi, j2)
    if j_lo is None or j_hi is None:
        return 0, 0
    return j_lo, j_hi


def merge_three_way(base: str, ours: str, theirs: str) -> MergePlan:
    """Compute a 3-way merge plan.

    Identity short-circuits:
      - ours == base  → fast-forward to theirs
      - theirs == base → fast-forward to ours
      - ours == theirs → identical change, return that
    """
    plan = MergePlan(base=base, ours=ours, theirs=theirs)

    if ours == base:
        plan.auto_merged = theirs
        return plan
    if theirs == base:
        plan.auto_merged = ours
        return plan
    if ours == theirs:
        plan.auto_merged = ours
        return plan

    base_lines = _split_lines(base)
    ours_lines = _split_lines(ours)
    theirs_lines = _split_lines(theirs)

    op_o = _opcodes(base_lines, ours_lines)
    op_t = _opcodes(base_lines, theirs_lines)

    changed_o = _changed_base_indices(op_o, len(base_lines))
    changed_t = _changed_base_indices(op_t, len(base_lines))

    # Group adjacent changed base indices into hunks.
    union = sorted(changed_o | changed_t)

    hunk_ranges: list[tuple[int, int]] = []
    if union:
        run_start = union[0]
        prev = union[0]
        for k in union[1:]:
            if k == prev + 1:
                prev = k
                continue
            hunk_ranges.append((run_start, prev + 1))
            run_start = k
            prev = k
        hunk_ranges.append((run_start, prev + 1))

    # Walk hunks and emit stitched output.
    out: list[str] = []
    cursor = 0
    next_id = 1
    hunks_out: list[Hunk] = []

    for lo, hi in hunk_ranges:
        # Append unchanged base prefix [cursor, lo)
        out.append(_slice_text(base_lines, cursor, lo))

        base_text = _slice_text(base_lines, lo, hi)
        o_lo, o_hi = _opcodes_overlapping(op_o, lo, hi)
        t_lo, t_hi = _opcodes_overlapping(op_t, lo, hi)
        ours_text = _slice_text(ours_lines, o_lo, o_hi)
        theirs_text = _slice_text(theirs_lines, t_lo, t_hi)

        only_ours_changed = (lo not in changed_t and not _range_changed(changed_t, lo, hi))
        only_theirs_changed = (lo not in changed_o and not _range_changed(changed_o, lo, hi))
        same_change = ours_text == theirs_text

        if same_change:
            kind: HunkKind = "clean"
            resolved = ours_text
        elif only_ours_changed:
            kind = "clean"
            resolved = ours_text
        elif only_theirs_changed:
            kind = "clean"
            resolved = theirs_text
        else:
            kind = "conflict"
            resolved = None

        h = Hunk(
            kind=kind,
            base_start=lo,
            base_end=hi,
            base_text=base_text,
            ours_text=ours_text,
            theirs_text=theirs_text,
            resolved=resolved,
            id=next_id,
        )
        next_id += 1
        hunks_out.append(h)

        if resolved is not None:
            out.append(resolved)
        cursor = hi

    # Trailing unchanged tail
    out.append(_slice_text(base_lines, cursor, len(base_lines)))

    plan.hunks = hunks_out
    if not plan.has_conflict:
        plan.auto_merged = "".join(out)
    return plan


def _range_changed(changed: set[int], lo: int, hi: int) -> bool:
    """Did any base index in [lo, hi) appear in ``changed``?"""
    return any(k in changed for k in range(lo, hi))


def apply_resolutions(
    plan: MergePlan, resolutions: dict[int, str]
) -> str:
    """Reassemble the merged text given a {hunk_id: text} resolution map.

    Any clean hunk uses ``plan.hunks[i].resolved`` automatically; conflict
    hunks must be present in ``resolutions``. Raises ``ValueError`` if a
    conflict is left unresolved.
    """
    base_lines = _split_lines(plan.base)
    out: list[str] = []
    cursor = 0
    for h in plan.hunks:
        out.append(_slice_text(base_lines, cursor, h.base_start))
        if h.kind == "clean":
            out.append(h.resolved or "")
        else:
            if h.id not in resolutions:
                raise ValueError(f"unresolved conflict hunk #{h.id}")
            out.append(resolutions[h.id])
        cursor = h.base_end
    out.append(_slice_text(base_lines, cursor, len(base_lines)))
    return "".join(out)

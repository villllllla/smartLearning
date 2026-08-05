"""Run the Feishu agent tool-routing evaluation.

Usage (from the ``backend`` directory)::

    python -m eval.run_eval

By default it runs against an in-memory SQLite database, which exercises the
deterministic *rule* fast path only (no model / API key needed). To also score
the LLM intent-routing cases, point it at a database that has a provider + model
configured for the ``chat_general`` scene::

    SL_EVAL_DATABASE_URL=sqlite:///./data/app.sqlite3 python -m eval.run_eval

The harness monkeypatches ``execute_tool`` with a recorder, so it drives the
*real* routing pipeline (``handle_incoming_text``) and never actually runs a
tool or mutates the bank — it only observes which tool the agent selected.
"""
from __future__ import annotations

import argparse
import asyncio
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.db.base import Base
from app.integrations.feishu import agent as agent_module
from app.integrations.feishu.commands import CommandResult
from app.services.feishu_trigger_service import seed_default_rules
from app.services.llm.client import LLMError, resolve_for_scene
from eval.routing_cases import ALL_CASES, Case


class _Recorder:
    """Async stand-in for ``execute_tool`` that captures the selected tool."""

    def __init__(self) -> None:
        self.tool: str | None = None
        self.args: dict | None = None

    def reset(self) -> None:
        self.tool = None
        self.args = None

    async def __call__(self, db, session, tool, args, *, user_text=None):  # noqa: ANN001
        self.tool = tool
        self.args = args
        return CommandResult(texts=["[recorded]"])


def _make_session_factory():
    url = os.environ.get("SL_EVAL_DATABASE_URL")
    if url:
        engine = create_engine(url)
        return sessionmaker(bind=engine)(), True
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    seed_default_rules(db, tenant_id=1)
    db.commit()
    return db, False


def _llm_available(db) -> bool:
    try:
        resolve_for_scene(db, "chat_general", tenant_id=1)
        return True
    except LLMError:
        return False


async def _route(db, settings, recorder: _Recorder, case: Case, idx: int) -> str | None:
    """Drive the real pipeline for one case; return the selected tool (or None)."""
    recorder.reset()
    # Distinct open_id per case → clean session state (queues, cursors, etc.).
    await agent_module.handle_incoming_text(
        db,
        settings,
        open_id=f"ou_eval_{idx}",
        chat_id=f"oc_eval_{idx}",
        text=case.text,
    )
    return recorder.tool


def _fmt_pct(hits: int, total: int) -> str:
    return f"{hits}/{total} = {100.0 * hits / total:.1f}%" if total else "n/a"


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--show-all", action="store_true", help="print every case, not just misses"
    )
    args = parser.parse_args()

    settings = get_settings()
    db, is_real_db = _make_session_factory()
    llm_ok = _llm_available(db)

    recorder = _Recorder()
    original = agent_module.execute_tool
    agent_module.execute_tool = recorder  # type: ignore[assignment]

    rows: list[tuple[Case, str | None, str]] = []
    try:
        for idx, case in enumerate(ALL_CASES):
            needs_llm = case.category in ("llm_intent", "adversarial")
            predicted = await _route(db, settings, recorder, case, idx)
            if predicted is None and needs_llm and not llm_ok:
                verdict = "SKIP"  # LLM branch, no provider configured
            elif predicted == case.expected_tool:
                verdict = "PASS"
            else:
                verdict = "FAIL"
            rows.append((case, predicted, verdict))
    finally:
        agent_module.execute_tool = original  # type: ignore[assignment]

    # --- report -----------------------------------------------------------
    mode = "real-LLM" if llm_ok else "rule-only (no provider configured)"
    print("=" * 70)
    print(f"Feishu agent routing eval — mode: {mode}")
    if is_real_db:
        print(f"database: {os.environ['SL_EVAL_DATABASE_URL']}")
    print("=" * 70)

    by_cat: dict[str, list[str]] = {}
    for case, _pred, verdict in rows:
        by_cat.setdefault(case.category, []).append(verdict)

    print("\nPer-category:")
    for cat in sorted(by_cat):
        verdicts = by_cat[cat]
        passed = verdicts.count("PASS")
        failed = verdicts.count("FAIL")
        skipped = verdicts.count("SKIP")
        scored = passed + failed
        tail = f"  ({skipped} skipped)" if skipped else ""
        print(f"  {cat:16s} {_fmt_pct(passed, scored):>18s}{tail}")

    scored_rows = [r for r in rows if r[2] in ("PASS", "FAIL")]
    overall_pass = sum(1 for r in scored_rows if r[2] == "PASS")
    print("\nOverall (scored cases only):")
    print(f"  accuracy: {_fmt_pct(overall_pass, len(scored_rows))}")
    print(f"  skipped (need LLM provider): {sum(1 for r in rows if r[2] == 'SKIP')}")

    misses = [r for r in rows if r[2] == "FAIL"]
    if misses:
        print(f"\nMisses ({len(misses)}):")
        for case, pred, _v in misses:
            print(f"  [{case.category}] {case.text!r}")
            print(f"      expected={case.expected_tool}  got={pred}")
            if case.note:
                print(f"      note: {case.note}")

    if args.show_all:
        print("\nAll cases:")
        for case, pred, verdict in rows:
            print(f"  {verdict:4s} {case.expected_tool:20s} <- {case.text!r} (got {pred})")

    db.close()
    # Non-zero exit if any scored case failed (useful in CI).
    return 1 if misses else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

import type { Difficulty, Grade } from "@/api/bank";

/** Map a grade letter to a Badge variant. */
export function gradeBadgeVariant(g: Grade | null | undefined) {
  switch (g) {
    case "S":
      return "success" as const;
    case "A":
      return "default" as const;
    case "B":
      return "secondary" as const;
    case "C":
      return "destructive" as const;
    default:
      return "outline" as const;
  }
}

export function difficultyVariant(d: Difficulty | string) {
  if (d === "easy") return "success" as const;
  if (d === "hard") return "destructive" as const;
  return "default" as const;
}

/** Short Chinese label for a grade letter, with a fallback. */
export function gradeLabel(g: Grade | null | undefined): string {
  if (!g) return "未作答";
  if (g === "C") return "C · 错题";
  return g;
}

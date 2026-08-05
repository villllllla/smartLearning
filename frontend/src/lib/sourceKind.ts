export type QuestionSourceKind = "simulated" | "interview";

export const SOURCE_KIND_OPTIONS: {
  value: QuestionSourceKind;
  label: string;
  hint: string;
}[] = [
  {
    value: "interview",
    label: "实战面经",
    hint: "从真实面经文档导入的原题",
  },
  {
    value: "simulated",
    label: "模拟题库",
    hint: "从 Wiki 文档由模型生成的题目",
  },
];

export function sourceKindLabel(kind: QuestionSourceKind | string): string {
  return SOURCE_KIND_OPTIONS.find((o) => o.value === kind)?.label ?? kind;
}

export function sourceKindVariant(
  kind: QuestionSourceKind | string,
): "default" | "secondary" | "outline" {
  return kind === "interview" ? "default" : "secondary";
}

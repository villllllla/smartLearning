import { useEffect, useMemo, useState, type Dispatch, type SetStateAction } from "react";
import { useMutation } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { ArrowRight, ChevronLeft, Clock, RefreshCw, Send } from "lucide-react";

import { type QuestionSummary } from "@/api/bank";
import { type PracticeAnswerResponse, practiceApi } from "@/api/practice";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Empty } from "@/components/Empty";
import { PageHeader } from "@/components/layout/PageHeader";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "@/components/ui/toast";
import { cn } from "@/lib/utils";
import { difficultyVariant, gradeBadgeVariant, gradeLabel } from "@/lib/grade";
import { getPracticeSession, recordAnswer, setPracticeSession } from "./session";

export function PracticeRunPage() {
  const navigate = useNavigate();
  const session = getPracticeSession();
  const [idx, setIdx] = useState(0);
  const [answer, setAnswer] = useState("");
  const [result, setResult] = useState<PracticeAnswerResponse | null>(null);
  const [showAnswer, setShowAnswer] = useState(false);

  if (!session || session.questions.length === 0) {
    return (
      <>
        <PageHeader title="练习" />
        <div className="mx-auto max-w-2xl p-8">
          <Empty
            title="没有进行中的练习"
            description="请先到练习设置页配置题集并出题。"
            action={
              <Button asChild>
                <Link to="/practice">回到练习设置</Link>
              </Button>
            }
          />
        </div>
      </>
    );
  }

  const total = session.questions.length;
  const finished = idx >= total;
  const current = finished ? null : session.questions[idx];

  return finished ? (
    <SummaryView session={session} onRestart={() => navigate("/practice")} />
  ) : (
    <ActiveQuestion
      key={current!.id}
      idx={idx}
      total={total}
      question={current!}
      timeLimit={session.timeLimit}
      answer={answer}
      setAnswer={setAnswer}
      result={result}
      setResult={setResult}
      showAnswer={showAnswer}
      setShowAnswer={setShowAnswer}
      onNext={() => {
        setIdx((i) => i + 1);
        setAnswer("");
        setResult(null);
        setShowAnswer(false);
      }}
      onAbort={() => {
        if (confirm("结束本次练习?进度会被丢弃。")) {
          setPracticeSession(null);
          navigate("/practice");
        }
      }}
    />
  );
}

// ---------------------------------------------------------------------------
// ActiveQuestion
// ---------------------------------------------------------------------------

interface ActiveProps {
  idx: number;
  total: number;
  question: QuestionSummary;
  timeLimit: number | null;
  answer: string;
  setAnswer: Dispatch<SetStateAction<string>>;
  result: PracticeAnswerResponse | null;
  setResult: Dispatch<SetStateAction<PracticeAnswerResponse | null>>;
  showAnswer: boolean;
  setShowAnswer: Dispatch<SetStateAction<boolean>>;
  onNext: () => void;
  onAbort: () => void;
}

function ActiveQuestion({
  idx,
  total,
  question,
  timeLimit,
  answer,
  setAnswer,
  result,
  setResult,
  showAnswer,
  setShowAnswer,
  onNext,
  onAbort,
}: ActiveProps) {
  const [secondsLeft, setSecondsLeft] = useState<number | null>(timeLimit);

  useEffect(() => {
    setSecondsLeft(timeLimit);
  }, [question.id, timeLimit]);

  useEffect(() => {
    if (secondsLeft === null || result) return;
    if (secondsLeft <= 0) return;
    const t = setTimeout(() => setSecondsLeft((s) => (s === null ? null : s - 1)), 1000);
    return () => clearTimeout(t);
  }, [secondsLeft, result]);

  const submit = useMutation({
    mutationFn: () =>
      practiceApi.answer({
        question_id: question.id,
        user_answer_text: answer.trim(),
      }),
    onSuccess: (res) => {
      setResult(res);
      recordAnswer(question.id, answer.trim(), res);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const canSubmit = answer.trim().length > 0 && !submit.isPending && !result;
  const timeUp = secondsLeft === 0 && !result;

  return (
    <>
      <PageHeader
        title={`第 ${idx + 1} / ${total} 题`}
        description={
          <span className="flex items-center gap-3">
            <Badge variant={difficultyVariant(question.difficulty)}>
              {question.difficulty}
            </Badge>
            <Badge variant="outline">{question.qtype}</Badge>
            {question.tags.map((t) => (
              <Badge key={t.id} variant="secondary">
                {t.name}
              </Badge>
            ))}
          </span>
        }
        actions={
          <Button variant="outline" onClick={onAbort}>
            <ChevronLeft className="h-4 w-4" />
            结束练习
          </Button>
        }
      />

      <div className="mx-auto max-w-3xl space-y-4 p-4 md:p-8">
        <Card>
          <CardContent className="space-y-4 p-5">
            <div className="text-base leading-relaxed">{question.question_text}</div>
            {question.source_wiki_id && (
              <div className="text-xs text-muted-foreground">
                来源:
                <Link
                  to={`/wiki/${question.source_wiki_id}`}
                  className="ml-1 text-primary underline-offset-2 hover:underline"
                  target="_blank"
                  rel="noreferrer"
                >
                  {question.source_wiki_title || `wiki #${question.source_wiki_id}`}
                </Link>
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardContent className="space-y-3 p-5">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-muted-foreground">
                你的作答
              </span>
              {timeLimit !== null && secondsLeft !== null && (
                <span
                  className={cn(
                    "flex items-center gap-1 text-xs font-medium",
                    secondsLeft <= 5 ? "text-destructive" : "text-muted-foreground",
                  )}
                >
                  <Clock className="h-3.5 w-3.5" />
                  {secondsLeft}s
                </span>
              )}
            </div>
            <Textarea
              value={answer}
              onChange={(e) => setAnswer(e.target.value)}
              rows={8}
              placeholder="结论先行 → 关键要点(要点式) → 可被追问的方向"
              disabled={!!result}
            />
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-xs text-muted-foreground">
                {timeUp ? "时间到,但仍可提交。" : ""}
              </span>
              <div className="flex gap-2">
                {!result && (
                  <Button
                    onClick={() => submit.mutate()}
                    disabled={!canSubmit}
                  >
                    <Send className="h-4 w-4" />
                    {submit.isPending ? "评分中..." : "提交作答"}
                  </Button>
                )}
                {result && (
                  <>
                    <Button variant="outline" onClick={() => setShowAnswer((s) => !s)}>
                      {showAnswer ? "隐藏标准答案" : "对照标准答案"}
                    </Button>
                    <Button onClick={onNext}>
                      {idx === total - 1 ? "完成" : "下一题"}
                      <ArrowRight className="h-4 w-4" />
                    </Button>
                  </>
                )}
              </div>
            </div>
          </CardContent>
        </Card>

        {result && (
          <ResultCard
            result={result}
            standardAnswer={question.answer_standard}
            showAnswer={showAnswer}
          />
        )}
      </div>
    </>
  );
}

// ---------------------------------------------------------------------------
// Result card
// ---------------------------------------------------------------------------

function ResultCard({
  result,
  standardAnswer,
  showAnswer,
}: {
  result: PracticeAnswerResponse;
  standardAnswer: string;
  showAnswer: boolean;
}) {
  const dimensions: Array<{ key: keyof PracticeAnswerResponse; label: string }> = [
    { key: "score_correctness", label: "正确性 (硬门槛)" },
    { key: "score_completeness", label: "完整性" },
    { key: "score_structure", label: "结构性" },
    { key: "score_depth", label: "深度" },
  ];
  const summary = result.feedback_text.split("\n")[0] || "";
  const bullets = result.feedback_text
    .split("\n")
    .slice(1)
    .map((s) => s.replace(/^- /, "").trim())
    .filter(Boolean);

  return (
    <Card>
      <CardContent className="space-y-4 p-5">
        <div className="flex flex-wrap items-center gap-3">
          <Badge variant={gradeBadgeVariant(result.grade)} className="text-base">
            {gradeLabel(result.grade)}
          </Badge>
          <span className="text-sm text-muted-foreground">{summary}</span>
        </div>

        <div className="space-y-2">
          {dimensions.map((d) => (
            <ScoreBar
              key={d.key}
              label={d.label}
              value={result[d.key] as number}
            />
          ))}
        </div>

        {bullets.length > 0 && (
          <div>
            <div className="mb-1 text-xs font-medium text-muted-foreground">
              改进建议
            </div>
            <ul className="list-disc space-y-1 pl-5 text-sm leading-relaxed">
              {bullets.map((b, i) => (
                <li key={i}>{b}</li>
              ))}
            </ul>
          </div>
        )}

        {showAnswer && (
          <div>
            <div className="mb-1 text-xs font-medium text-muted-foreground">
              标准答案
            </div>
            <div className="whitespace-pre-wrap rounded-md border bg-muted/30 p-3 text-sm leading-relaxed">
              {standardAnswer || "(无)"}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function ScoreBar({ label, value }: { label: string; value: number }) {
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>{label}</span>
        <span className="font-mono">{value}/100</span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
        <div
          className={cn(
            "h-full transition-all",
            value >= 80 ? "bg-emerald-500" : value >= 60 ? "bg-amber-500" : "bg-rose-500",
          )}
          style={{ width: `${Math.max(0, Math.min(100, value))}%` }}
        />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Summary view
// ---------------------------------------------------------------------------

function SummaryView({
  session,
  onRestart,
}: {
  session: ReturnType<typeof getPracticeSession> & object;
  onRestart: () => void;
}) {
  const answered = useMemo(
    () =>
      session!.questions.map((q) => ({
        q,
        answer: session!.answers[q.id],
      })),
    [session],
  );
  const counts = answered.reduce(
    (acc, { answer }) => {
      if (!answer) return acc;
      acc[answer.result.grade] = (acc[answer.result.grade] ?? 0) + 1;
      return acc;
    },
    {} as Record<string, number>,
  );

  return (
    <>
      <PageHeader
        title="练习总结"
        description={`共 ${answered.length} 题,完成 ${Object.values(counts).reduce((a, b) => a + b, 0)} 题`}
        actions={
          <>
            <Button variant="outline" asChild>
              <Link to="/bank">回题库</Link>
            </Button>
            <Button onClick={onRestart}>
              <RefreshCw className="h-4 w-4" />
              再来一组
            </Button>
          </>
        }
      />
      <div className="mx-auto max-w-3xl space-y-4 p-4 md:p-8">
        <Card>
          <CardContent className="flex flex-wrap items-center gap-4 p-5">
            {(["S", "A", "B", "C"] as const).map((g) => (
              <div key={g} className="flex items-center gap-2">
                <Badge variant={gradeBadgeVariant(g)} className="text-base">
                  {gradeLabel(g)}
                </Badge>
                <span className="text-sm tabular-nums">×{counts[g] ?? 0}</span>
              </div>
            ))}
          </CardContent>
        </Card>

        <div className="grid gap-3">
          {answered.map(({ q, answer }) => (
            <Card key={q.id}>
              <CardContent className="space-y-2 p-4">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant={difficultyVariant(q.difficulty)}>{q.difficulty}</Badge>
                  {answer ? (
                    <Badge variant={gradeBadgeVariant(answer.result.grade)}>
                      {gradeLabel(answer.result.grade)}
                    </Badge>
                  ) : (
                    <Badge variant="outline">未作答</Badge>
                  )}
                </div>
                <div className="text-sm">{q.question_text}</div>
                {answer && (
                  <div className="grid grid-cols-4 gap-1 text-[10px] uppercase text-muted-foreground">
                    <span>正确 {answer.result.score_correctness}</span>
                    <span>完整 {answer.result.score_completeness}</span>
                    <span>结构 {answer.result.score_structure}</span>
                    <span>深度 {answer.result.score_depth}</span>
                  </div>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </>
  );
}

import { PageHeader } from "@/components/layout/PageHeader";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Construction } from "lucide-react";

interface Props {
  title: string;
  description: string;
  upcoming: string[];
}

export function PlaceholderPage({ title, description, upcoming }: Props) {
  return (
    <>
      <PageHeader title={title} description={description} />
      <div className="mx-auto max-w-3xl space-y-4 p-4 md:p-8">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Construction className="h-4 w-4 text-amber-500" />
              本模块下个迭代上线
            </CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            <p className="mb-3">
              一期 MVP 的本模块已经定好数据结构与接口形态,UI 将在后续迭代逐项推出。
              目前可在 <code className="rounded bg-muted px-1.5 py-0.5">/docs</code> 查看后端 API。
            </p>
            <ul className="list-disc space-y-1 pl-5">
              {upcoming.map((u) => (
                <li key={u}>{u}</li>
              ))}
            </ul>
          </CardContent>
        </Card>
      </div>
    </>
  );
}

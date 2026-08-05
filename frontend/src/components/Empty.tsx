import type { ReactNode } from "react";
import { Inbox } from "lucide-react";

interface Props {
  title: string;
  description?: string;
  action?: ReactNode;
}

export function Empty({ title, description, action }: Props) {
  return (
    <div className="mx-auto flex max-w-md flex-col items-center gap-3 rounded-xl border border-dashed bg-card/40 p-10 text-center">
      <Inbox className="h-10 w-10 text-muted-foreground" />
      <div className="text-base font-medium">{title}</div>
      {description && (
        <div className="text-sm text-muted-foreground">{description}</div>
      )}
      {action}
    </div>
  );
}

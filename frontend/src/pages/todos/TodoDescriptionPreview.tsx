const PREVIEW_MAX_LINES = 2;
const PREVIEW_MAX_CHARS = 96;

export function previewDescription(text: string): { preview: string; truncated: boolean } {
  const lines = text.split("\n");
  const lineLimited = lines.length > PREVIEW_MAX_LINES;
  const head = lines.slice(0, PREVIEW_MAX_LINES).join("\n");
  const charLimited = head.length > PREVIEW_MAX_CHARS;
  const preview = charLimited ? head.slice(0, PREVIEW_MAX_CHARS).trimEnd() : head.trimEnd();
  const truncated = lineLimited || charLimited || text.length > preview.length;
  return { preview: truncated ? `${preview}…` : preview, truncated };
}

export function TodoDescriptionPreview({
  text,
  editable,
  busy,
  onEdit,
}: {
  text: string;
  editable: boolean;
  busy: boolean;
  onEdit: () => void;
}) {
  const { preview, truncated } = previewDescription(text);
  const className =
    "block w-full break-words text-sm leading-5 text-muted-foreground max-h-[2.5rem] overflow-hidden";

  if (editable) {
    return (
      <button
        type="button"
        onClick={onEdit}
        disabled={busy}
        className={`${className} cursor-pointer border-0 bg-transparent p-0 text-left hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 rounded-sm`}
        title={truncated ? "点击查看/编辑完整说明" : "点击查看/编辑说明"}
      >
        {preview}
      </button>
    );
  }

  return <p className={className}>{preview}</p>;
}

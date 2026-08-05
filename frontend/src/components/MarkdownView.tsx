import type { ReactNode } from "react";
import type { Components } from "react-markdown";
import ReactMarkdown from "react-markdown";
import rehypeHighlight from "rehype-highlight";
import rehypeRaw from "rehype-raw";
import remarkGfm from "remark-gfm";

interface Props {
  source: string;
  /**
   * When set (e.g. `/api/wiki/12/assets`), relative image paths in Markdown/HTML
   * resolve under this prefix so bare .md + `_assets/` files can load.
   */
  wikiAssetBase?: string;
}

export function MarkdownView({ source, wikiAssetBase }: Props) {
  const components = markdownComponents(wikiAssetBase);

  return (
    <article className="md-body">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[
          rehypeRaw,
          [rehypeHighlight, { ignoreMissing: true }] as const,
        ]}
        components={components}
      >
        {source}
      </ReactMarkdown>
    </article>
  );
}

function markdownComponents(wikiAssetBase?: string): Components {
  return {
    h1: ({ node: _node, ...p }) => <h1 id={anchorOf(p.children)} {...p} />,
    h2: ({ node: _node, ...p }) => <h2 id={anchorOf(p.children)} {...p} />,
    h3: ({ node: _node, ...p }) => <h3 id={anchorOf(p.children)} {...p} />,
    h4: ({ node: _node, ...p }) => <h4 id={anchorOf(p.children)} {...p} />,
    img: ({ node: _node, src, ...rest }) => (
      <img
        src={resolveImgSrc(typeof src === "string" ? src : undefined, wikiAssetBase)}
        {...rest}
      />
    ),
  };
}

/** Prefix relative wiki image paths; keep absolute `/api/...`, `http`, `data`. */
export function resolveImgSrc(src: string | undefined, wikiAssetBase?: string): string {
  if (!src?.trim()) return "";
  const s = src.trim();
  if (/^(https?:)?\/\//i.test(s) || s.startsWith("data:")) return s;
  if (s.startsWith("/api/")) return s;
  if (s.startsWith("/") && !wikiAssetBase) return s;
  if (s.startsWith("/")) return s;

  if (!wikiAssetBase) return s;

  const rel = s.replace(/^\.\//, "").replace(/\\/g, "/");
  if (!rel || rel.split("/").some((seg) => seg === "..")) return s;

  const encoded = rel
    .split("/")
    .filter(Boolean)
    .map((seg) => encodeURIComponent(seg))
    .join("/");
  const base = wikiAssetBase.replace(/\/$/, "");
  return `${base}/${encoded}`;
}

function anchorOf(children: ReactNode): string {
  const text = childrenToText(children).trim().toLowerCase();
  return text
    .replace(/\s+/g, "-")
    .replace(/[^\w\u4e00-\u9fff-]/g, "");
}

function childrenToText(children: ReactNode): string {
  if (typeof children === "string" || typeof children === "number")
    return String(children);
  if (Array.isArray(children)) return children.map(childrenToText).join("");
  if (children && typeof children === "object" && "props" in children) {
    const c = children as { props?: { children?: ReactNode } };
    return childrenToText(c.props?.children);
  }
  return "";
}

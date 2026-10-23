"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { API_URL } from "@/lib/api";

/** Преобразует относительные /uploads/... в полный URL бэкенда. */
function resolveSrc(src: string | Blob | undefined): string {
  if (typeof src !== "string" || !src) return "";
  if (src.startsWith("/uploads")) return `${API_URL}${src}`;
  return src;
}

/** Стилизованный рендер markdown (заголовки, списки, таблицы, картинки). */
export default function MarkdownBody({ content }: { content: string }) {
  return (
    <div className="kb-markdown text-sm leading-relaxed">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: ({ children }) => <h1 className="mb-2 mt-4 text-xl font-bold first:mt-0">{children}</h1>,
          h2: ({ children }) => <h2 className="mb-2 mt-4 text-lg font-bold first:mt-0">{children}</h2>,
          h3: ({ children }) => <h3 className="mb-1.5 mt-3 font-semibold first:mt-0">{children}</h3>,
          h4: ({ children }) => <h4 className="mb-1 mt-3 font-semibold first:mt-0">{children}</h4>,
          p: ({ children }) => <p className="my-2">{children}</p>,
          ul: ({ children }) => <ul className="my-2 list-disc space-y-1 pl-6">{children}</ul>,
          ol: ({ children }) => <ol className="my-2 list-decimal space-y-1 pl-6">{children}</ol>,
          li: ({ children }) => <li>{children}</li>,
          a: ({ href, children }) => (
            <a
              href={href}
              target="_blank"
              rel="noreferrer"
              className="text-primary underline underline-offset-2"
            >
              {children}
            </a>
          ),
          img: ({ src, alt }) => (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={resolveSrc(src)}
              alt={alt || ""}
              className="my-3 max-w-full rounded-md border"
              loading="lazy"
            />
          ),
          code: ({ className, children }) =>
            className ? (
              <code className={className}>{children}</code>
            ) : (
              <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-[0.85em]">{children}</code>
            ),
          pre: ({ children }) => (
            <pre className="my-2 overflow-x-auto rounded-md border bg-muted p-3 font-mono text-xs">
              {children}
            </pre>
          ),
          blockquote: ({ children }) => (
            <blockquote className="my-2 border-l-4 border-primary/40 bg-muted/50 py-1 pl-3 italic">
              {children}
            </blockquote>
          ),
          hr: () => <hr className="my-4 border-t" />,
          table: ({ children }) => (
            <div className="my-2 overflow-x-auto">
              <table className="w-full border-collapse text-sm">{children}</table>
            </div>
          ),
          th: ({ children }) => (
            <th className="border bg-muted px-2 py-1 text-left font-semibold">{children}</th>
          ),
          td: ({ children }) => <td className="border px-2 py-1 align-top">{children}</td>,
          strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}

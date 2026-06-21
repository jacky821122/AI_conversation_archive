import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

// AI 回應是 markdown（標題、表格、清單、程式碼）。用暖色 prose 排版渲染。
export default function Markdown({ children }: { children: string }) {
  return (
    <div
      className="prose prose-sm prose-stone max-w-none dark:prose-invert
        prose-headings:font-display prose-headings:text-ink
        prose-p:leading-relaxed prose-p:text-ink/85
        prose-li:text-ink/85 prose-strong:text-ink
        prose-a:text-accent
        prose-code:text-accent prose-code:before:content-[''] prose-code:after:content-['']
        prose-pre:bg-ink prose-pre:text-paper
        prose-table:text-sm prose-th:text-ink
        prose-hr:border-line"
    >
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{children}</ReactMarkdown>
    </div>
  );
}

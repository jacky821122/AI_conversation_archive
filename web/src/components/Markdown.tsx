import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

// AI 回應是 markdown。一般排版交給 prose；程式碼樣式由 index.css 的 .md 規則控制。
// 寬表格包進可橫向捲動的容器，避免在手機上撐破版面、被裁切。
export default function Markdown({ children }: { children: string }) {
  return (
    <div
      className="md prose prose-sm prose-stone max-w-none dark:prose-invert
        prose-headings:font-display prose-headings:text-ink
        prose-p:leading-relaxed prose-p:text-ink/85
        prose-li:text-ink/85 prose-strong:text-ink
        prose-a:text-accent
        prose-table:text-sm prose-th:text-ink
        prose-hr:border-line"
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          table: ({ node, ...props }) => (
            <div className="-mx-1 overflow-x-auto">
              <table {...props} />
            </div>
          ),
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}

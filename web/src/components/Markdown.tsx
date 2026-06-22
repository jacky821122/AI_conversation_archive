import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";

// 各家匯出的數學分隔符不一致：Gemini 用 $…$ / $$…$$（remark-math 原生支援），
// ChatGPT 用 \(…\) / \[…\]（remark-math 不認）。先把後者轉成 $ 形式，
// 並用 split 保護 code（fenced ``` 與 inline `）不被誤轉。
function normalizeMath(src: string): string {
  return src
    .split(/(```[\s\S]*?```|`[^`]*`)/g)
    .map((seg, i) =>
      i % 2 === 1
        ? seg // code 段原樣保留
        : seg
            .replace(/\\\[([\s\S]+?)\\\]/g, (_, m) => `$$${m}$$`)
            .replace(/\\\(([\s\S]+?)\\\)/g, (_, m) => `$${m}$`),
    )
    .join("");
}

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
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[[rehypeKatex, { throwOnError: false, strict: "ignore" }]]}
        components={{
          table: ({ node, ...props }) => (
            <div className="-mx-1 overflow-x-auto">
              <table {...props} />
            </div>
          ),
        }}
      >
        {normalizeMath(children)}
      </ReactMarkdown>
    </div>
  );
}

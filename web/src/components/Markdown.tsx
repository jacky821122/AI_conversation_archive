import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import remarkCjkFriendly from "remark-cjk-friendly";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";

// rehype 外掛：把 hast text 節點中命中 query 的片段包成 <mark class="kw">，讓 markdown
// 內容（助理訊息）也能高亮、並供對話頁的頁內 find 導覽抓取。零新依賴（手寫淺走訪）。
// 跳過 code/pre 與 katex 子樹，避免破壞程式碼與數學排版。
function hasClass(node: any, name: string): boolean {
  const c = node?.properties?.className;
  if (Array.isArray(c)) return c.includes(name);
  return typeof c === "string" && c.split(/\s+/).includes(name);
}

function markText(value: string, needle: string): any[] {
  const lower = value.toLowerCase();
  const out: any[] = [];
  let i = 0;
  while (i < value.length) {
    const hit = lower.indexOf(needle, i);
    if (hit === -1) {
      out.push({ type: "text", value: value.slice(i) });
      break;
    }
    if (hit > i) out.push({ type: "text", value: value.slice(i, hit) });
    out.push({
      type: "element",
      tagName: "mark",
      properties: { className: ["kw"] },
      children: [{ type: "text", value: value.slice(hit, hit + needle.length) }],
    });
    i = hit + needle.length;
  }
  return out;
}

function rehypeMarkKeyword(query: string) {
  const needle = query.trim().toLowerCase();
  return (tree: any) => {
    if (!needle) return;
    const walk = (node: any) => {
      if (!node || !Array.isArray(node.children)) return;
      if (
        node.type === "element" &&
        (node.tagName === "code" || node.tagName === "pre" || hasClass(node, "katex"))
      ) {
        return; // 不進入程式碼／數學子樹
      }
      const next: any[] = [];
      for (const child of node.children) {
        if (child.type === "text" && child.value.toLowerCase().includes(needle)) {
          next.push(...markText(child.value, needle));
        } else {
          walk(child);
          next.push(child);
        }
      }
      node.children = next;
    };
    walk(tree);
  };
}

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
export default function Markdown({
  children,
  highlight,
}: {
  children: string;
  highlight?: string;
}) {
  const rehypePlugins: any[] = [[rehypeKatex, { throwOnError: false, strict: "ignore" }]];
  if (highlight && highlight.trim()) {
    // 包成 unified attacher（呼叫後回傳 transformer），故用 () => transformer。
    rehypePlugins.push(() => rehypeMarkKeyword(highlight));
  }
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
        remarkPlugins={[remarkGfm, remarkMath, remarkCjkFriendly]}
        rehypePlugins={rehypePlugins}
        components={{
          table: ({ node, ...props }) => (
            <div className="-mx-1 overflow-x-auto">
              <table {...props} />
            </div>
          ),
          // 連結預設開新分頁，避免點對話內連結時離開語料庫頁面。
          a: ({ node, ...props }) => (
            <a {...props} target="_blank" rel="noopener noreferrer" />
          ),
        }}
      >
        {normalizeMath(children)}
      </ReactMarkdown>
    </div>
  );
}

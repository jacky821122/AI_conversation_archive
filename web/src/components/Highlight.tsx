// 對 text 中所有出現的 query 子字串做高亮（契合 trigram/CJK，無需斷詞）

export default function Highlight({ text, query }: { text: string; query: string }) {
  const q = query.trim();
  if (!q) return <>{text}</>;

  const lower = text.toLowerCase();
  const needle = q.toLowerCase();
  const out: (string | JSX.Element)[] = [];
  let i = 0;
  let key = 0;
  while (i < text.length) {
    const hit = lower.indexOf(needle, i);
    if (hit === -1) {
      out.push(text.slice(i));
      break;
    }
    if (hit > i) out.push(text.slice(i, hit));
    out.push(
      <mark key={key++} className="kw">
        {text.slice(hit, hit + needle.length)}
      </mark>,
    );
    i = hit + needle.length;
  }
  return <>{out}</>;
}

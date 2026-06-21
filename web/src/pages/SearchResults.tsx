import { useSearchParams, Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, platformMeta, PLATFORMS, fmtDate } from "../lib/api";
import Highlight from "../components/Highlight";
import { Loading, ErrorBox } from "./Dashboard";

export default function SearchResults() {
  const [params, setParams] = useSearchParams();
  const q = params.get("q") ?? "";
  const platform = params.get("platform") ?? "";

  const { data, isLoading, error } = useQuery({
    queryKey: ["search", q, platform],
    queryFn: () => api.search(q, platform || undefined, 50),
    enabled: q.length > 0,
  });

  function setPlatform(p: string) {
    const next = new URLSearchParams(params);
    if (p) next.set("platform", p);
    else next.delete("platform");
    setParams(next);
  }

  if (!q)
    return (
      <div className="py-24 text-center font-mono text-sm text-faint">
        在上面輸入關鍵字，開始挖掘
      </div>
    );

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-baseline gap-x-3 gap-y-2">
        <p className="eyebrow">搜尋</p>
        <span className="font-display text-2xl text-ink">「{q}」</span>
        {data && <span className="font-mono text-sm text-muted">{data.count} 則命中</span>}
        <div className="ml-auto flex gap-1.5">
          <Chip label="全部" active={!platform} onClick={() => setPlatform("")} />
          {PLATFORMS.map((p) => (
            <Chip
              key={p}
              label={platformMeta[p].label}
              color={platformMeta[p].color}
              active={platform === p}
              onClick={() => setPlatform(p)}
            />
          ))}
        </div>
      </header>

      {isLoading && <Loading />}
      {error && <ErrorBox msg={String(error)} />}
      {data && data.results.length === 0 && (
        <div className="py-16 text-center font-mono text-sm text-faint">沒有命中</div>
      )}

      <div>
        {data?.results.map((r) => {
          const meta = platformMeta[r.platform];
          return (
            <Link
              key={`${r.conv_id}#${r.idx}`}
              to={`/c/${encodeURIComponent(r.conv_id)}?m=${r.idx}&q=${encodeURIComponent(q)}`}
              className="group flex items-stretch gap-3 border-b border-line py-4 transition hover:bg-surface"
            >
              <span
                className="w-0.5 shrink-0 rounded-full opacity-60 group-hover:opacity-100"
                style={{ backgroundColor: meta?.color }}
              />
              <div className="min-w-0 flex-1">
                <div className="mb-1.5 flex items-center gap-3 font-mono text-[0.7rem] text-faint">
                  <span style={{ color: meta?.color }}>{meta?.label}</span>
                  <span className="truncate text-muted">{r.title || "未命名對話"}</span>
                  <span className="ml-auto shrink-0">{fmtDate(r.time)}</span>
                </div>
                <p className="whitespace-prewrap line-clamp-3 text-sm leading-relaxed text-ink/80">
                  <span className="mr-1.5 font-mono text-[0.7rem] text-faint">
                    {r.role === "user" ? "我" : "AI"}
                  </span>
                  <Highlight text={r.text} query={q} />
                </p>
              </div>
            </Link>
          );
        })}
      </div>
    </div>
  );
}

function Chip({
  label,
  active,
  color,
  onClick,
}: {
  label: string;
  active: boolean;
  color?: string;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 font-mono text-xs transition ${
        active
          ? "border-ink bg-ink text-paper"
          : "border-line-strong text-muted hover:border-ink hover:text-ink"
      }`}
    >
      {color && <span className="h-2 w-2 rounded-full" style={{ backgroundColor: color }} />}
      {label}
    </button>
  );
}

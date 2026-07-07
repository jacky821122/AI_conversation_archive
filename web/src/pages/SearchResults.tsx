import { useMemo, useState } from "react";
import { useSearchParams, Link } from "react-router-dom";
import { useInfiniteQuery } from "@tanstack/react-query";
import { api, platformMeta, PLATFORMS, fmtDate } from "../lib/api";
import Highlight from "../components/Highlight";
import { Loading, ErrorBox } from "./Dashboard";

const PAGE = 50;

export default function SearchResults() {
  const [params, setParams] = useSearchParams();
  const q = params.get("q") ?? "";
  const platform = params.get("platform") ?? "";

  const { data, isLoading, error, fetchNextPage, hasNextPage, isFetchingNextPage } =
    useInfiniteQuery({
      queryKey: ["search", q, platform],
      queryFn: ({ pageParam }) => api.search(q, platform || undefined, PAGE, pageParam),
      initialPageParam: 0,
      // 後端不回總數；一批滿 PAGE 就假設還有下一批，offset 累加。
      getNextPageParam: (lastPage, allPages) =>
        lastPage.results.length === PAGE ? allPages.length * PAGE : undefined,
      enabled: q.length > 0,
    });

  type Hit = Awaited<ReturnType<typeof api.search>>["results"][number];
  const groups = useMemo(() => {
    const out: {
      conv_id: string;
      platform: Hit["platform"];
      title: string;
      best: Hit;
      hits: Hit[];
    }[] = [];
    const seen = new Map<string, number>();
    // 累積所有已載入批次後再分組：同一對話的命中跨批次也能正確合併，不會破碎。
    for (const r of data?.pages.flatMap((p) => p.results) ?? []) {
      let gi = seen.get(r.conv_id);
      if (gi === undefined) {
        gi = out.length;
        seen.set(r.conv_id, gi);
        out.push({ conv_id: r.conv_id, platform: r.platform, title: r.title, best: r, hits: [] });
      }
      out[gi].hits.push(r);
    }
    // results 已按 bm25 排序 → 各 thread 首次出現即其最佳命中，thread 間順序沿用；
    // thread 內改依 idx（對話時間序）排列。best 保留為最相關那則，收合時顯示它。
    for (const g of out) g.hits.sort((a, b) => a.idx - b.idx);
    return out;
  }, [data]);
  const total = data?.pages.reduce((n, p) => n + p.results.length, 0) ?? 0;
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  function toggle(id: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

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
        {data && (
          <span className="font-mono text-sm text-muted">
            {total} 則命中{hasNextPage ? "+" : ""} · {groups.length} 個對話
          </span>
        )}
        <div className="no-scrollbar ml-auto flex max-w-full gap-1.5 overflow-x-auto">
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
      {data && total === 0 && (
        <div className="py-16 text-center font-mono text-sm text-faint">沒有命中</div>
      )}

      <div>
        {groups.map((g) => {
          const meta = platformMeta[g.platform];
          const isOpen = expanded.has(g.conv_id);
          const shown = isOpen ? g.hits : [g.best];
          return (
            <div
              key={g.conv_id}
              className="flex items-stretch gap-3 border-b border-line py-4"
            >
              <span
                className="w-0.5 shrink-0 rounded-full opacity-60"
                style={{ backgroundColor: meta?.color }}
              />
              <div className="min-w-0 flex-1">
                <div className="mb-1.5 flex items-center gap-3 font-mono text-[0.7rem] text-faint">
                  <span style={{ color: meta?.color }}>{meta?.label}</span>
                  <span className="min-w-0 truncate text-muted">
                    {g.title || "未命名對話"}
                  </span>
                  {g.hits.length > 1 && (
                    <span className="shrink-0 rounded-full border border-line-strong px-1.5 text-muted">
                      {g.hits.length} 則
                    </span>
                  )}
                  <span className="ml-auto shrink-0">{fmtDate(g.best.time)}</span>
                </div>
                <div className="space-y-1">
                  {shown.map((r) => (
                    <Link
                      key={r.idx}
                      to={`/c/${encodeURIComponent(r.conv_id)}?m=${r.idx}&q=${encodeURIComponent(q)}`}
                      className="-mx-2 block rounded px-2 py-1 transition hover:bg-surface"
                    >
                      <p className="line-clamp-3 text-sm leading-relaxed text-ink/80">
                        <span className="mr-1.5 font-mono text-[0.7rem] text-faint">
                          {r.role === "user" ? "我" : "AI"}
                        </span>
                        <Highlight text={snippet(r.text, q)} query={q} />
                      </p>
                    </Link>
                  ))}
                </div>
                {g.hits.length > 1 && (
                  <button
                    onClick={() => toggle(g.conv_id)}
                    className="mt-2 font-mono text-[0.7rem] text-muted transition hover:text-ink"
                  >
                    {isOpen ? "收合" : `+ 展開其餘 ${g.hits.length - 1} 則命中`}
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {hasNextPage && (
        <div className="pt-6 text-center">
          <button
            onClick={() => fetchNextPage()}
            disabled={isFetchingNextPage}
            className="rounded-full border border-line-strong px-5 py-2 font-mono text-xs text-muted transition hover:border-ink hover:text-ink disabled:opacity-50"
          >
            {isFetchingNextPage ? "載入中…" : "載入更多"}
          </button>
        </div>
      )}
    </div>
  );
}

// 以第一個命中為中心切出片段，確保高亮的關鍵字一定落在 line-clamp 可見範圍內。
// 換行壓成單空白以利在 3 行內閱讀；截斷處補省略號。找不到命中則退回原文開頭。
// 前綴刻意短：中文每行才 ~18 字，前綴太長會把關鍵字擠出 3 行裁切範圍而看不到高亮。
const BEFORE = 24;
const AFTER = 180;
function snippet(text: string, query: string): string {
  const q = query.trim();
  const hit = q ? text.toLowerCase().indexOf(q.toLowerCase()) : -1;
  if (hit === -1) return text.slice(0, BEFORE + AFTER).replace(/\s+/g, " ").trim();
  const start = Math.max(0, hit - BEFORE);
  const end = Math.min(text.length, hit + q.length + AFTER);
  let s = text.slice(start, end).replace(/\s+/g, " ").trim();
  if (start > 0) s = "… " + s;
  if (end < text.length) s = s + " …";
  return s;
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
      className={`inline-flex shrink-0 items-center gap-1.5 rounded-full border px-3 py-1 font-mono text-xs transition ${
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

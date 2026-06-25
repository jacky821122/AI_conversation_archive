import { useSearchParams } from "react-router-dom";
import { useInfiniteQuery } from "@tanstack/react-query";
import { X } from "lucide-react";
import { api, platformMeta, PLATFORMS, fmtMonth } from "../lib/api";
import ConvListItem from "../components/ConvListItem";
import { Loading, ErrorBox } from "./Dashboard";

const PAGE = 30;

export default function Browse() {
  const [params, setParams] = useSearchParams();
  const month = params.get("month") ?? "";
  const platform = params.get("platform") ?? "";

  const query = useInfiniteQuery({
    queryKey: ["browse", month, platform],
    initialPageParam: 0,
    queryFn: ({ pageParam }) =>
      api.conversations({
        month: month || undefined,
        platform: platform || undefined,
        limit: PAGE,
        offset: pageParam,
      }),
    getNextPageParam: (last, all) => {
      const loaded = all.reduce((n, p) => n + p.items.length, 0);
      return loaded < last.total ? loaded : undefined;
    },
  });

  function patch(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next);
  }

  // 嚴格從「目前 key 的已載入資料」取值；pending 時不顯示舊資料，
  // 避免標題月份與清單內容不一致。
  const ready = !query.isPending && !query.error;
  const total = ready ? query.data!.pages[0]?.total ?? 0 : null;
  const items = ready ? query.data!.pages.flatMap((p) => p.items) : [];

  return (
    <div className="space-y-5">
      <header>
        <p className="eyebrow">瀏覽</p>
        <h1 className="mt-2 flex flex-wrap items-baseline gap-3">
          <span className="font-display text-3xl font-semibold text-ink">
            {month ? fmtMonth(month) : "全部對話"}
          </span>
          {total !== null && <span className="font-mono text-sm text-muted">{total} 段</span>}
          {month && (
            <button
              onClick={() => patch("month", "")}
              className="inline-flex items-center gap-1 font-mono text-xs text-faint hover:text-accent"
            >
              <X className="h-3 w-3" /> 清除月份
            </button>
          )}
        </h1>
      </header>

      <div className="no-scrollbar -mx-5 flex gap-1.5 overflow-x-auto px-5">
        <Chip label="全部" active={!platform} onClick={() => patch("platform", "")} />
        {PLATFORMS.map((p) => (
          <Chip
            key={p}
            label={platformMeta[p].label}
            active={platform === p}
            color={platformMeta[p].color}
            onClick={() => patch("platform", p)}
          />
        ))}
      </div>

      {query.isPending && <Loading />}
      {query.error && <ErrorBox msg={String(query.error)} />}
      {ready && items.length === 0 && (
        <div className="py-16 text-center font-mono text-sm text-faint">這個月沒有對話</div>
      )}

      <div>
        {items.map((c) => <ConvListItem key={c.id} conv={c} />)}
      </div>

      {ready && query.hasNextPage && (
        <div className="pt-2 text-center">
          <button
            onClick={() => query.fetchNextPage()}
            disabled={query.isFetchingNextPage}
            className="rounded-full border border-line-strong px-5 py-2 font-mono text-xs text-muted transition hover:border-accent hover:text-accent disabled:opacity-50"
          >
            {query.isFetchingNextPage ? "載入中…" : "載入更多"}
          </button>
        </div>
      )}
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

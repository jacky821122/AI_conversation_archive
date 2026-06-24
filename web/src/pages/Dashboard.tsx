import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate, Link } from "react-router-dom";
import { Library } from "lucide-react";
import { api, platformMeta, PLATFORMS, fmtMonth } from "../lib/api";
import MonthChart from "../components/MonthChart";
import MonthList from "../components/MonthList";
import ConvListItem from "../components/ConvListItem";

export default function Dashboard() {
  const navigate = useNavigate();
  const [metric, setMetric] = useState<"count" | "tokens">("count");
  const stats = useQuery({ queryKey: ["stats"], queryFn: api.stats });
  const recent = useQuery({
    queryKey: ["recent"],
    queryFn: () => api.conversations({ order: "recent", limit: 8 }),
  });

  if (stats.isLoading) return <Loading />;
  if (stats.error) return <ErrorBox msg={String(stats.error)} />;
  const s = stats.data!;

  const months = s.distribution.map((d) => d.month).sort();
  const span =
    months.length > 0 ? `${fmtMonth(months[0])} – ${fmtMonth(months[months.length - 1])}` : "";

  return (
    <div className="space-y-14">
      {/* Hero：thesis */}
      <section>
        <p className="eyebrow">個人對話檔案庫</p>
        <h1 className="mt-3 flex items-baseline gap-3">
          <span className="font-display text-6xl font-semibold leading-none tracking-tight text-ink">
            {s.conversations.toLocaleString()}
          </span>
          <span className="font-display text-2xl text-muted">段對話</span>
        </h1>
        <p className="mt-4 max-w-xl font-mono text-xs leading-relaxed text-muted">
          {s.messages.toLocaleString()} 則訊息 · {span}
        </p>
        <div className="mt-3 flex flex-wrap gap-x-6 gap-y-1 font-mono text-xs">
          {PLATFORMS.map((p) => (
            <span key={p} className="inline-flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full" style={{ backgroundColor: platformMeta[p].color }} />
              <span className="text-muted">{platformMeta[p].label}</span>
              <span className="text-ink">{(s.per_platform[p] ?? 0).toLocaleString()}</span>
            </span>
          ))}
        </div>

        <Link
          to="/ask"
          className="mt-6 inline-flex items-center gap-2 rounded-full border border-ink bg-ink px-5 py-2.5 font-mono text-xs text-paper transition hover:opacity-90"
        >
          <Library className="h-4 w-4" />
          問問館長
        </Link>
      </section>

      {/* Signature：可點擊的思緒時間軸（桌面圖表 / 手機清單） */}
      <section>
        <div className="mb-2 flex items-baseline justify-between">
          <h2 className="font-display text-lg font-semibold text-ink">思緒的時間軸</h2>
          <div className="flex items-center gap-3">
            <div className="flex rounded-full border border-line p-0.5 font-mono text-[0.7rem]">
              <button
                onClick={() => setMetric("count")}
                className={`rounded-full px-2.5 py-1 transition ${
                  metric === "count" ? "bg-ink text-paper" : "text-muted hover:text-ink"
                }`}
              >
                則數
              </button>
              <button
                onClick={() => setMetric("tokens")}
                className={`rounded-full px-2.5 py-1 transition ${
                  metric === "tokens" ? "bg-ink text-paper" : "text-muted hover:text-ink"
                }`}
              >
                token
              </button>
            </div>
            <span className="hidden font-mono text-[0.7rem] text-faint sm:inline">
              點任一月份，回到那時候
            </span>
          </div>
        </div>
        <div className="hidden sm:block">
          <MonthChart
            distribution={s.distribution}
            onSelectMonth={(m) => navigate(`/browse?month=${m}`)}
            metric={metric}
          />
        </div>
        <div className="sm:hidden">
          <MonthList
            distribution={s.distribution}
            onSelectMonth={(m) => navigate(`/browse?month=${m}`)}
            metric={metric}
          />
        </div>
      </section>

      {/* 最近 */}
      <section>
        <h2 className="mb-2 font-display text-lg font-semibold text-ink">最近</h2>
        <div>
          {recent.data?.items.map((c) => <ConvListItem key={c.id} conv={c} />)}
        </div>
      </section>
    </div>
  );
}

export function Loading() {
  return <div className="py-24 text-center font-mono text-sm text-faint">載入中…</div>;
}

export function ErrorBox({ msg }: { msg: string }) {
  return (
    <div className="rounded-md border border-line-strong bg-accent-soft p-4 text-sm text-accent">
      {msg}
    </div>
  );
}

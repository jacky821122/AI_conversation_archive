import { useState } from "react";
import { ChevronDown } from "lucide-react";
import { Stats, platformMeta, PLATFORMS } from "../lib/api";
import { Metric } from "./MetricToggle";

// 手機版時間軸：以年分組的可點月份清單（大點擊區、垂直捲動、好讀）。
type MonthRow = { month: string; total: number; parts: Record<string, number> };

function group(
  distribution: Stats["distribution"],
  metric: Metric,
) {
  const byMonth = new Map<string, MonthRow>();
  let max = 0;
  for (const d of distribution) {
    const row = byMonth.get(d.month) ?? { month: d.month, total: 0, parts: {} };
    const v = metric === "tokens" ? d.tokens : d.n;
    row.parts[d.platform] = v;
    row.total += v;
    byMonth.set(d.month, row);
    if (row.total > max) max = row.total;
  }
  const rows = Array.from(byMonth.values()).sort((a, b) => b.month.localeCompare(a.month));
  // 依年分組（新→舊）
  const byYear = new Map<string, MonthRow[]>();
  for (const r of rows) {
    const y = r.month.slice(0, 4);
    (byYear.get(y) ?? byYear.set(y, []).get(y)!).push(r);
  }
  return { byYear, max };
}

export default function MonthList({
  distribution,
  onSelectMonth,
  metric,
}: {
  distribution: Stats["distribution"];
  onSelectMonth: (month: string) => void;
  metric: Metric;
}) {
  const { byYear, max } = group(distribution, metric);
  const years = Array.from(byYear.keys());
  // 預設全展開；收合的年份放進 set。
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());

  function toggleYear(year: string) {
    setCollapsed((prev) => {
      const next = new Set(prev);
      next.has(year) ? next.delete(year) : next.add(year);
      return next;
    });
  }

  return (
    <div className="space-y-6">
      {years.map((year) => {
        const isOpen = !collapsed.has(year);
        return (
          <div key={year}>
            <button
              onClick={() => toggleYear(year)}
              aria-expanded={isOpen}
              className="mb-3 flex w-full items-center gap-1.5 py-1 font-mono text-xs text-faint transition active:text-ink"
            >
              <ChevronDown
                className={`h-3.5 w-3.5 transition-transform ${isOpen ? "" : "-rotate-90"}`}
              />
              {year}
            </button>
            {isOpen && (
              <div>
                {byYear.get(year)!.map((r) => (
                  <button
                    key={r.month}
                    onClick={() => onSelectMonth(r.month)}
                    className="flex w-full items-center gap-3 border-b border-line py-2.5 text-left transition active:bg-surface"
                  >
                    <span className="w-12 shrink-0 font-mono text-sm text-ink">
                      {Number(r.month.slice(5))}月
                    </span>
                    {/* 比例條 */}
                    <span className="flex h-2.5 flex-1 overflow-hidden rounded-full bg-line">
                      {PLATFORMS.map((p) =>
                        r.parts[p] ? (
                          <span
                            key={p}
                            style={{
                              width: `${(r.parts[p] / max) * 100}%`,
                              backgroundColor: platformMeta[p].color,
                            }}
                          />
                        ) : null,
                      )}
                    </span>
                    <span className="w-14 shrink-0 text-right font-mono text-xs text-muted">
                      {r.total.toLocaleString()}
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>
        );
      })}
      <p className="font-mono text-[0.7rem] text-faint">點任一月份，看當月對話</p>
    </div>
  );
}

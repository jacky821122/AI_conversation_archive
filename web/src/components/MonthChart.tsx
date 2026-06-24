import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  Tooltip,
} from "recharts";
import { Stats, platformMeta, PLATFORMS, fmtMonth } from "../lib/api";

type Row = { month: string; total: number } & Record<string, number | string>;

function buildRows(
  distribution: Stats["distribution"],
  metric: "count" | "tokens",
): Row[] {
  const byMonth = new Map<string, Row>();
  for (const d of distribution) {
    const row = byMonth.get(d.month) ?? ({ month: d.month, total: 0 } as Row);
    const v = metric === "tokens" ? d.tokens : d.n;
    row[d.platform] = v;
    row.total = (row.total as number) + v;
    byMonth.set(d.month, row);
  }
  return Array.from(byMonth.values()).sort((a, b) =>
    a.month.localeCompare(b.month),
  );
}

function TimelineTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-md border border-line-strong bg-surface px-3 py-2 shadow-sm">
      <div className="font-display text-sm font-semibold text-ink">{fmtMonth(label)}</div>
      <div className="mt-1 space-y-0.5">
        {payload
          .filter((p: any) => p.value)
          .map((p: any) => (
            <div key={p.name} className="flex items-center gap-2 font-mono text-[0.7rem]">
              <span className="h-2 w-2 rounded-full" style={{ backgroundColor: p.color }} />
              <span className="text-muted">{platformMeta[p.dataKey as keyof typeof platformMeta]?.label}</span>
              <span className="ml-auto text-ink">{Number(p.value).toLocaleString()}</span>
            </div>
          ))}
      </div>
      <div className="mt-1.5 font-mono text-[0.65rem] text-accent">點擊看這個月 →</div>
    </div>
  );
}

// 每年只在第一次出現時顯示年份刻度，做出年界線。
function makeYearTick() {
  const seen = new Set<string>();
  return function YearTick({ x, y, payload }: any) {
    const year = String(payload.value).slice(0, 4);
    const first = !seen.has(year);
    if (first) seen.add(year);
    return (
      <text
        x={x}
        y={y + 12}
        textAnchor="middle"
        className="fill-faint font-mono"
        fontSize={10}
      >
        {first ? year : ""}
      </text>
    );
  };
}

export default function MonthChart({
  distribution,
  onSelectMonth,
  metric,
}: {
  distribution: Stats["distribution"];
  onSelectMonth: (month: string) => void;
  metric: "count" | "tokens";
}) {
  const data = buildRows(distribution, metric);
  if (data.length === 0) {
    return <div className="font-mono text-sm text-faint">尚無時間資料</div>;
  }

  return (
    <ResponsiveContainer width="100%" height={260}>
      <BarChart
        data={data}
        margin={{ top: 8, right: 4, left: 4, bottom: 4 }}
        barCategoryGap={2}
        onClick={(state: any) => {
          if (state?.activeLabel) onSelectMonth(state.activeLabel);
        }}
        style={{ cursor: "pointer" }}
      >
        <XAxis
          dataKey="month"
          tickLine={false}
          axisLine={{ stroke: "#ddd5c8" }}
          interval={0}
          tick={makeYearTick() as any}
          height={24}
        />
        <Tooltip
          content={<TimelineTooltip />}
          cursor={{ fill: "#6b3f5b", fillOpacity: 0.08 }}
        />
        {PLATFORMS.map((p, i) => (
          <Bar
            key={p}
            dataKey={p}
            name={platformMeta[p].label}
            stackId="a"
            fill={platformMeta[p].color}
            radius={i === PLATFORMS.length - 1 ? [2, 2, 0, 0] : undefined}
          />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}

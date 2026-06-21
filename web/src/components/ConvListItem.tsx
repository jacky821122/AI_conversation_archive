import { Link } from "react-router-dom";
import { platformMeta, ConvSummary, fmtDate } from "../lib/api";

// 帳本式列：左側細色條標記平台，標題為主，數據用 mono。
export default function ConvListItem({ conv }: { conv: ConvSummary }) {
  const meta = platformMeta[conv.platform];
  return (
    <Link
      to={`/c/${encodeURIComponent(conv.id)}`}
      className="group flex items-stretch gap-3 border-b border-line py-3 transition hover:bg-surface"
    >
      <span
        className="w-0.5 shrink-0 rounded-full opacity-60 group-hover:opacity-100"
        style={{ backgroundColor: meta?.color ?? "#79736b" }}
      />
      <div className="min-w-0 flex-1">
        <div className="truncate text-[0.95rem] text-ink group-hover:text-accent">
          {conv.title || "未命名對話"}
        </div>
        <div className="mt-1 flex items-center gap-3 font-mono text-[0.7rem] text-faint">
          <span style={{ color: meta?.color }}>{meta?.label ?? conv.platform}</span>
          <span>{fmtDate(conv.create_time)}</span>
          <span>{conv.n_messages} 則</span>
        </div>
      </div>
    </Link>
  );
}

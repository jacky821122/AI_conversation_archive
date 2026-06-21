import { platformMeta, Platform } from "../lib/api";

// 極簡徽章：彩色圓點承載平台語意，文字維持安靜。
export default function PlatformBadge({ platform }: { platform: Platform }) {
  const meta = platformMeta[platform] ?? { label: platform, color: "#79736b" };
  return (
    <span className="inline-flex items-center gap-1.5 font-mono text-[0.7rem] tracking-wide text-muted">
      <span
        className="h-2 w-2 rounded-full"
        style={{ backgroundColor: meta.color }}
      />
      {meta.label}
    </span>
  );
}

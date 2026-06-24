// 則數 / token 切換：單一撥桿開關，點任一處即翻轉（手機桌面共用）。
export type Metric = "count" | "tokens";

export default function MetricToggle({
  metric,
  onChange,
}: {
  metric: Metric;
  onChange: (m: Metric) => void;
}) {
  const isTokens = metric === "tokens";
  return (
    <button
      type="button"
      role="switch"
      aria-checked={isTokens}
      aria-label="切換時間軸度量：則數或 token"
      onClick={() => onChange(isTokens ? "count" : "tokens")}
      className="relative inline-flex select-none items-center rounded-full border border-line bg-surface p-0.5 font-mono text-[0.7rem]"
    >
      {/* 滑塊 */}
      <span
        className="absolute top-0.5 bottom-0.5 rounded-full bg-ink transition-all duration-200"
        style={{ left: isTokens ? "50%" : "0.125rem", right: isTokens ? "0.125rem" : "50%" }}
      />
      <span
        className={`relative z-10 px-2.5 py-1 transition-colors ${
          !isTokens ? "text-paper" : "text-muted"
        }`}
      >
        則數
      </span>
      <span
        className={`relative z-10 px-2.5 py-1 transition-colors ${
          isTokens ? "text-paper" : "text-muted"
        }`}
      >
        token
      </span>
    </button>
  );
}

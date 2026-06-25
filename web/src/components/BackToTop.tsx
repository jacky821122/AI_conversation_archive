import { ArrowUp } from "lucide-react";
import { useScrollDirection } from "../lib/scroll";

// 懸浮「回到頂端」鈕：捲過一定距離才出現，手機＋桌面皆適用。
// 近似玻璃圓鈕；手機置於膠囊 tab bar 上方、桌面置於右下角。
export default function BackToTop() {
  const { y } = useScrollDirection();
  const show = y > 400;
  return (
    <button
      onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}
      aria-label="回到頂端"
      className={`fixed right-4 z-40 grid h-11 w-11 place-items-center rounded-full
        border border-line-strong/50 bg-paper/70 text-muted shadow-lg backdrop-blur-xl
        backdrop-saturate-150 transition-all duration-300 hover:text-accent
        bottom-[calc(5.75rem+env(safe-area-inset-bottom))] sm:bottom-6 sm:right-6
        ${show ? "translate-y-0 opacity-100" : "pointer-events-none translate-y-4 opacity-0"}`}
    >
      <ArrowUp className="h-5 w-5" />
    </button>
  );
}

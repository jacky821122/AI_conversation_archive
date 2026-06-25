import { useEffect, useState } from "react";

export type ScrollDir = "up" | "down";

// 單一捲動監聽（passive + rAF 節流），回傳目前 scrollY 與最近的捲動方向。
// 給「回頂端鈕」顯示判斷與「Threads 式 tab bar 隱藏」共用，避免多個 scroll listener。
export function useScrollDirection(): { y: number; dir: ScrollDir } {
  const [state, setState] = useState<{ y: number; dir: ScrollDir }>({
    y: typeof window === "undefined" ? 0 : window.scrollY,
    dir: "up",
  });

  useEffect(() => {
    let last = window.scrollY;
    let ticking = false;
    const onScroll = () => {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(() => {
        const y = window.scrollY;
        // 接近頂端一律視為 up（避免回彈造成 tab bar 抖動）；其餘看與上次的差。
        const dir: ScrollDir = y <= 8 || y < last ? "up" : y > last ? "down" : "up";
        setState((s) => (s.y === y && s.dir === dir ? s : { y, dir }));
        last = y;
        ticking = false;
      });
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return state;
}

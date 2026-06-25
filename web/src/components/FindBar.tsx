import { useCallback, useEffect, useRef, useState, RefObject } from "react";
import { ChevronUp, ChevronDown, X } from "lucide-react";

// 頁內關鍵字導覽（iOS 尋找式）：對容器內既有的 .kw 命中元素做上下切換 + 計數。
// 高亮本身由 Highlight 元件（user）與 Markdown 的 rehype 外掛（assistant）產生，
// 這裡只負責「當前命中」標記（.kw-current）、捲動置中與計數。
export function useFind(
  containerRef: RefObject<HTMLElement | null>,
  query: string,
  matchIdx: number | null,
  // 內容就緒訊號（如已載入的訊息數）：資料載入後 containerRef.current 才掛上，
  // ref 本身識別不變不會觸發 effect，故用此值變動來重掃。
  ready: unknown = null,
) {
  const [total, setTotal] = useState(0);
  const [current, setCurrent] = useState(0); // 0-based
  const hitsRef = useRef<HTMLElement[]>([]);
  const currentRef = useRef(0);
  const initedRef = useRef(false);

  const focus = useCallback((idx: number, behavior: ScrollBehavior) => {
    const hits = hitsRef.current;
    hits.forEach((el) => el.classList.remove("kw-current"));
    const el = hits[idx];
    if (!el) return;
    el.classList.add("kw-current");
    el.scrollIntoView({ block: "center", behavior });
    currentRef.current = idx;
    setCurrent(idx);
  }, []);

  // query 變更時重置初始化狀態（換關鍵字＝重新定位）
  useEffect(() => {
    initedRef.current = false;
    currentRef.current = 0;
    setCurrent(0);
  }, [query]);

  // 掃描命中；展開／KaTeX 等非同步渲染後由 MutationObserver 重掃。
  useEffect(() => {
    const root = containerRef.current;
    if (!query.trim() || !root) {
      hitsRef.current = [];
      setTotal(0);
      return;
    }
    let timer: number | undefined;

    const rescan = () => {
      const hits = Array.from(root.querySelectorAll<HTMLElement>(".kw"));
      hitsRef.current = hits;
      setTotal(hits.length);
      if (!hits.length) return;

      if (!initedRef.current) {
        // 初始定位：命中訊息(data-idx)內第一個 .kw，否則第一個。
        let start = 0;
        if (matchIdx != null) {
          const i = hits.findIndex((el) => el.closest(`[data-idx="${matchIdx}"]`));
          if (i >= 0) start = i;
        }
        initedRef.current = true;
        requestAnimationFrame(() => focus(start, "auto"));
      } else {
        // 重掃後讓計數對齊目前被標記的元素（展開可能新增命中）。
        const ci = hits.findIndex((el) => el.classList.contains("kw-current"));
        if (ci >= 0 && ci !== currentRef.current) {
          currentRef.current = ci;
          setCurrent(ci);
        }
      }
    };

    rescan();
    const obs = new MutationObserver(() => {
      window.clearTimeout(timer);
      timer = window.setTimeout(rescan, 150);
    });
    obs.observe(root, { childList: true, subtree: true, characterData: true });
    return () => {
      obs.disconnect();
      window.clearTimeout(timer);
    };
  }, [query, matchIdx, containerRef, focus, ready]);

  const go = useCallback(
    (delta: number) => {
      const n = hitsRef.current.length;
      if (!n) return;
      focus((currentRef.current + delta + n) % n, "smooth");
    },
    [focus],
  );

  return {
    total,
    current,
    next: useCallback(() => go(1), [go]),
    prev: useCallback(() => go(-1), [go]),
  };
}

export function FindBar({
  total,
  current,
  onPrev,
  onNext,
  onClose,
}: {
  total: number;
  current: number;
  onPrev: () => void;
  onNext: () => void;
  onClose: () => void;
}) {
  if (total <= 0) return null;
  return (
    <div
      className="fixed left-1/2 z-40 flex -translate-x-1/2 items-center gap-1 rounded-full
        border border-line-strong bg-paper/95 px-2 py-1 shadow-lg backdrop-blur
        bottom-[calc(4.75rem+env(safe-area-inset-bottom))] sm:bottom-6"
    >
      <button
        onClick={onPrev}
        aria-label="上一個"
        className="rounded-full p-1.5 text-muted transition hover:text-accent"
      >
        <ChevronUp className="h-4 w-4" />
      </button>
      <span className="min-w-[3.2rem] text-center font-mono text-xs tabular-nums text-muted">
        {current + 1}/{total}
      </span>
      <button
        onClick={onNext}
        aria-label="下一個"
        className="rounded-full p-1.5 text-muted transition hover:text-accent"
      >
        <ChevronDown className="h-4 w-4" />
      </button>
      <span className="mx-0.5 h-4 w-px bg-line-strong" />
      <button
        onClick={onClose}
        aria-label="關閉尋找"
        className="rounded-full p-1.5 text-muted transition hover:text-accent"
      >
        <X className="h-4 w-4" />
      </button>
    </div>
  );
}

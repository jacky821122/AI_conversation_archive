import { useRef, useState, PointerEvent as ReactPointerEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Home, FolderOpen, Library, ClipboardList } from "lucide-react";
import { useScrollDirection } from "../lib/scroll";

// 站台分頁：桌面頂部 nav 與手機膠囊 tab bar 共用同一份來源。
export const TABS = [
  { to: "/", label: "總覽", icon: Home },
  { to: "/browse", label: "瀏覽", icon: FolderOpen },
  { to: "/ask", label: "館長", icon: Library },
  { to: "/plan", label: "計畫", icon: ClipboardList },
];

const TAB_W = 64; // 每個 tab 寬（px），與 w-16 一致
const PAD = 6; // 膠囊內距（px），與 p-1.5 一致
const INDW = 52; // 指示器靜止寬（px）
const N = TABS.length;

function activeIndexOf(pathname: string): number {
  return TABS.findIndex((t) => (t.to === "/" ? pathname === "/" : pathname.startsWith(t.to)));
}

// 手機膠囊式底部分頁列（Threads 風）：近似玻璃、下滑隱藏上滑出現、
// 按住放大成玻璃泡泡、拖曳時連續跟手指（類比位置），放開吸附到最近 tab。
// 桌面隱藏（sm:hidden，桌面用頂部 nav）。
export default function TabBar() {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const { y, dir } = useScrollDirection();
  const rowRef = useRef<HTMLDivElement>(null);
  const [dragX, setDragX] = useState<number | null>(null); // 手指在膠囊內的 x（px）
  const [pressed, setPressed] = useState(false);

  const activeIndex = activeIndexOf(pathname);
  const trackMin = PAD + TAB_W / 2;
  const trackMax = PAD + (N - 0.5) * TAB_W;
  const restCx = activeIndex >= 0 ? PAD + activeIndex * TAB_W + TAB_W / 2 : trackMin;
  const dragging = dragX !== null;
  const cx = dragging ? Math.max(trackMin, Math.min(trackMax, dragX!)) : restCx;
  const hoverIndex = Math.max(0, Math.min(N - 1, Math.round((cx - PAD - TAB_W / 2) / TAB_W)));
  const displayIndex = dragging ? hoverIndex : activeIndex;
  const showIndicator = displayIndex >= 0 || dragging;
  const hidden = dir === "down" && y > 80;

  function fingerX(clientX: number): number {
    const r = rowRef.current?.getBoundingClientRect();
    return r ? clientX - r.left : 0;
  }
  // pointer capture 讓拖曳離開膠囊仍收得到 move；tap 與 drag 都在 pointerUp 導覽
  // （capture 會攔截 button click），onClick 僅作鍵盤備援。
  function onPointerDown(e: ReactPointerEvent) {
    rowRef.current?.setPointerCapture(e.pointerId);
    setPressed(true);
    setDragX(fingerX(e.clientX));
  }
  function onPointerMove(e: ReactPointerEvent) {
    if (dragX === null) return;
    setDragX(fingerX(e.clientX));
  }
  function onPointerUp() {
    if (dragX !== null && hoverIndex !== activeIndex) navigate(TABS[hoverIndex].to);
    setDragX(null);
    setPressed(false);
  }

  return (
    <nav
      className={`fixed inset-x-0 bottom-0 z-30 flex select-none justify-center pb-[calc(0.25rem+env(safe-area-inset-bottom))]
        transition-transform duration-300 ease-out sm:hidden ${hidden ? "translate-y-[185%]" : "translate-y-0"}`}
    >
      <div
        ref={rowRef}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
        style={{ touchAction: "none", WebkitUserSelect: "none", WebkitTouchCallout: "none" }}
        className="relative flex select-none rounded-full border border-line-strong/50 bg-paper/70 p-1.5
          shadow-[0_8px_30px_rgba(0,0,0,0.18)] backdrop-blur-xl backdrop-saturate-150 dark:bg-paper/60"
      >
        {/* 滑動指示器：靜止為玻璃藥丸；按住放大成泡泡（凸出上緣＋彩色折射邊近似 liquid glass）。
            translate 與 scale 拆成獨立 CSS 屬性分開設 transition：
            - 位置(translate)：拖曳時短過渡＝液態跟手、放開時較長＝平滑吸附。
            - 放大(scale)：永遠帶 spring 過渡，避免按下/放開瞬間跳。 */}
        <span
          aria-hidden
          className="pointer-events-none absolute bottom-1.5 top-1.5 left-0 rounded-full
            bg-surface/75 ring-1 ring-white/40 dark:bg-surface/60"
          style={{
            width: INDW,
            transformOrigin: "center",
            translate: `${cx - INDW / 2}px ${pressed ? -4 : 0}px`,
            scale: pressed ? "1.42" : "1",
            opacity: showIndicator ? 1 : 0,
            willChange: "translate, scale",
            transitionProperty: "translate, scale, opacity, box-shadow",
            transitionDuration: dragging ? "110ms, 260ms, 200ms, 260ms" : "360ms, 260ms, 200ms, 260ms",
            transitionTimingFunction:
              "cubic-bezier(0.22,1,0.36,1), cubic-bezier(0.34,1.56,0.64,1), ease, ease",
            boxShadow: pressed
              ? "0 6px 16px rgba(0,0,0,.18), 2px 0 7px rgba(255,0,128,.22), -2px 0 7px rgba(0,170,255,.22), inset 0 0 0 1px rgba(255,255,255,.45)"
              : "0 1px 3px rgba(0,0,0,.12)",
          }}
        />
        {TABS.map((t, i) => {
          const Icon = t.icon;
          const on = i === displayIndex;
          return (
            <button
              key={t.to}
              onClick={() => navigate(t.to)}
              aria-label={t.label}
              aria-current={i === activeIndex ? "page" : undefined}
              style={{ width: TAB_W }}
              className={`relative z-10 flex select-none flex-col items-center gap-0.5 py-1.5 font-mono text-[0.6rem]
                transition-colors ${on ? "text-accent" : "text-muted"}`}
            >
              <Icon className="h-5 w-5" />
              {t.label}
            </button>
          );
        })}
      </div>
    </nav>
  );
}

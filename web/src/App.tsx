import { useState, useEffect, FormEvent } from "react";
import { Outlet, Link, NavLink, useNavigate, useSearchParams, useLocation } from "react-router-dom";
import { Search, Moon, Sun } from "lucide-react";
import { useTheme } from "./lib/theme";
import TabBar, { TABS } from "./components/TabBar";
import BackToTop from "./components/BackToTop";

export default function App() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const { pathname } = useLocation();
  const [theme, toggleTheme] = useTheme();
  const [q, setQ] = useState(params.get("q") ?? "");

  useEffect(() => {
    setQ(params.get("q") ?? "");
  }, [params]);

  // 換頁回到頁首（換 search params 不影響）。對話頁的 find 初始定位走 rAF/observer
  // 在此之後，故進對話頁仍會捲到命中、其餘頁回頂端。
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    const term = q.trim();
    if (term) navigate(`/search?q=${encodeURIComponent(term)}`);
  }

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-20 border-b border-line bg-paper/85 backdrop-blur">
        <div className="mx-auto flex max-w-5xl items-center gap-5 px-5 py-3.5">
          <Link to="/" className="shrink-0 leading-none">
            <span className="font-display text-xl font-semibold tracking-tight text-ink">
              對話檔案庫
            </span>
          </Link>

          <nav className="hidden gap-4 font-mono text-xs sm:flex">
            {TABS.map((t) => (
              <TopLink key={t.to} to={t.to} label={t.label} />
            ))}
          </nav>

          <form onSubmit={onSubmit} className="relative ml-auto w-full max-w-sm">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-faint" />
            {/* 手機 16px 避免 iOS focus 自動縮放/平移；桌面維持 14px */}
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="搜尋你說過、問過的一切…"
              className="w-full rounded-full border border-line bg-surface py-2 pl-9 pr-4 text-base text-ink outline-none transition placeholder:text-faint focus:border-accent sm:text-sm"
            />
          </form>

          <button
            onClick={toggleTheme}
            aria-label={theme === "dark" ? "切換亮色" : "切換深色"}
            className="shrink-0 rounded-full border border-line p-2 text-muted transition hover:border-accent hover:text-accent"
          >
            {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </button>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-5 py-8">
        <Outlet />
      </main>

      {/* 手機底部留白：避免頁尾被懸浮膠囊 tab bar 遮住（含 iOS 安全區） */}
      <footer className="mx-auto max-w-5xl px-5 pb-[calc(6rem+env(safe-area-inset-bottom))] pt-4 sm:pb-10">
        <p className="font-mono text-[0.65rem] text-faint">
          你的 ChatGPT · Grok · Gemini · Claude 對話，存在本機。
        </p>
      </footer>

      <BackToTop />
      <TabBar />
    </div>
  );
}

function TopLink({ to, label }: { to: string; label: string }) {
  return (
    <NavLink
      to={to}
      end={to === "/"}
      className={({ isActive }) =>
        `transition ${isActive ? "text-accent" : "text-muted hover:text-ink"}`
      }
    >
      {label}
    </NavLink>
  );
}

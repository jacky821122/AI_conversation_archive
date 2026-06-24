import { useState, useEffect, FormEvent } from "react";
import { Outlet, Link, NavLink, useNavigate, useSearchParams } from "react-router-dom";
import { Search, Moon, Sun, Home, FolderOpen, Library, ClipboardList } from "lucide-react";
import { useTheme } from "./lib/theme";

// 站台分頁：桌面頂部 nav 與手機底部 tab bar 共用同一份來源。
const TABS = [
  { to: "/", label: "總覽", icon: Home },
  { to: "/browse", label: "瀏覽", icon: FolderOpen },
  { to: "/ask", label: "館長", icon: Library },
  { to: "/plan", label: "計畫", icon: ClipboardList },
];

export default function App() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [theme, toggleTheme] = useTheme();
  const [q, setQ] = useState(params.get("q") ?? "");

  useEffect(() => {
    setQ(params.get("q") ?? "");
  }, [params]);

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
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="搜尋你說過、問過的一切…"
              className="w-full rounded-full border border-line bg-surface py-2 pl-9 pr-4 text-sm text-ink outline-none transition placeholder:text-faint focus:border-accent"
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

      {/* 手機底部留白：避免內容被固定 tab bar 遮住（含 iOS 安全區） */}
      <main className="mx-auto max-w-5xl px-5 py-8 pb-[calc(4rem+env(safe-area-inset-bottom))] sm:pb-8">
        <Outlet />
      </main>

      <footer className="mx-auto max-w-5xl px-5 pb-10 pt-4">
        <p className="font-mono text-[0.65rem] text-faint">
          你的 ChatGPT · Grok · Gemini · Claude 對話，存在本機。
        </p>
      </footer>

      {/* 手機底部分頁列：桌面隱藏（桌面用頂部 nav） */}
      <nav className="fixed inset-x-0 bottom-0 z-30 border-t border-line bg-paper/95 pb-[env(safe-area-inset-bottom)] backdrop-blur sm:hidden">
        <div className="mx-auto flex max-w-5xl">
          {TABS.map((t) => (
            <BottomLink key={t.to} to={t.to} label={t.label} icon={t.icon} />
          ))}
        </div>
      </nav>
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

function BottomLink({
  to,
  label,
  icon: Icon,
}: {
  to: string;
  label: string;
  icon: typeof Home;
}) {
  return (
    <NavLink
      to={to}
      end={to === "/"}
      className={({ isActive }) =>
        `flex flex-1 flex-col items-center gap-0.5 py-2 font-mono text-[0.6rem] transition ${
          isActive ? "text-accent" : "text-muted"
        }`
      }
    >
      <Icon className="h-5 w-5" />
      {label}
    </NavLink>
  );
}

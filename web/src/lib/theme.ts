import { useEffect, useState } from "react";

export type Theme = "light" | "dark";

function current(): Theme {
  if (typeof document !== "undefined" && document.documentElement.classList.contains("dark"))
    return "dark";
  return "light";
}

// 主題狀態：與 <html class="dark"> 同步，存 localStorage。
// 初始 class 由 index.html 的 inline script 先套好（避免閃白）。
export function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>(current);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    try {
      localStorage.setItem("theme", theme);
    } catch {
      /* ignore */
    }
  }, [theme]);

  return [theme, () => setTheme((t) => (t === "dark" ? "light" : "dark"))];
}

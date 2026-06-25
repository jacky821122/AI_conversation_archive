import { useRef, useState, ReactNode } from "react";
import { useParams, useSearchParams, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { api, platformMeta, fmtDate } from "../lib/api";
import Highlight from "../components/Highlight";
import Markdown from "../components/Markdown";
import { useFind, FindBar } from "../components/FindBar";
import { Loading, ErrorBox } from "./Dashboard";

// 命中訊息可自動整則展開的字數上限：超過則維持分段（避免重現超大訊息卡死）。
const SAFE_FULL = 120000;

export default function ConversationView() {
  const { id } = useParams();
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const matchIdx = params.get("m") ? Number(params.get("m")) : null;
  const q = params.get("q") ?? "";

  const { data, isLoading, error } = useQuery({
    queryKey: ["conv", id],
    queryFn: () => api.conversation(id!),
    enabled: !!id,
  });

  const listRef = useRef<HTMLDivElement>(null);
  const find = useFind(listRef, q, matchIdx, data?.messages.length ?? 0);

  function closeFind() {
    const next = new URLSearchParams(params);
    next.delete("q");
    next.delete("m");
    setParams(next, { replace: true });
  }

  if (isLoading) return <Loading />;
  if (error) return <ErrorBox msg={String(error)} />;
  if (!data) return null;
  const meta = platformMeta[data.platform];

  return (
    <div className="space-y-6">
      <button
        onClick={() => navigate(-1)}
        className="inline-flex items-center gap-1 font-mono text-xs text-muted transition hover:text-accent"
      >
        <ArrowLeft className="h-3.5 w-3.5" /> 返回
      </button>

      <header className="border-b border-line pb-4">
        <h1 className="font-display text-2xl font-semibold leading-snug text-ink break-words">
          {data.title || "未命名對話"}
        </h1>
        <div className="mt-2 flex items-center gap-3 font-mono text-xs text-faint">
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full" style={{ backgroundColor: meta?.color }} />
            <span style={{ color: meta?.color }}>{meta?.label}</span>
          </span>
          <span>{fmtDate(data.create_time)}</span>
          <span>{data.messages.length} 則訊息</span>
        </div>
      </header>

      <div ref={listRef} className="space-y-5">
        {data.messages.map((m) => {
          const isUser = m.role === "user";
          const isMatch = m.idx === matchIdx;
          // 命中訊息預設整則展開，讓 occurrence 一定在 DOM 裡可被 find 抓到、可捲到。
          const expanded = isMatch && m.text.length <= SAFE_FULL;
          return (
            <div
              key={m.idx}
              data-idx={m.idx}
              className={`flex ${isUser ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`max-w-[88%] rounded-2xl px-4 py-3 ${
                  isUser
                    ? "rounded-br-sm bg-ink text-paper"
                    : "rounded-bl-sm border border-line bg-surface text-ink"
                }`}
              >
                <div
                  className={`mb-1 font-mono text-[0.6rem] uppercase tracking-widest ${
                    isUser ? "text-paper/50" : "text-faint"
                  }`}
                >
                  {isUser ? "我" : meta?.label ?? "AI"}
                </div>
                {isUser ? (
                  <div className="whitespace-prewrap text-sm leading-relaxed">
                    <LongContent
                      text={m.text}
                      dark
                      expanded={expanded}
                      render={(t) => (q ? <Highlight text={t} query={q} /> : t)}
                    />
                  </div>
                ) : (
                  <LongContent
                    text={m.text}
                    expanded={expanded}
                    render={(t) => <Markdown highlight={q}>{t}</Markdown>}
                  />
                )}
              </div>
            </div>
          );
        })}
      </div>

      <FindBar
        total={find.total}
        current={find.current}
        onPrev={find.prev}
        onNext={find.next}
        onClose={closeFind}
      />
    </div>
  );
}

// 單次渲染的字數上限。極長訊息（例如一次貼上整份文件/log，數十萬字）若全量
// 渲染會讓頁面高達數十萬 px、手機首屏直接卡死，故先渲染前段、其餘分段展開。
const CHUNK = 20000;

function LongContent({
  text,
  render,
  dark = false,
  expanded = false,
}: {
  text: string;
  render: (slice: string) => ReactNode;
  dark?: boolean;
  expanded?: boolean;
}) {
  const [shown, setShown] = useState(() =>
    expanded ? text.length : Math.min(text.length, CHUNK),
  );
  const remaining = text.length - shown;
  if (remaining <= 0) return <>{render(text)}</>;

  // dark：在深色泡泡（user）內，按鈕需用淺色描邊才看得見。
  const btn = dark
    ? "rounded-full border border-paper/30 px-3 py-1 text-paper/80 transition hover:border-paper/60 hover:text-paper"
    : "rounded-full border border-line-strong px-3 py-1 text-muted transition hover:border-accent hover:text-accent";
  return (
    <>
      {render(text.slice(0, shown))}
      <div className="mt-3 flex flex-wrap items-center gap-2 font-mono text-xs">
        <button onClick={() => setShown((s) => Math.min(text.length, s + CHUNK))} className={btn}>
          展開更多
        </button>
        <button onClick={() => setShown(text.length)} className={btn}>
          全部展開
        </button>
        <span className={dark ? "text-paper/50" : "text-faint"}>
          剩 {remaining.toLocaleString()} 字
        </span>
      </div>
    </>
  );
}

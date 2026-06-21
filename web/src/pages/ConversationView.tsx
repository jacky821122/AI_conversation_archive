import { useEffect, useRef } from "react";
import { useParams, useSearchParams, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { api, platformMeta, fmtDate } from "../lib/api";
import Highlight from "../components/Highlight";
import Markdown from "../components/Markdown";
import { Loading, ErrorBox } from "./Dashboard";

export default function ConversationView() {
  const { id } = useParams();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const matchIdx = params.get("m") ? Number(params.get("m")) : null;
  const q = params.get("q") ?? "";

  const { data, isLoading, error } = useQuery({
    queryKey: ["conv", id],
    queryFn: () => api.conversation(id!),
    enabled: !!id,
  });

  const markRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (data && markRef.current) {
      markRef.current.scrollIntoView({ block: "center" });
    }
  }, [data]);

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
        <h1 className="font-display text-2xl font-semibold leading-snug text-ink">
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

      <div className="space-y-5">
        {data.messages.map((m) => {
          const isUser = m.role === "user";
          const isMatch = m.idx === matchIdx;
          return (
            <div
              key={m.idx}
              ref={isMatch ? markRef : undefined}
              className={`flex ${isUser ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`max-w-[88%] rounded-2xl px-4 py-3 ${
                  isUser
                    ? "rounded-br-sm bg-ink text-paper"
                    : "rounded-bl-sm border border-line bg-surface text-ink"
                } ${isMatch ? "ring-2 ring-accent ring-offset-2 ring-offset-paper" : ""}`}
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
                    {q ? <Highlight text={m.text} query={q} /> : m.text}
                  </div>
                ) : (
                  <Markdown>{m.text}</Markdown>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

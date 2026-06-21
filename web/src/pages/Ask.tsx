import { useState, FormEvent } from "react";
import { Link } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Sparkles, Power, Loader2, KeyRound, CircleDot } from "lucide-react";
import { api, ApiError, platformMeta, fmtDate, AskResponse } from "../lib/api";
import Markdown from "../components/Markdown";

// 模型生命週期由使用者手動掌控：載入才碰 GPU、問完可釋放 VRAM
// （閒置 15 分 server 也會自動釋放）。token 存 localStorage，load/ask/release 共用。
export default function Ask() {
  const qc = useQueryClient();
  const [token, setToken] = useState(() => localStorage.getItem("ask_token") ?? "");
  const [tokenDraft, setTokenDraft] = useState("");
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<AskResponse | null>(null);
  const [needToken, setNeedToken] = useState(false);

  const status = useQuery({
    queryKey: ["model-status"],
    queryFn: api.modelStatus,
    refetchInterval: 20_000, // 同步 server 端的閒置自動釋放
  });
  const loaded = status.data?.loaded ?? false;

  function saveToken() {
    const t = tokenDraft.trim();
    if (!t) return;
    localStorage.setItem("ask_token", t);
    setToken(t);
    setTokenDraft("");
    setNeedToken(false);
  }

  // 401 → token 失效，要求重輸；其餘錯誤直接拋給 UI 顯示。
  function handleErr(e: unknown) {
    if (e instanceof ApiError && e.status === 401) setNeedToken(true);
  }

  const loadMut = useMutation({
    mutationFn: () => api.modelLoad(token),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["model-status"] }),
    onError: handleErr,
  });
  const releaseMut = useMutation({
    mutationFn: () => api.modelRelease(token),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["model-status"] }),
    onError: handleErr,
  });
  const askMut = useMutation({
    mutationFn: () => api.ask(question.trim(), token, 8),
    onSuccess: (data) => setAnswer(data),
    onError: (e) => {
      handleErr(e);
      // 409：模型在閒置時被自動釋放了 → 同步 switch 狀態
      if (e instanceof ApiError && e.status === 409)
        qc.invalidateQueries({ queryKey: ["model-status"] });
    },
  });

  function onAsk(e: FormEvent) {
    e.preventDefault();
    if (!question.trim() || !loaded || askMut.isPending) return;
    askMut.mutate();
  }

  const askErr = askMut.error instanceof ApiError ? askMut.error : null;

  // load/release 的錯誤（401 交給下方 token 區處理，其餘要顯示，否則按鈕像「沒反應」）
  const modelErrRaw = loadMut.error ?? releaseMut.error;
  let modelErrMsg: string | null = null;
  if (modelErrRaw instanceof ApiError) {
    if (modelErrRaw.status === 401) modelErrMsg = null; // token 區會處理
    else if (modelErrRaw.status === 503)
      modelErrMsg = "server 未啟用問答（未設定 ASK_TOKEN，或服務未重啟載入新設定）。";
    else if (modelErrRaw.status === 404)
      modelErrMsg = "server 沒有這個端點——多半是舊版服務還沒重啟。";
    else modelErrMsg = modelErrRaw.message;
  } else if (modelErrRaw) {
    modelErrMsg = "連不上 server（可能未啟動，或缺 RAG 依賴 / GPU）。";
  }

  return (
    <div className="space-y-8">
      <header>
        <p className="eyebrow">圖書館長</p>
        <h1 className="mt-3 font-display text-3xl font-semibold tracking-tight text-ink">
          問問館長
        </h1>
        <p className="mt-3 max-w-xl font-mono text-xs leading-relaxed text-muted">
          茫茫資料庫找不到想要的內容？請館長幫你從對話庫裡整理出來——找不到就說找不到，每則都附上出處。
        </p>
      </header>

      {/* 模型 switch */}
      <div className="flex items-center gap-3 rounded-xl border border-line bg-surface px-4 py-3">
        <span
          className={`inline-flex items-center gap-1.5 font-mono text-xs ${
            loaded ? "text-accent" : "text-faint"
          }`}
        >
          <CircleDot className="h-3.5 w-3.5" />
          {loaded ? `模型已載入 · ${status.data?.device ?? ""}` : "模型未載入"}
        </span>
        <button
          onClick={() => (loaded ? releaseMut.mutate() : loadMut.mutate())}
          disabled={loadMut.isPending || releaseMut.isPending}
          className={`ml-auto inline-flex items-center gap-1.5 rounded-full border px-3.5 py-1.5 font-mono text-xs transition disabled:opacity-50 ${
            loaded
              ? "border-line-strong text-muted hover:border-ink hover:text-ink"
              : "border-ink bg-ink text-paper hover:opacity-90"
          }`}
        >
          {loadMut.isPending || releaseMut.isPending ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Power className="h-3.5 w-3.5" />
          )}
          {loadMut.isPending
            ? "載入中…"
            : releaseMut.isPending
              ? "釋放中…"
              : loaded
                ? "釋放模型"
                : "載入模型"}
        </button>
      </div>

      {modelErrMsg && (
        <div className="rounded-xl border border-line bg-surface px-4 py-3 font-mono text-xs text-muted">
          {modelErrMsg}
        </div>
      )}

      {/* token 設定（沒 token 或收到 401 時顯示）*/}
      {(needToken || !token) && (
        <div className="space-y-2 rounded-xl border border-accent/40 bg-surface px-4 py-3">
          <p className="inline-flex items-center gap-1.5 font-mono text-xs text-muted">
            <KeyRound className="h-3.5 w-3.5" />
            {needToken ? "token 不符或失效，請重新輸入" : "問答需要 token（見 .env 的 ASK_TOKEN）"}
          </p>
          <div className="flex gap-2">
            <input
              type="password"
              value={tokenDraft}
              onChange={(e) => setTokenDraft(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && saveToken()}
              placeholder="貼上 ASK_TOKEN…"
              className="w-full rounded-full border border-line bg-paper px-4 py-2 text-sm text-ink outline-none transition placeholder:text-faint focus:border-accent"
            />
            <button
              onClick={saveToken}
              className="shrink-0 rounded-full border border-ink bg-ink px-4 py-2 font-mono text-xs text-paper transition hover:opacity-90"
            >
              儲存
            </button>
          </div>
        </div>
      )}

      {/* 問句 */}
      <form onSubmit={onAsk} className="space-y-3">
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) onAsk(e);
          }}
          rows={3}
          placeholder={loaded ? "例如：整理我對睡眠和恢復的做法" : "先載入模型，再開始提問"}
          disabled={!loaded}
          className="w-full resize-y rounded-xl border border-line bg-surface px-4 py-3 text-sm leading-relaxed text-ink outline-none transition placeholder:text-faint focus:border-accent disabled:opacity-50"
        />
        <div className="flex items-center gap-3">
          <span className="font-mono text-[0.65rem] text-faint">⌘/Ctrl + Enter 送出</span>
          <button
            type="submit"
            disabled={!loaded || !question.trim() || askMut.isPending}
            className="ml-auto inline-flex items-center gap-1.5 rounded-full border border-ink bg-ink px-5 py-2 font-mono text-xs text-paper transition hover:opacity-90 disabled:opacity-40"
          >
            {askMut.isPending ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Sparkles className="h-3.5 w-3.5" />
            )}
            {askMut.isPending ? "思考中…" : "問"}
          </button>
        </div>
      </form>

      {askErr && askErr.status !== 401 && (
        <div className="rounded-xl border border-line bg-surface px-4 py-3 font-mono text-xs text-muted">
          {askErr.status === 409 ? "模型已被釋放，請重新載入模型再問。" : askErr.message}
        </div>
      )}

      {answer && <Answer data={answer} />}
    </div>
  );
}

function Answer({ data }: { data: AskResponse }) {
  return (
    <section className="space-y-6 border-t border-line pt-8">
      <Markdown>{data.answer}</Markdown>

      {data.sources.length > 0 && (
        <div className="space-y-2">
          <p className="eyebrow">出處 · {data.model}</p>
          <ul className="space-y-1.5">
            {data.sources.map((s) => {
              const meta = platformMeta[s.platform];
              return (
                <li key={s.n}>
                  <Link
                    to={`/c/${encodeURIComponent(s.conv_id)}?m=${s.msg_start}`}
                    className="group flex items-center gap-2.5 rounded-lg border border-line px-3 py-2 font-mono text-xs transition hover:border-accent hover:bg-surface"
                  >
                    <span className="text-faint">[{s.n}]</span>
                    <span style={{ color: meta?.color }}>{meta?.label}</span>
                    <span className="truncate text-ink/80">{s.title || "未命名對話"}</span>
                    <span className="ml-auto shrink-0 text-faint">{fmtDate(s.time)}</span>
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </section>
  );
}

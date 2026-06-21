"""Gemini 對話串本地還原（stitch）。

Gemini 的 Takeout 匯出無 conversation id、無 threading，一個真實對話串被切成
多筆「1 問 1 答」迷你對話。本模組在本地把它們重新串回去：

  中心思想——外部 deterministic 程式負責「選候選 + 組裝」，LLM 只當灰色地帶的
  審判者。framing 不是「判斷任兩段能否合併（clustering，受傳遞性之苦）」，而是
  「每段照時間序找它唯一的前驅，建森林/鏈」：一則訊息只續接唯一一串，傳遞性問題
  消失，且天然產出有序的串。

產出側邊 artifact，完全不動 normalized.jsonl / archive.db / vectors.db：
  - out/threads.json          —— 分組結果（Gemini only）
  - out/thread_decisions.json —— pair-hash → LLM 判斷快取（只快取 LLM，規則每次重算）

冪等 + 增量：fragment id 是內容雜湊故穩定；LLM 只對快取沒有的 pair 呼叫，重跑
結果一致、重新匯出只為新 pair 付費。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time as _time
from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np

from .schema import read_jsonl

# ── 可調參數（靠 eval 調；CLI 可覆蓋部分）───────────────────────────────
W_RECENCY = 12        # 候選：時間上最近的 W 段
S_SEMANTIC = 10       # 候選：embedding 最相似的 S 段
TOP_K = 6             # 每段最終保留的候選數
TAU = 6 * 3600.0      # 時間鄰近度指數衰減常數（秒）
W_SIM = 1.0           # 排名權重：語意相似度
W_TIME = 0.5          # 排名權重：時間鄰近度
SIM_HI = 0.75         # 高信心自動接門檻
SIM_MED = 0.60        # 有回指時的自動接門檻
SIM_LO = 0.45         # 低於此且無回指 → 自動拒
SHORT_GAP = 1800.0    # 「同一坐席」的時間差（秒）
ASSIST_TRUNC = 600    # 餵 embedding / LLM 的 assistant 截斷字數

# 回指 / 續問的 lexical 訊號：命中代表「這段在續接某串」（提高判斷傾向）。
# 為可調 heuristic，非硬規則。
_ANAPHORA_SUBSTR = (
    "剛剛", "剛才", "你剛", "妳剛", "你之前", "之前說", "之前提", "如上", "上面",
    "前面", "上述", "同上", "接續", "繼續", "延續", "你說的", "你提到", "你訴說",
    "再給", "再寫", "再列", "再說", "換成", "改成",
)
_ANAPHORA_PREFIX = ("那", "這", "它", "他", "她", "所以", "然後", "接著", "那麼", "再")
_SHORT_PROMPT_CHARS = 12  # 極短 prompt 多半無法獨立成立 → 視為續問訊號


@dataclass
class Fragment:
    id: str
    user_text: str
    assistant_text: str
    time: float


def load_fragments(jsonl_path: str) -> list[Fragment]:
    """讀 Gemini fragment，依時間升冪。"""
    frags: list[Fragment] = []
    for c in read_jsonl(jsonl_path):
        if c.platform != "gemini":
            continue
        user = next((m.text for m in c.messages if m.role == "user"), "") or ""
        asst = next((m.text for m in c.messages if m.role == "assistant"), "") or ""
        frags.append(Fragment(id=c.id, user_text=user, assistant_text=asst,
                              time=c.create_time or 0.0))
    frags.sort(key=lambda f: f.time)
    return frags


def _repr_text(f: Fragment) -> str:
    """embedding 用的代表文字：user prompt + 截斷的 assistant 尾段（補主題訊號）。"""
    asst = f.assistant_text.strip()
    if len(asst) > ASSIST_TRUNC:
        asst = asst[:ASSIST_TRUNC]
    return f"{f.user_text}\n{asst}".strip()


def has_anaphora(text: str) -> bool:
    t = text.strip()
    if not t:
        return False
    if len(t) <= _SHORT_PROMPT_CHARS:
        return True
    if any(s in t for s in _ANAPHORA_SUBSTR):
        return True
    if t.startswith(_ANAPHORA_PREFIX):
        return True
    return False


def _pair_key(prev_id: str, cur_id: str) -> str:
    return hashlib.sha1(f"{prev_id}\n{cur_id}".encode("utf-8")).hexdigest()


# ── 候選前驅生成 ─────────────────────────────────────────────────────────
def _candidates(i: int, emb: np.ndarray, frags: list[Fragment],
                window: int, s_semantic: int, top_k: int) -> list[tuple[int, float, float]]:
    """回傳 fragment i 的候選前驅 [(j, sim, combined_score)]，combined 由高到低。"""
    if i == 0:
        return []
    sims = emb[:i] @ emb[i]  # cos（已 normalize）
    cand_idx = set(range(max(0, i - window), i))
    if s_semantic > 0 and i > 0:
        topk = np.argsort(-sims)[:s_semantic]
        cand_idx.update(int(j) for j in topk)
    scored = []
    for j in cand_idx:
        sim = float(sims[j])
        gap = max(0.0, frags[i].time - frags[j].time)
        proximity = float(np.exp(-gap / TAU))
        combined = W_SIM * sim + W_TIME * proximity
        scored.append((j, sim, combined))
    scored.sort(key=lambda x: x[2], reverse=True)
    return scored[:top_k]


# ── LLM 審判（灰色地帶才呼叫）────────────────────────────────────────────
_JUDGE_SYSTEM = """你是「對話串連續性」的審判者。給你兩段來自同一使用者、與 AI 的\
問答片段：A 在前、B 在後（時間較晚）。判斷 B 是否「直接續接 A 所在的同一條對話串」\
——即 B 是順著 A 的脈絡/主題繼續問或追問，而非另起一個新話題。

只輸出 JSON，不要多餘文字：{"continues": true/false, "confidence": 0~1, "reason": "簡短理由"}"""


def _judge_prompt(prev: Fragment, cur: Fragment) -> str:
    pa = prev.assistant_text.strip()
    if len(pa) > ASSIST_TRUNC:
        pa = pa[:ASSIST_TRUNC] + "…"
    return (
        f"【A（前）】\n使用者問：{prev.user_text}\nAI 答（摘錄）：{pa}\n\n"
        f"【B（後）】\n使用者問：{cur.user_text}\n\n"
        f"B 是否直接續接 A 的同一條對話串？"
    )


def _parse_judge(raw: str) -> dict:
    """從 LLM 回覆抽 JSON；失敗時退回字串啟發式。"""
    s = raw.strip()
    m = re.search(r"\{.*\}", s, re.DOTALL)
    if m:
        try:
            d = json.loads(m.group(0))
            return {"continues": bool(d.get("continues")),
                    "confidence": float(d.get("confidence", 0.0) or 0.0),
                    "reason": str(d.get("reason", ""))}
        except Exception:
            pass
    cont = ("true" in s.lower()) or ("續接" in s and "不" not in s[:s.find("續接")] if "續接" in s else False)
    return {"continues": cont, "confidence": 0.0, "reason": "parse-fallback"}


def _llm_judge(prev: Fragment, cur: Fragment, model: str,
               timeout: float = 45.0) -> dict:
    from . import rag  # 延後 import，避免 report/eval 時拖 openai
    try:
        raw = rag.complete(
            [
                {"role": "system", "content": _JUDGE_SYSTEM},
                {"role": "user", "content": _judge_prompt(prev, cur)},
            ],
            model=model, max_tokens=512, temperature=0.0,
            timeout=timeout, max_retries=1,
        )
    except Exception as e:  # 逾時/網路錯 → 不接、且不寫快取（下次重判）
        return {"continues": False, "confidence": 0.0,
                "reason": f"error: {type(e).__name__}", "_error": True}
    return _parse_judge(raw)


GAP_MIN_DEFAULT = 60.0  # session 切割：相鄰 gap 超過此分鐘數 → 新 session
# 60 分為使用者選定的「寧漏不過」門檻：零過併（不把不同主題黏一起、不污染檢索），
# 代價是偶爾把中間停頓 60–75 分的同一次坐席切成兩段。見 PLAN.local.md 門檻掃描。


def build_timegap(out_dir: str = "out", gap_min: float = GAP_MIN_DEFAULT) -> dict:
    """時間 gap 法（deterministic、零 LLM）：相鄰 fragment gap > gap_min 分鐘
    就切新 session。忠於「一次坐下來連續聊的 = 一串」。"""
    jsonl = os.path.join(out_dir, "normalized.jsonl")
    if not os.path.exists(jsonl):
        raise SystemExit(f"找不到 {jsonl}；請先執行 ingest")
    frags = load_fragments(jsonl)
    n = len(frags)
    if n == 0:
        raise SystemExit("沒有 Gemini fragment 可串接")
    gap_sec = gap_min * 60.0
    parent = [-1] * n
    for i in range(1, n):
        if frags[i].time - frags[i - 1].time <= gap_sec:
            parent[i] = i - 1
    threads = _assemble(parent, frags)
    result = _write_threads(out_dir, threads, frags, model=f"timegap:{gap_min}min",
                            params={"method": "timegap", "gap_min": gap_min})
    result["n_fragments"] = n
    result["stats"] = {"method": "timegap", "gap_min": gap_min}
    return result


# ── 主流程：建串 ─────────────────────────────────────────────────────────
def build(out_dir: str = "out", model: str | None = None,
          window: int = W_RECENCY, s_semantic: int = S_SEMANTIC, top_k: int = TOP_K,
          sim_hi: float = SIM_HI, sim_med: float = SIM_MED, sim_lo: float = SIM_LO,
          verbose: bool = True) -> dict:
    """(重)建 Gemini 對話串 → out/threads.json（+ 更新 thread_decisions.json）。"""
    from .rag import DEFAULT_MODEL
    model = model or DEFAULT_MODEL
    jsonl = os.path.join(out_dir, "normalized.jsonl")
    if not os.path.exists(jsonl):
        raise SystemExit(f"找不到 {jsonl}；請先執行 ingest")
    frags = load_fragments(jsonl)
    n = len(frags)
    if n == 0:
        raise SystemExit("沒有 Gemini fragment 可串接")

    cache_path = os.path.join(out_dir, "thread_decisions.json")
    cache = _load_cache(cache_path)

    # 本地向量化（reuse Embedder）；用 fragment id 列表雜湊當快取 key，
    # 內容不變就不重算（門檻調校迴圈免每次等 3 分）。
    emb = _embed_fragments(frags, out_dir, verbose)

    parent: list[int] = [-1] * n      # 每段的前驅 fragment index（-1 = 串首）
    stats = {"rule_link": 0, "rule_new": 0, "llm_calls": 0,
             "llm_link": 0, "llm_new": 0, "cache_hits": 0}

    for i in range(n):
        cands = _candidates(i, emb, frags, window, s_semantic, top_k)
        if not cands:
            stats["rule_new"] += 1
            continue
        j, sim, _ = cands[0]
        anaph = has_anaphora(frags[i].user_text)
        gap = max(0.0, frags[i].time - frags[j].time)

        if (sim >= sim_hi and gap <= SHORT_GAP) or (anaph and sim >= sim_med):
            parent[i] = j
            stats["rule_link"] += 1
        elif sim < sim_lo and not anaph:
            stats["rule_new"] += 1
        else:
            # 灰色地帶 → LLM（先查快取）
            key = _pair_key(frags[j].id, frags[i].id)
            if key in cache:
                d = cache[key]
                stats["cache_hits"] += 1
            else:
                d = _llm_judge(frags[j], frags[i], model)
                stats["llm_calls"] += 1
                if not d.get("_error"):
                    cache[key] = d
                    _save_cache(cache_path, cache)  # 即時 flush：可續跑、被砍不丟
                else:
                    stats["llm_errors"] = stats.get("llm_errors", 0) + 1
                if verbose and stats["llm_calls"] % 20 == 0:
                    print(f"    …LLM 判斷 {stats['llm_calls']} 次"
                          f"（錯 {stats.get('llm_errors', 0)}）", flush=True)
            if d.get("continues"):
                parent[i] = j
                stats["llm_link"] += 1
            else:
                stats["llm_new"] += 1

    _save_cache(cache_path, cache)
    threads = _assemble(parent, frags)
    result = _write_threads(out_dir, threads, frags, model,
                            {"window": window, "s_semantic": s_semantic,
                             "top_k": top_k, "sim_hi": sim_hi, "sim_med": sim_med,
                             "sim_lo": sim_lo})
    result["stats"] = stats
    result["n_fragments"] = n
    return result


def _embed_fragments(frags: list[Fragment], out_dir: str, verbose: bool) -> np.ndarray:
    """向量化 fragment 代表文字；fragment id 列表不變就讀快取（out/thread_embeddings.npz）。"""
    sig = hashlib.sha1("\n".join(f.id for f in frags).encode("utf-8")).hexdigest()
    cache_path = os.path.join(out_dir, "thread_embeddings.npz")
    if os.path.exists(cache_path):
        try:
            z = np.load(cache_path, allow_pickle=False)
            if str(z["sig"]) == sig:
                if verbose:
                    print(f"  讀 embedding 快取（{len(frags)} 段，跳過向量化）")
                return z["emb"]
        except Exception:
            pass
    from .embed import Embedder
    embedder = Embedder()
    if verbose:
        print(f"  向量化 {len(frags)} 段 Gemini fragment（device: {embedder.device_str}）…")
    emb = embedder.encode([_repr_text(f) for f in frags], show_progress=verbose)
    np.savez(cache_path, emb=emb, sig=np.array(sig))
    return emb


def _assemble(parent: list[int], frags: list[Fragment]) -> list[list[int]]:
    """依 parent 連結組裝有序的串（每串為 fragment index 的時間序 list）。"""
    children: dict[int, list[int]] = {}
    roots: list[int] = []
    for i, p in enumerate(parent):
        if p < 0:
            roots.append(i)
        else:
            children.setdefault(p, []).append(i)
    threads: list[list[int]] = []
    for r in roots:
        chain = [r]
        stack = list(children.get(r, []))
        # 一段可能被多段選為前驅（分叉）；全部收進同一串，最後依時間排序
        while stack:
            node = stack.pop()
            chain.append(node)
            stack.extend(children.get(node, []))
        chain.sort(key=lambda idx: frags[idx].time)
        threads.append(chain)
    threads.sort(key=lambda ch: frags[ch[0]].time)
    return threads


def _write_threads(out_dir: str, threads: list[list[int]], frags: list[Fragment],
                   model: str, params: dict) -> dict:
    thread_objs = []
    frag_to_thread: dict[str, str] = {}
    for chain in threads:
        head = frags[chain[0]]
        tid = "gthread:" + head.id.split(":", 1)[-1]
        ids = [frags[k].id for k in chain]
        times = [frags[k].time for k in chain]
        thread_objs.append({
            "thread_id": tid,
            "fragment_ids": ids,
            "title": (head.user_text or "").replace("\n", " ")[:60],
            "create_time": min(times), "update_time": max(times),
            "n_fragments": len(ids),
        })
        for fid in ids:
            frag_to_thread[fid] = tid
    payload = {
        "built_at": int(_time.time()), "model": model, "params": params,
        "n_threads": len(thread_objs), "n_fragments": len(frags),
        "threads": thread_objs, "fragment_to_thread": frag_to_thread,
    }
    path = os.path.join(out_dir, "threads.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return {"path": path, "n_threads": len(thread_objs)}


def _load_cache(path: str) -> dict:
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_cache(path: str, cache: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def load_threads(out_dir: str = "out") -> dict:
    path = os.path.join(out_dir, "threads.json")
    if not os.path.exists(path):
        raise SystemExit(f"找不到 {path}；請先執行 `stitch`")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ── 驗證工具 ─────────────────────────────────────────────────────────────
def _fmt(t: float) -> str:
    if not t:
        return "----------------"
    return datetime.fromtimestamp(t, tz=timezone.utc).astimezone().strftime(
        "%Y-%m-%d %H:%M")


def report(out_dir: str = "out") -> str:
    """人讀提案：每條串的標題 + 時間範圍 + 串內各段 user prompt（時間序）。"""
    data = load_threads(out_dir)
    frags = {f.id: f for f in load_fragments(os.path.join(out_dir, "normalized.jsonl"))}
    lines: list[str] = []
    threads = sorted(data["threads"], key=lambda t: -t["n_fragments"])
    multi = sum(1 for t in threads if t["n_fragments"] > 1)
    lines.append(f"# {data['n_fragments']} fragment → {data['n_threads']} 串"
                 f"（其中 {multi} 串含 ≥2 段）\n")
    for t in threads:
        lines.append(f"━━ [{t['n_fragments']}] {t['title']}  "
                     f"（{_fmt(t['create_time'])} ~ {_fmt(t['update_time'])}）")
        for fid in t["fragment_ids"]:
            f = frags.get(fid)
            if not f:
                continue
            q = f.user_text.replace("\n", " ")
            if len(q) > 70:
                q = q[:70] + "…"
            lines.append(f"    · {_fmt(f.time)}  {q}")
        lines.append("")
    return "\n".join(lines)


def slice_fragments(out_dir: str, since: float | None,
                    until: float | None) -> list[Fragment]:
    frags = load_fragments(os.path.join(out_dir, "normalized.jsonl"))
    return [f for f in frags
            if (since is None or f.time >= since) and (until is None or f.time < until)]


def dump_slice(out_dir: str, since: float | None, until: float | None) -> str:
    """印出時間切片內的 fragment（帶序號），供人工標注 gold。"""
    frags = slice_fragments(out_dir, since, until)
    lines = [f"# {len(frags)} fragment（序號 = 時間序；標 gold 時每行列同一串的序號）"]
    for n, f in enumerate(frags):
        q = f.user_text.replace("\n", " ")
        if len(q) > 80:
            q = q[:80] + "…"
        lines.append(f"{n:4d}  {_fmt(f.time)}  {q}")
    return "\n".join(lines)


def _parse_gold(path: str) -> list[list[int]]:
    """gold 檔：每行一串，列該串成員的序號（空白/逗號分隔）；# 開頭為註解。"""
    groups: list[list[int]] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            nums = [int(x) for x in re.split(r"[\s,]+", line) if x.strip()]
            if nums:
                groups.append(nums)
    return groups


def evaluate(out_dir: str, gold_path: str, since: float | None,
             until: float | None) -> dict:
    """以手標 gold（同一切片 since/until）算連結 pairwise precision/recall。"""
    frags = slice_fragments(out_dir, since, until)
    seq_to_id = {n: f.id for n, f in enumerate(frags)}
    gold_groups = _parse_gold(gold_path)
    # gold：序號 → 群編號
    gold_label: dict[str, int] = {}
    labeled_seqs: set[int] = set()
    for gi, grp in enumerate(gold_groups):
        for s in grp:
            if s in seq_to_id:
                gold_label[seq_to_id[s]] = gi
                labeled_seqs.add(s)
    # 預測：fragment id → thread id（限制在已標注的 fragment）
    pred = load_threads(out_dir)["fragment_to_thread"]
    ids = [seq_to_id[s] for s in sorted(labeled_seqs)]
    # 所有 pair 的 same/diff 比對
    tp = fp = fn = tn = 0
    for a in range(len(ids)):
        for b in range(a + 1, len(ids)):
            ia, ib = ids[a], ids[b]
            gold_same = gold_label[ia] == gold_label[ib]
            pred_same = pred.get(ia) is not None and pred.get(ia) == pred.get(ib)
            if pred_same and gold_same:
                tp += 1
            elif pred_same and not gold_same:
                fp += 1  # 過併
            elif not pred_same and gold_same:
                fn += 1  # 漏併
            else:
                tn += 1
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {"n_labeled": len(ids), "n_gold_threads": len(gold_groups),
            "precision": precision, "recall": recall, "f1": f1,
            "over_merge_pairs": fp, "under_merge_pairs": fn,
            "tp": tp, "tn": tn}

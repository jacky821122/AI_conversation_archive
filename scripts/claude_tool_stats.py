"""One-shot analysis of Claude Code tool-call behaviour (read-only, stdlib only).

The archive's Claude parser is prose-only by design — it drops thinking /
tool_use / tool_result. That is the right call for a human-facing cross-platform
archive, but it means tool-level behaviour is invisible to `search` / `ask`.
This script reads the same source files directly and reports on the layer the
archive throws away. It writes nothing and touches no archive artefact.

Run from the repo root:
    PYTHONPATH=. python scripts/claude_tool_stats.py
    PYTHONPATH=. python scripts/claude_tool_stats.py --json > out/tool_stats.json
    PYTHONPATH=. python scripts/claude_tool_stats.py --project <substring>

Source root follows the parser: CLAUDE_PROJECTS, else ~/.claude/projects.
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import re

from ai_archive.parsers import claude
from ai_archive.parsers._util import iso_to_epoch

# ---------------------------------------------------------------- error taxonomy

# 判別順序有意義：先撈掉「不是 agent 犯的錯」，剩下的才是可檢討的行為。
# (category, human_attributable?, predicate)
_RULES: list[tuple[str, bool, "callable"]] = [
    ("user-denied", False,
     lambda t: t.startswith("Permission to use")
     or "doesn't want to proceed" in t
     or "user doesn't want to take this action" in t
     # 被 permission settings 擋下＝設定邊界，與 user 按拒絕同性質，非 agent 判斷錯
     or "denied by your permission settings" in t),
    ("interrupted", False,
     lambda t: "Request interrupted" in t or "aborted" in t.lower()),
    ("timeout", False,
     lambda t: "Command timed out" in t or "Exit code 143" in t),
    ("read-before-edit", True,
     lambda t: "has not been read yet" in t),
    ("stale-edit-target", True,
     lambda t: "String to replace not found" in t
     or "Found 0 matches" in t
     or "has not been modified" in t),
    ("bad-path", True,
     lambda t: "File does not exist" in t
     or "no such file or directory" in t.lower()
     or "ENOENT" in t),
    ("out-of-scope-dir", True,
     lambda t: "not in the list of directories" in t
     or "directory that is not" in t),
    ("bad-params", True,
     lambda t: "Invalid" in t or "InputValidationError" in t
     or "required" in t.lower() and "parameter" in t.lower()),
    # invocation 本身寫壞（引號沒收、shell 解析失敗、pathspec 打錯）＝真的是 agent 的錯
    ("bad-invocation", True,
     lambda t: "parse error" in t
     or "unmatched" in t
     or "did not match any files" in t
     or "command not found" in t
     or "unexpected argument" in t
     or "invalid option" in t.lower()),
    # 非零 exit code 是「那個指令的判決」（測試紅了、憑證錯、機台掛了），不是 agent 判斷錯。
    # 之前把整包算成 agent 的錯，讓可歸咎比例從 ~35% 灌水到 61%。
    ("command-failed", False,
     lambda t: t.startswith("Exit code") or "Traceback (most recent call last)" in t),
]


def classify(text: str) -> tuple[str, bool]:
    for name, blame, pred in _RULES:
        try:
            if pred(text):
                return name, blame
        except Exception:  # 規則寫壞不該中斷整份報告
            continue
    return "other", True


_SUBS = [
    (re.compile(r"<[^>]{1,40}>"), ""),            # <tool_use_error> 之類的包裝
    (re.compile(r"/\S+"), "<path>"),
    (re.compile(r"\b[0-9a-f]{7,40}\b"), "<hash>"),
    (re.compile(r"\b\d+\b"), "<n>"),
    (re.compile(r"\s+"), " "),
]


def template(text: str) -> str:
    """把路徑/行號/hash 抽掉，讓同型錯誤收斂成同一個 template。"""
    t = text
    for pat, rep in _SUBS:
        t = pat.sub(rep, t)
    return t.strip()[:90]


# ---------------------------------------------------------------- extraction

def _blocks(rec):
    msg = rec.get("message")
    if not isinstance(msg, dict):
        return []
    content = msg.get("content")
    return [b for b in content if isinstance(b, dict)] if isinstance(content, list) else []


def _result_text(block) -> str:
    c = block.get("content")
    if isinstance(c, list):
        c = " ".join(x.get("text", "") for x in c if isinstance(x, dict))
    return (c or "") if isinstance(c, str) else ""


def scan(paths: list[str]) -> dict:
    calls: list[dict] = []       # 每個 tool_use 一筆，補上結果
    sessions = 0

    for path in paths:
        sessions += 1
        session = os.path.splitext(os.path.basename(path))[0]
        project = os.path.basename(os.path.dirname(path))
        pending: dict[str, dict] = {}   # tool_use_id -> call
        order: list[dict] = []

        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("type") not in ("user", "assistant"):
                    continue
                ts = iso_to_epoch(rec.get("timestamp") or "")
                for b in _blocks(rec):
                    kind = b.get("type")
                    if kind == "tool_use":
                        call = {
                            "session": session,
                            "project": project,
                            "cwd": rec.get("cwd") or "",
                            "tool": b.get("name") or "?",
                            "input_digest": json.dumps(
                                b.get("input"), sort_keys=True, ensure_ascii=False
                            )[:400],
                            # digest 會被截斷導致無法 json.loads，根因分析要靠這兩個
                            # 獨立欄位，別從 digest 反解。
                            "target": (b.get("input") or {}).get("file_path")
                            or (b.get("input") or {}).get("path") or "",
                            "param_keys": sorted((b.get("input") or {}).keys())
                            if isinstance(b.get("input"), dict) else [],
                            "time": ts,
                            "ok": None,
                            "category": None,
                            "blame": None,
                            "template": None,
                            "duration": None,
                        }
                        pending[b.get("id") or ""] = call
                        order.append(call)
                    elif kind == "tool_result":
                        call = pending.pop(b.get("tool_use_id") or "", None)
                        if call is None:
                            continue
                        err = bool(b.get("is_error"))
                        call["ok"] = not err
                        if call["time"] and ts:
                            call["duration"] = round(ts - call["time"], 2)
                        if err:
                            txt = _result_text(b)
                            cat, blame = classify(re.sub(r"<[^>]{1,40}>", "", txt).strip())
                            call["category"] = cat
                            call["blame"] = blame
                            call["template"] = template(txt)
        calls.extend(order)

    return {"sessions": sessions, "calls": calls}


def incidents(calls: list[dict]) -> list[dict]:
    """Retry chain 去重：同一 session 內、同 tool + 同 input 的連續失敗算 1 次。

    不去重的話「重試 3 次」會被記成 3 個獨立錯誤，把真實錯誤率灌水。
    """
    seen: set[tuple] = set()
    out = []
    for c in calls:
        if c["ok"] is not False:
            continue
        key = (c["session"], c["tool"], c["input_digest"], c["category"])
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


# ---------------------------------------------------------------- report

def _bar(n: int, total: int, width: int = 28) -> str:
    filled = int(round(width * n / total)) if total else 0
    return "█" * filled + "·" * (width - filled)


def report(data: dict) -> None:
    calls = data["calls"]
    done = [c for c in calls if c["ok"] is not None]
    errs = [c for c in calls if c["ok"] is False]
    inc = incidents(calls)
    mine = [c for c in inc if c["blame"]]

    print(f"sessions            {data['sessions']}")
    print(f"tool calls          {len(calls)}  (有結果 {len(done)}，未配對 {len(calls) - len(done)})")
    print(f"raw errors          {len(errs)}")
    print(f"incidents (去重後)   {len(inc)}   ← retry chain 折疊掉 {len(errs) - len(inc)} 筆")
    print(f"可歸咎 agent 的      {len(mine)}   ({len(mine) / len(inc) * 100:.0f}% of incidents)"
          if inc else "")

    print("\n── 錯誤分類（incident 基準）" + "─" * 40)
    cat = collections.Counter((c["category"], c["blame"]) for c in inc)
    for (name, blame), n in cat.most_common():
        tag = "agent" if blame else "環境/人"
        print(f"  {n:4}  {_bar(n, len(inc))}  {name:18} [{tag}]")

    print("\n── 可歸咎 agent 的錯誤：代表性 template " + "─" * 20)
    by_cat = collections.defaultdict(collections.Counter)
    for c in mine:
        by_cat[c["category"]][c["template"]] += 1
    for name, _ in collections.Counter(c["category"] for c in mine).most_common():
        print(f"\n  [{name}]")
        for tpl, n in by_cat[name].most_common(3):
            print(f"    {n:3}× {tpl}")

    print("\n── 每個 tool 的失敗率（incident / 呼叫數）" + "─" * 18)
    per = collections.Counter(c["tool"] for c in calls)
    bad = collections.Counter(c["tool"] for c in mine)
    rows = [(t, per[t], bad[t], bad[t] / per[t] * 100) for t in per if per[t] >= 20]
    for t, tot, b, rate in sorted(rows, key=lambda r: -r[3])[:12]:
        print(f"  {t:34} {tot:6}  err {b:4}  {rate:5.1f}%")

    print("\n── 跨專案分佈（archive.db 沒有這個維度）" + "─" * 18)
    proj_calls = collections.Counter(c["project"] for c in calls)
    proj_bad = collections.Counter(c["project"] for c in mine)
    for p, n in proj_calls.most_common(10):
        rate = proj_bad[p] / n * 100 if n else 0
        print(f"  {p[:44]:44} {n:6}  err {proj_bad[p]:4}  {rate:4.1f}%")

    print("\n── 行為指標 " + "─" * 46)
    edits = per.get("Edit", 0) + per.get("Write", 0) + per.get("NotebookEdit", 0)
    reads = per.get("Read", 0)
    rbe = sum(1 for c in mine if c["category"] == "read-before-edit")
    print(f"  Read {reads} / 寫入類 {edits}  → 比值 {reads / edits:.2f}" if edits else "")
    print(f"  read-before-edit 違規 {rbe} 次，佔寫入類呼叫 {rbe / edits * 100:.2f}%" if edits else "")
    slow = [c["duration"] for c in done if c["duration"]]
    if slow:
        slow.sort()
        print(f"  tool 回應時間 median {slow[len(slow) // 2]:.1f}s，p95 {slow[int(len(slow) * .95)]:.1f}s")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--project", help="只看 project 目錄名含此字串的 session")
    ap.add_argument("--json", action="store_true", help="輸出彙總 JSON 而非報表")
    args = ap.parse_args()

    paths = claude.discover("")
    if args.project:
        paths = [p for p in paths if args.project in os.path.basename(os.path.dirname(p))]
    if not paths:
        raise SystemExit("找不到任何 session（檢查 CLAUDE_PROJECTS / --project）")

    data = scan(paths)
    if args.json:
        inc = incidents(data["calls"])
        print(json.dumps({
            "sessions": data["sessions"],
            "calls": len(data["calls"]),
            "incidents": len(inc),
            "by_category": collections.Counter(c["category"] for c in inc),
            "by_tool": collections.Counter(c["tool"] for c in data["calls"]),
            "by_project_err": collections.Counter(
                c["project"] for c in inc if c["blame"]),
        }, ensure_ascii=False, indent=2))
    else:
        report(data)


if __name__ == "__main__":
    main()

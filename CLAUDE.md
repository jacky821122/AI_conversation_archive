# AI Conversation Archive — AI Collaboration Guidelines

Export your personal ChatGPT / Grok / Gemini / Claude Code conversations and turn them into a searchable, queryable corpus and second brain.

## Role and authority order of the context files

**Authority order (high -> low)**: explicit decisions in the current conversation　>　`CLAUDE.md` / `CLAUDE.local.md` (hard rules)　>
`PLAN.local.md` / `ARCHITECTURE.md` (historical encyclopedia).

- **The hard rules are this file (CLAUDE.md), plus the peer-level `CLAUDE.local.md` (if present)**: at the start of every task, check
  whether the project root has a `CLAUDE.local.md`; if so, **its authority equals this file's — follow it as a rule too**.
- **`PLAN.local.md` / `ARCHITECTURE.md` are a historical encyclopedia, not scripture**: they record "the truth as of when they were last written".
  The user often implements a series of changes and only updates the docs afterward, so these two **may lag behind the code and the current conversation**. Treat them as
  reference, open to question; when they conflict with the code or the current conversation, **defer to the present state, and remind the user the doc may be stale**. Do not
  conclude something doesn't exist just because "the doc doesn't mention it", and do not use an old decision in them to overturn a new decision just established in the conversation.
- **Read on demand, not by force every time** (PLAN keeps growing fatter; force-reading it for trivial tasks just injects noise and burns tokens):
  - Need project context / decision history (discussing direction, design, implementing non-trivial features) -> consult `PLAN.local.md`.
  - Need architectural rationale (touching data flow, schema, cross-module design) -> consult `ARCHITECTURE.md`.
  - Trivial / local tasks (renaming variables, fixing typos, small single-file edits, pure Q&A) -> neither is needed.
  - Updating one of these files -> read that file first, of course.
- When `PLAN.local.md` is absent (a clone on another machine) -> carry on from git log + `ARCHITECTURE.md`, and remind the user.

## Division of labor across documents (match the right file when editing docs)

- **`README.md`** — purely a user manual (environment setup, commands, how to run). Manual info goes up top, visible at a glance; no design rationale.
- **`ARCHITECTURE.md`** — non-sensitive architecture and design rationale (program structure, data flow, schema, the "why" of each design). Goes into git.
- **`PLAN.local.md`** — local development plan, containing personal notes / possibly sensitive content, planned work, decision history. **Not in git**.
- **`CLAUDE.md`** (this file) — collaboration guidelines and a summary of conventions not obvious from the code. Goes into git (public).
- **`CLAUDE.local.md`** — machine-specific collaboration guidelines. When present, its authority equals `CLAUDE.md`'s. **Not in git**.

> The architecture tree, data flow, and the details of each platform and design rationale are all in `ARCHITECTURE.md`; commands and setup are in `README.md`.
> This file keeps only "guidelines to remember while collaborating" and does not duplicate that content.

## Conventions and boundaries (not directly obvious from the code)

- **Privacy boundary (top principle)**: indexing / vectorization / retrieval all happen locally, with zero external calls; only the final "retrieved fragments" of RAG
  are sent to the generation endpoint. `data/`, `out/`, `.env`, `PLAN.local.md` are all gitignored. The GitHub repo is
  **public, code only**. Before changing anything, confirm it won't push private data or sensitive context to the public repo.
- **Dependency layering**: the foundation is pure stdlib (ingest/search/stats, zero install); web uses `requirements-web.txt`;
  RAG uses `requirements-rag.txt`. When touching the foundation layer, basically do not introduce third-party dependencies; if truly needed, ask the user.
- **Swappable generation endpoint**: RAG goes through an OpenAI-compatible interface, all configured in `.env`. Switching model / provider = edit `.env`, no code change.
- **Adding a platform = data-driven downstream**: do not hardcode platforms downstream (store/index/rag/web). For the actual steps see
  the "Adding a platform" section in `ARCHITECTURE.md`.
- **Responsive Web UI (RWD)**: any Web UI change must consider both the mobile (iOS-first) and desktop layouts' presentation and
  interaction, and both must be verified — don't attend to only one form factor.
- **Gemini overlay is on the consumer side**: `normalized.jsonl` always preserves the raw fragment (never rewritten); `ingest`/`index`
  apply the `threads.json` overlay only at consumption time. Do not write the overlay back into the source file.
- **Idempotency**: rerunning `ingest` / `index` / `stitch` must overwrite the output and produce identical results. Keep these commands idempotent when changing them.
- **When you need to consult the corpus yourself**: list / fetch full text via `ai_archive list` / `get` (add `--json` for you to parse),
  keyword via `search`, semantic via `search-dense` — all of the above are local with zero external calls; only `ask` (RAG) sends fragments to the generation endpoint,
  treat it as an outbound transmission and confirm before running. For field / JSON contracts see the "read-only read contract" section in `ARCHITECTURE.md`.

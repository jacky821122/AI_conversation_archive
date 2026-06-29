# Repo Review Findings

This file records the issues found during the June 2026 repo review and the
acceptance criteria for each fix. Each numbered item should be implemented and
committed independently after design review and verification.

## 1. RAG model config from `.env` can be ignored

`ai_archive.rag.DEFAULT_MODEL` is resolved at module import time, before
`complete()` loads `.env`. CLI paths such as `ask` and semantic `stitch` may use
the hard-coded fallback model when `AGNES_MODEL` exists only in `.env`.

Acceptance criteria:
- Runtime model resolution honors `.env` without requiring shell-exported env.
- CLI `ask` and semantic `stitch` keep their documented defaults.
- Existing provider override behavior remains intact.
- Add or update a focused regression test if practical.

## 2. API ask/load/release model lifecycle is not fully serialized

`api.py` declares `_model_lock` and documents that load, release, and ask should
be serialized, but `/api/ask` does not hold the lock while using the shared
embedder. A manual release or idle release could overlap with encoding.

Acceptance criteria:
- `/api/ask` cannot race with model release while it is using `_embedder`.
- Existing 409 behavior for unloaded models remains.
- The lock scope avoids unnecessary blocking around external generation where
  possible.
- Add or update a focused regression test if practical.

## 3. RAG system prompt omits Claude

The RAG system prompt names ChatGPT, Grok, and Gemini but the archive now also
supports Claude Code. This is a correctness/documentation drift in the prompt.

Acceptance criteria:
- RAG prompt accurately names the supported source platforms.
- No behavior change outside the prompt text unless needed by item 1.

## 4. Grok parser treats unknown senders as assistant

`grok.py` maps any sender other than `human` to `assistant`. If the export gains
system/tool/metadata sender types, those records would pollute the corpus.

Acceptance criteria:
- Only known user and assistant sender values are ingested.
- Unknown sender values are skipped conservatively.
- Add a parser regression covering unknown sender behavior.

## 5. Frontend main bundle is large

The production build succeeds but Vite warns that the main JS chunk is over
500 kB after minification. Markdown, KaTeX, charting, and route code are likely
loaded eagerly.

Acceptance criteria:
- Apply conservative route-level or component-level code splitting.
- `npm run build` succeeds.
- The main app chunk is smaller or the warning is resolved/reduced.
- User-facing routes continue to resolve through the existing router.

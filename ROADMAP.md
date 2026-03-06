# ROADMAP.md — word-translator

This document tracks the development direction of `word-translator`. Items are grouped by horizon and priority. The roadmap is updated as work is completed or priorities shift.

---

## Status Key

| Symbol | Meaning |
|--------|---------|
| ✅ | Completed |
| 🔄 | In progress |
| 📋 | Planned |
| 💡 | Under consideration |

---

## Completed Work

### Bug Fixes (resolved 2026-03-05)

| ID | Fix | Commit |
|----|-----|--------|
| BUG-1 | Replace Windows-only `rmdir /s /q` with `shutil.rmtree` — temp dirs now cleaned up correctly on Linux/macOS | `8b90305` → current |
| BUG-2 | Long paragraphs (> 900 chars) are now chunked on whitespace boundaries before buffering, preventing oversized Sarvam API requests | same |
| BUG-3 | A `WARNING` log message is emitted when the Sarvam API returns a different number of lines than were submitted | same |
| BUG-4 | SarvamAI client instantiation moved inside `translate_doc()` via optional `client` parameter (dependency injection); module is now importable without a real API key | same |

### Documentation (completed 2026-03-05)

- `CLAUDE.md` — AI assistant guide covering structure, setup, API reference, implementation details, conventions, and known issues
- `LEARNINGS.md` — design decisions, discovered bugs, observations, and recommended next steps
- `SPEC.md` — authoritative technical specification of API contract, translation algorithm, file handling, and non-functional requirements
- `ROADMAP.md` — this file

### Testing (completed 2026-03-05)

- `tests/test_translate_doc.py` — 12 unit tests covering batching logic, chunking, logging, and dependency injection
- `tests/test_app.py` — 11 integration tests covering happy path, validation (422), error propagation (500), CORS allow/deny
- `pytest.ini` — pytest configuration pointing to `tests/`
- `pytest` and `httpx` added to `requirements.txt`

---

## Short-Term (next sprint)

### High Priority

- 📋 **Pin dependency versions** — Run `pip freeze` against a known-good install and commit a pinned `requirements.txt`. This prevents silent breakage from upstream updates.

- 📋 **Structured error responses** — Replace raw 500 exception propagation with a FastAPI exception handler that returns a JSON body (`{"error": "...", "detail": "..."}`) for Sarvam API failures. Clients currently receive no actionable error information.

- 📋 **Validate `mode` parameter** — Enumerate accepted Sarvam mode values and validate at the endpoint level, returning HTTP 422 with a clear message for unknown values rather than a delayed 500.

### Medium Priority

- 📋 **CI pipeline** — Add a GitHub Actions workflow that runs `pytest` on every push and pull request. No live API key needed since tests are fully mocked.

- 📋 **Logging configuration** — Add a startup log handler (e.g. `logging.basicConfig`) with a configurable log level so warning and error messages are visible in production without code changes.

---

## Medium-Term (1–2 months)

### Translation Quality

- 📋 **Sentence-boundary chunking** — Replace the current whitespace-split chunking for long paragraphs with a sentence-tokeniser (e.g. `nltk.sent_tokenize`). This preserves sentence context across chunk boundaries and improves translation coherence.

- 💡 **Context-window stitching** — Send a small overlap of the previous batch's text as context to the Sarvam API for each subsequent request. May improve coherence at batch boundaries.

### Document Coverage

- 📋 **Table translation** — Extend `translate_doc.py` to iterate over `doc.tables` and translate cell text in addition to paragraphs.

- 💡 **Header and footer translation** — Process `doc.sections[i].header` and `.footer` paragraph collections.

### Formatting

- 💡 **Basic formatting preservation** — Preserve bold, italic, and underline on translated runs where the source and target paragraph structure is 1:1. A safe-to-implement subset that avoids the complexity of full run-level reconstruction.

---

## Long-Term (3+ months)

### Scalability and Reliability

- 💡 **Async Sarvam API calls** — Migrate from synchronous `SarvamAI.text.translate` to async equivalents (if supported by the SDK) and run batch calls concurrently with `asyncio.gather`. This would significantly reduce latency for documents with many batches.

- 💡 **Retry with exponential backoff** — Wrap Sarvam API calls in a retry loop (e.g. `tenacity`) to handle transient network failures without surfacing them as 500 errors.

- 💡 **File size limit** — Reject uploads exceeding a configurable size (e.g. 10 MB) before processing to prevent memory exhaustion.

### Observability

- 💡 **Structured JSON logging** — Emit JSON log lines with fields for request ID, document size, paragraph count, batch count, API call durations, and any warnings. Enables log aggregation and alerting.

- 💡 **Prometheus metrics endpoint** — Expose `/metrics` with counters for requests, errors, and batch counts, and histograms for request duration and document size.

### Developer Experience

- 💡 **OpenAPI documentation** — Populate FastAPI's auto-generated docs (`/docs`) with descriptions, examples, and response schemas for the `/translate-doc` endpoint.

- 💡 **Docker image** — Add a `Dockerfile` for reproducible builds and straightforward deployment to any container platform.

- 💡 **Pre-commit hooks** — Add `.pre-commit-config.yaml` with `ruff` (linting) and `black` (formatting) to enforce code style automatically before commits.

---

## Won't Fix / Out of Scope

| Item | Reason |
|------|--------|
| Non-`.docx` formats (PDF, `.doc`, ODT) | Requires additional parsers with complex extraction logic; out of current scope |
| Full formatting preservation | Requires run-level reconstruction that is brittle when paragraph counts change on translation |
| User authentication | The service is consumed by a known frontend; auth is handled at the infrastructure level |
| Multi-file / bulk translation | Not a stated requirement; increases API surface complexity significantly |

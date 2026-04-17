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

### Abuse-Protection Safeguards (completed 2026-03-06)

Added to `app.py` ahead of public social-media launch. All six safeguards target financial and availability risks:

| Safeguard | Trigger | HTTP | Config var | Default |
|---|---|---|---|---|
| Per-IP rate limiting (`slowapi`) | >N req/min from same IP | 429 | `RATE_LIMIT_PER_MINUTE` | 5 |
| Language code validation | `source_lang`/`target_lang` not in allowlist | 422 | — | — |
| Mode validation | `mode` not `formal` or `colloquial` | 422 | — | — |
| File size limit | Upload > N MB | 413 | `MAX_FILE_SIZE_MB` | 5 |
| Document character limit | Total paragraph chars > N | 422 | `MAX_DOC_CHARS` | 50,000 |
| Request timeout | Translation takes > N seconds | 504 | `REQUEST_TIMEOUT_SECONDS` | 120 |

Also added: `INFO`-level request logging (IP, size, chars, langs, elapsed), structured JSON error bodies with `"detail"` key for all error cases, 18 new tests (46 total).

`slowapi` added to `requirements.txt`.

---

## Short-Term (next sprint)

### High Priority

- 📋 **Pin dependency versions** — Run `pip freeze` against a known-good install and commit a pinned `requirements.txt`. This prevents silent breakage from upstream updates.

### Medium Priority

- 📋 **CI pipeline** — Add a GitHub Actions workflow that runs `pytest` on every push and pull request. No live API key needed since tests are fully mocked.

- 📋 **Fix mode allowlist** — Add `classic-colloquial` and `code-mixed` to `VALID_MODES` in `app.py`. Currently these are valid Sarvam API modes on `mayura:v1` but are rejected with HTTP 422. One-line fix in the allowlist; update tests accordingly.

- 📋 **Add `speaker_gender` parameter** — Expose an optional `speaker_gender` form field (`Male` / `Female`) in the `/translate-doc` endpoint and pass it through to the Sarvam translation call. Improves output quality for gendered languages like Hindi and Tamil. Validate against the two accepted values; default to omitting the parameter if not provided.

- 📋 **Add `numerals_format` parameter** — Expose an optional `numerals_format` form field (`international` / `native`) in the `/translate-doc` endpoint and pass it through to the Sarvam translation call. Useful for documents containing numbers, dates, or financial figures. Default to `international` if not provided.

---

## Medium-Term (1–2 months)

### API Capabilities

- 📋 **Add `sarvam-translate:v1` model selection** — Expose an optional `model` form field in `/translate-doc` accepting `mayura:v1` (default) or `sarvam-translate:v1`. The new model supports all 22 scheduled languages of India (11 more than current: Bodo, Dogri, Konkani, Kashmiri, Maithili, Manipuri, Nepali, Sanskrit, Santali, Sindhi, and expanded Assamese/Urdu coverage). Constraint: `sarvam-translate:v1` only supports `formal` mode — validate this combination and return HTTP 422 if a colloquial mode is requested with that model. Update the language allowlist to include the 11 new codes when this model is selected.

- 📋 **TTS endpoint (`POST /synthesize-doc`)** — New endpoint that accepts a `.docx` file and a target language code, extracts paragraph text, and sends it to the Sarvam `bulbul:v3` TTS API. Returns an MP3 audio file of the document read aloud. Supports voice selection from the `bulbul:v3` speaker list (default: `shubh`). Apply the same abuse-protection pattern as `/translate-doc`: file size limit, character cap, rate limiting, timeout. Can be used standalone or chained after a translation.

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
| Transliteration (`/transliterate` endpoint) | Out of current scope — useful for Roman-script output but not relevant to the core .docx translation use case. Revisit if user demand emerges. |

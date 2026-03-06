# CLAUDE.md — word-translator

This file provides guidance for AI assistants working in this repository.

## Project Overview

`word-translator` is a lightweight Python API service that translates Word documents (`.docx`) between languages using the [Sarvam AI](https://www.sarvam.ai/) translation API. It exposes a single HTTP endpoint built with FastAPI and is intended to be consumed by a frontend at `job-joseph.com`.

## Repository Structure

```
word-translator/
├── app.py                      # FastAPI application, route definitions, CORS config
├── translate_doc.py            # Core translation logic (batching, chunking, Sarvam API calls)
├── requirements.txt            # Python dependencies (no version pinning)
├── pytest.ini                  # pytest configuration (testpaths = tests/)
├── README.md                   # Brief project description
├── CLAUDE.md                   # This file — AI assistant guide
├── SPEC.md                     # Authoritative technical specification
├── LEARNINGS.md                # Design decisions, bugs, and lessons learned
├── ROADMAP.md                  # Development plans and status
├── .gitignore                  # Ignores venv/, .env, __pycache__/, *.docx
└── tests/
    ├── __init__.py
    ├── test_translate_doc.py   # Unit tests for translation batching/chunking logic
    └── test_app.py             # Integration tests for the FastAPI endpoint
```

## Environment Setup

### Prerequisites
- Python 3.x
- A valid [Sarvam AI](https://www.sarvam.ai/) API key

### Installation

```bash
python -m venv venv
source venv/bin/activate       # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Environment Variables

Create a `.env` file in the project root (it is gitignored):

```
SARVAM_API_KEY=your_sarvam_api_key_here

# Optional abuse-protection limits (defaults shown):
RATE_LIMIT_PER_MINUTE=5
MAX_FILE_SIZE_MB=5
MAX_DOC_CHARS=50000
REQUEST_TIMEOUT_SECONDS=120
```

| Variable | Required | Default | Description |
|---|---|---|---|
| `SARVAM_API_KEY` | Yes | — | Sarvam AI subscription key. App raises at startup if absent. |
| `RATE_LIMIT_PER_MINUTE` | No | `5` | Max requests per IP per minute (HTTP 429 when exceeded). Memory-backed — **not shared across multiple uvicorn workers**. |
| `MAX_FILE_SIZE_MB` | No | `5` | Max upload file size in MB (HTTP 413 when exceeded). |
| `MAX_DOC_CHARS` | No | `50000` | Max total non-empty characters across all paragraphs (HTTP 422 when exceeded). Caps Sarvam API cost per request. |
| `REQUEST_TIMEOUT_SECONDS` | No | `120` | Max seconds for a translation call (HTTP 504 when exceeded). |

`app.py` reads all variables at startup. `translate_doc.py` validates the Sarvam key lazily at the point of the first API call (when `client` is not injected).

## Running the Application

```bash
uvicorn app:app --reload
```

The API will be available at `http://localhost:8000`.

## Running Tests

```bash
pytest -v
```

Tests require no API key and make no network calls. All Sarvam API interactions are mocked via the `client` dependency-injection parameter.

## API Reference

### `POST /translate-doc`

Accepts a `.docx` file and returns a translated `.docx` file.

**Form fields:**

| Field         | Type   | Required | Description                                  |
|---------------|--------|----------|----------------------------------------------|
| `file`        | file   | Yes      | A `.docx` Word document                      |
| `source_lang` | string | Yes      | BCP-47 language code of the source document  |
| `target_lang` | string | Yes      | BCP-47 language code for the output          |
| `mode`        | string | No       | Translation mode; defaults to `"formal"`     |

**Response:** A `.docx` file download named `translated.docx`.

**Example (curl):**
```bash
curl -X POST http://localhost:8000/translate-doc \
  -F "file=@document.docx" \
  -F "source_lang=en-IN" \
  -F "target_lang=hi-IN" \
  -F "mode=formal" \
  --output translated.docx
```

**CORS:** Only requests from `https://job-joseph.com` and `https://www.job-joseph.com` are allowed. Local development tools (curl, Postman) bypass CORS and work without restriction.

## Key Implementation Details

### Translation Batching and Chunking (`translate_doc.py`)

Documents are translated paragraph-by-paragraph with a **900-character buffer limit** to stay within Sarvam API constraints:

1. Paragraphs are read from the input `.docx` and accumulated into a text buffer.
2. When adding the next paragraph would exceed 900 characters, the current buffer is flushed to the Sarvam API as a single `\n`-joined text block.
3. The translated response is split back on `\n` and written as individual paragraphs into a new `Document`.
4. Empty paragraphs are preserved as blank lines without being sent to the API.
5. Any remaining buffer content is flushed after all paragraphs are processed.

**Long paragraph handling:** If a single paragraph exceeds 900 characters, `_chunk_text()` splits it on whitespace boundaries (falling back to a hard character-limit split) before buffering. Each chunk is treated as an independent unit.

**Mismatch logging:** When the Sarvam API returns a different number of `\n`-separated lines than were submitted, a `WARNING`-level log message is emitted via the `translate_doc` logger.

**Important caveats:**
- Paragraph **formatting** (bold, italic, fonts, styles) is **not preserved** — all output paragraphs use the default document style.
- The output paragraph count may differ from input if the API merges or splits lines on translation, or if long paragraphs are chunked.
- Only the `.paragraphs` property of the document is processed; tables, headers, footers, and text boxes are **not translated**.

### Dependency Injection (`translate_doc.py`)

`translate_doc()` accepts an optional `client` parameter:

```python
def translate_doc(input_path, output_path, source_lang, target_lang, mode, client=None):
```

When `client=None` (production), a `SarvamAI` instance is created from the environment key. In tests, pass a `MagicMock` to avoid any network calls or key requirements.

### Abuse-Protection Safeguards (`app.py`)

Six safeguards are applied in the endpoint, in cheapest-first order:

1. **Language code validation** — `source_lang` and `target_lang` are checked against an allowlist of 13 Sarvam BCP-47 codes. HTTP 422 if invalid (zero I/O cost).
2. **Mode validation** — `mode` must be `"formal"` or `"colloquial"`. HTTP 422 if invalid.
3. **File size limit** — `len(contents) > MAX_FILE_SIZE_BYTES` → HTTP 413.
4. **Document character limit** — total non-empty paragraph characters > `MAX_DOC_CHARS` → HTTP 422. Checked after writing to disk, before any Sarvam call. Directly caps API cost per request.
5. **Request timeout** — `translate_doc` runs in a `ThreadPoolExecutor` wrapped with `asyncio.wait_for`. HTTP 504 on expiry.
6. **Per-IP rate limit** — `slowapi` Limiter with `RATE_LIMIT_PER_MINUTE` per IP. HTTP 429 when exceeded. Memory-backed; **not shared across multiple uvicorn worker processes**.

All error responses include a `{"detail": "..."}` JSON body. Internal exception messages are never exposed.

### Temporary File Handling (`app.py`)

Each request creates a `tempfile.mkdtemp()` directory containing `input.docx` and `translated.docx`. Early-exit paths (char limit exceeded, timeout, exception) call `shutil.rmtree(tmpdir, True)` inline before returning. The success path uses `background_tasks.add_task(shutil.rmtree, tmpdir, True)` so the file remains readable until `FileResponse` finishes streaming.

## Dependencies

| Package            | Purpose                                        |
|--------------------|------------------------------------------------|
| `fastapi`          | Web framework for the API                     |
| `uvicorn`          | ASGI server to run FastAPI                    |
| `python-docx`      | Read and write `.docx` files                  |
| `python-dotenv`    | Load environment variables from `.env`        |
| `python-multipart` | Parse `multipart/form-data` file uploads      |
| `slowapi`          | Per-IP rate limiting middleware               |
| `sarvamai`         | Official Sarvam AI Python SDK                 |
| `pytest`           | Test runner (dev/test)                        |
| `httpx`            | HTTP client required by FastAPI TestClient (dev/test) |

**Note:** `requirements.txt` has no version pins. If you encounter compatibility issues, pin versions after verifying a working combination.

## Conventions and Patterns

- **Flat structure:** Keep all Python source files at the project root. `tests/` is the only subdirectory.
- **Single responsibility:** `app.py` handles HTTP concerns only; `translate_doc.py` handles document processing. Keep this separation.
- **Dependency injection for testability:** Pass external clients/services as parameters with `None` defaults to make modules testable without real credentials.
- **Tests:** Use `pytest`. Place all test files in `tests/`. Mock the Sarvam client via the `client` parameter — do not patch at the module level.
- **No linting config:** No linter or formatter is configured. Follow PEP 8 style conventions manually.
- **Environment-based config:** All secrets and deployment-specific values go in `.env`. Never hardcode credentials.
- **Language codes:** Use BCP-47 format as expected by the Sarvam AI API (e.g., `en-IN`, `hi-IN`, `ta-IN`).

## Known Limitations (not bugs)

1. **No version pinning:** `requirements.txt` may break on future dependency updates.
2. **Formatting loss:** Document styles and inline formatting are stripped during translation.
3. **Partial document coverage:** Only top-level paragraphs are translated; tables and other content blocks are ignored.
4. **No CI:** Changes cannot be automatically validated via a pipeline (tests can be run locally).
5. **Rate limiter is per-process:** `slowapi` uses in-memory storage. If uvicorn is run with multiple workers (`--workers N`), each worker enforces its own independent limit. An IP can make `N × RATE_LIMIT_PER_MINUTE` requests per minute. Use Redis storage for multi-worker deployments.
6. **Timeout does not stop the thread:** When `REQUEST_TIMEOUT_SECONDS` expires, HTTP 504 is returned immediately but the underlying translation thread continues running until the Sarvam API call completes. API credits may still be consumed.

## Related Documents

- **[SPEC.md](./SPEC.md)** — Full technical specification (API contract, algorithm, file handling, NFRs)
- **[LEARNINGS.md](./LEARNINGS.md)** — Design decisions, discovered bugs, and lessons learned
- **[ROADMAP.md](./ROADMAP.md)** — Development plans, status, and prioritised backlog

## Development Workflow

Since there is no CI pipeline, validate changes manually:

1. Activate your virtual environment and install dependencies.
2. Set up `.env` with a valid `SARVAM_API_KEY`.
3. Run the test suite: `pytest -v` (no API key needed — all mocked).
4. Start the server with `uvicorn app:app --reload`.
5. Test end-to-end using `curl` or Postman against `http://localhost:8000/translate-doc`.
6. Commit with a descriptive message following the pattern used in git history (imperative, short, focused on what changed).

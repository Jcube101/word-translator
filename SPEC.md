# SPEC.md — word-translator Technical Specification

This document defines the authoritative behaviour of the `word-translator` service. It is the source of truth for API contracts, translation algorithm semantics, error behaviour, and operational constraints.

---

## 1. Purpose and Scope

`word-translator` is a single-endpoint HTTP microservice. Its sole responsibility is to accept a Microsoft Word document (`.docx`), translate its text content between two BCP-47 language codes using the Sarvam AI translation API, and return a new `.docx` file containing the translated text.

**In scope:**
- Paragraph-level text translation of `.docx` documents
- Batching of paragraphs to respect the Sarvam API character limit
- Long-paragraph chunking to prevent oversized API requests

**Out of scope:**
- Non-`.docx` formats (`.doc`, `.pdf`, `.txt`, etc.)
- Inline formatting preservation (bold, italic, fonts, styles)
- Tables, headers, footers, text boxes, comments, or track changes
- Document structure beyond top-level paragraphs
- Authentication of API consumers

---

## 2. API Contract

### Endpoint

```
POST /translate-doc
Content-Type: multipart/form-data
```

### Request Fields

| Field         | Type            | Required | Default    | Description                                      |
|---------------|-----------------|----------|------------|--------------------------------------------------|
| `file`        | File (binary)   | Yes      | —          | A `.docx` Word document                          |
| `source_lang` | string          | Yes      | —          | BCP-47 language code of the source document      |
| `target_lang` | string          | Yes      | —          | BCP-47 language code for the output document     |
| `mode`        | string          | No       | `"formal"` | Sarvam translation mode                          |

### Language Code Format

All language codes use BCP-47 format. The server validates against an explicit allowlist and returns HTTP 422 for unrecognised codes. Accepted values:

| Code    | Language        |
|---------|-----------------|
| `en-IN` | English (India) |
| `hi-IN` | Hindi           |
| `ta-IN` | Tamil           |
| `te-IN` | Telugu          |
| `kn-IN` | Kannada         |
| `ml-IN` | Malayalam       |
| `mr-IN` | Marathi         |
| `gu-IN` | Gujarati        |
| `bn-IN` | Bengali         |
| `pa-IN` | Punjabi         |
| `as-IN` | Assamese        |
| `od-IN` | Odia            |
| `ur-IN` | Urdu            |

### Translation Mode

The server validates `mode` against an explicit allowlist and returns HTTP 422 for unrecognised values. Accepted values:
- `"formal"` (default) — formal register
- `"colloquial"` — conversational register

### Response — Success

```
HTTP 200 OK
Content-Type: application/vnd.openxmlformats-officedocument.wordprocessingml.document
Content-Disposition: attachment; filename="translated.docx"
```

Body: binary `.docx` file containing the translated paragraphs.

### Response — Errors

All error responses return a JSON body with a `"detail"` key.

| Condition | HTTP Status |
|---|---|
| Missing required field (`file`, `source_lang`, `target_lang`) | `422 Unprocessable Entity` |
| Invalid `source_lang` or `target_lang` (not in allowlist) | `422 Unprocessable Entity` |
| Invalid `mode` (not `formal` or `colloquial`) | `422 Unprocessable Entity` |
| Document too large (total chars > `MAX_DOC_CHARS`) | `422 Unprocessable Entity` |
| File exceeds `MAX_FILE_SIZE_MB` | `413 Request Entity Too Large` |
| Per-IP rate limit exceeded | `429 Too Many Requests` |
| Translation call exceeds `REQUEST_TIMEOUT_SECONDS` | `504 Gateway Timeout` |
| Sarvam API or internal processing failure | `500 Internal Server Error` |

Internal exception messages are never exposed in error responses.

### Example Request (curl)

```bash
curl -X POST http://localhost:8000/translate-doc \
  -F "file=@document.docx" \
  -F "source_lang=en-IN" \
  -F "target_lang=hi-IN" \
  -F "mode=formal" \
  --output translated.docx
```

---

## 3. CORS Policy

Only the following origins are permitted to make cross-origin requests:

| Allowed Origin                  |
|---------------------------------|
| `https://job-joseph.com`        |
| `https://www.job-joseph.com`    |

Allowed methods: `POST`, `OPTIONS`
Allowed headers: all (`*`)
Credentials: allowed

Local tooling (curl, Postman, server-to-server calls) bypasses CORS and always works regardless of origin.

---

## 4. Translation Algorithm

### 4.1 Overview

```
Input .docx
    │
    ▼
Read paragraphs (doc.paragraphs only)
    │
    ▼
For each paragraph:
  ├─ Empty? → write blank line to output, skip API
  └─ Non-empty:
       ├─ Fits in buffer (buffer_len + len(text) ≤ 900)? → buffer it
       └─ Doesn't fit?
            ├─ Single paragraph > 900 chars? → _chunk_text() → buffer each chunk
            └─ Flush buffer to Sarvam API → split response on \n → write to output
    │
    ▼
Flush remaining buffer to Sarvam API
    │
    ▼
Save output .docx
```

### 4.2 Paragraph Buffer

- Paragraphs are accumulated in a text buffer.
- The buffer is flushed (sent to Sarvam API) when the next paragraph would cause `buffer_len + len(text) > 900`.
- Flushing joins all buffered paragraphs with `\n` into a single API request, then splits the translated response back on `\n`.
- Any remaining buffered content is flushed once after all paragraphs are processed.

**Buffer limit:** 900 characters. This is a conservative value below the Sarvam API per-request maximum.

### 4.3 Long Paragraph Chunking

If a single paragraph's text exceeds 900 characters, `_chunk_text()` splits it before buffering:

1. Attempt to split at the last whitespace boundary within the character limit.
2. If no whitespace exists within the limit, perform a hard split at the character boundary.
3. Each resulting chunk is treated as an independent unit in the buffer.

**Consequence:** A single source paragraph may be translated as multiple chunks and produce multiple output paragraphs.

### 4.4 Empty Paragraph Handling

Paragraphs where `para.text.strip() == ""` are written directly to the output document as blank paragraphs without making any API call. This preserves visual spacing.

### 4.5 Paragraph Count Invariant

The output document is **not** guaranteed to have the same number of paragraphs as the input. Two mechanisms can alter the count:

1. **Long paragraph chunking** (§4.3): one input paragraph may become multiple output paragraphs.
2. **Sarvam API line merging/splitting**: the API may return fewer or more `\n`-separated lines than were submitted.

A `WARNING`-level log message is emitted when the submitted and returned paragraph counts differ for a single batch.

### 4.6 Formatting

All output paragraphs are added to a fresh `Document()` using `add_paragraph()` with the default style. **No formatting is preserved**: bold, italic, font size, font family, heading levels, list styles, and all other formatting is stripped.

### 4.7 Content Coverage

Only `doc.paragraphs` is processed. The following document elements are **not translated**:

- Tables (cells, headers, footers of tables)
- Headers and footers
- Text boxes and shapes
- Comments and annotations
- Track-changes content
- Footnotes and endnotes

---

## 5. File Handling

### Temporary Directory Lifecycle

1. On each request, a new temporary directory is created via `tempfile.mkdtemp()`.
2. The uploaded file is written to `<tmpdir>/input.docx`.
3. The translated document is written to `<tmpdir>/translated.docx`.
4. `translated.docx` is streamed to the caller as a `FileResponse`.
5. A FastAPI `BackgroundTask` calls `shutil.rmtree(tmpdir, ignore_errors=True)` after the response is sent, cleaning up both files and the directory.

### Concurrency

Each request receives its own isolated temporary directory, so concurrent requests do not interfere with each other's files.

---

## 6. Configuration

All runtime configuration is via environment variables, loaded from a `.env` file at startup via `python-dotenv`.

| Variable | Required | Default | Description |
|---|---|---|---|
| `SARVAM_API_KEY` | Yes | — | Sarvam AI API subscription key. Application raises an exception at startup if absent. |
| `RATE_LIMIT_PER_MINUTE` | No | `5` | Maximum requests per IP address per minute. Returns HTTP 429 when exceeded. Memory-backed; not shared across multiple uvicorn worker processes. |
| `MAX_FILE_SIZE_MB` | No | `5` | Maximum accepted upload size in megabytes. Returns HTTP 413 when exceeded. Checked immediately after the file is read. |
| `MAX_DOC_CHARS` | No | `50000` | Maximum total non-empty text characters across all paragraphs in the document. Returns HTTP 422 when exceeded. Checked before any Sarvam API call is made. ~55 Sarvam API batches at most per document at the default. |
| `REQUEST_TIMEOUT_SECONDS` | No | `120` | Maximum seconds to wait for `translate_doc` to complete. Returns HTTP 504 when exceeded. The underlying thread continues to completion after timeout (cannot be interrupted). |

---

## 7. Non-Functional Requirements

| Concern | Current Behaviour |
|---|---|
| **Scalability** | Single-process, no worker pool. Scale by running multiple uvicorn instances behind a load balancer. Note: the rate limiter uses in-memory storage and is **not shared across workers** — each worker enforces its own independent limit. |
| **Reliability** | No retry logic on Sarvam API failures; errors propagate as HTTP 500. Request timeout (default 120 s) prevents indefinite blocking. |
| **Observability** | `INFO`-level log on every request (IP, file size, char count, langs, elapsed time). `WARNING`-level log on paragraph count mismatches. No structured JSON logging or metrics. |
| **Security** | Per-IP rate limiting (default 5/minute). File size limit (default 5 MB). Document character limit (default 50,000 chars). Language code and mode validation. CORS restricts browser access to two domains. API key is environment-variable only, never logged or returned. Internal error messages are never exposed in HTTP responses. |
| **Cost protection** | `MAX_FILE_SIZE_MB` caps upload bandwidth. `MAX_DOC_CHARS` caps Sarvam API calls per request. `RATE_LIMIT_PER_MINUTE` caps requests per IP. |
| **Dependency versions** | No version pins in `requirements.txt`. Behaviour on future dependency updates is undefined. |

---

## 8. Dependencies

| Package            | Role                                                  |
|--------------------|-------------------------------------------------------|
| `fastapi`          | HTTP framework and request validation                 |
| `uvicorn`          | ASGI server                                           |
| `python-docx`      | `.docx` read/write                                    |
| `python-dotenv`    | `.env` loading                                        |
| `python-multipart` | `multipart/form-data` parsing (file uploads)          |
| `slowapi`          | Per-IP rate limiting middleware for FastAPI           |
| `sarvamai`         | Sarvam AI Python SDK                                  |
| `pytest`           | Test runner (dev/test only)                           |
| `httpx`            | Async HTTP client required by FastAPI TestClient (dev/test only) |

---

## 9. Running the Service

```bash
# Install dependencies
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configure
echo "SARVAM_API_KEY=your_key_here" > .env

# Start
uvicorn app:app --reload
```

Service listens on `http://localhost:8000`.

### Running Tests

```bash
pytest -v
```

Tests require no API key and make no network calls; all Sarvam API interactions are mocked.

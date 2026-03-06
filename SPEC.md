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
- Rate limiting or quota enforcement

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

All language codes use BCP-47 format as required by the Sarvam AI API. Supported values include (but are not limited to):

| Code    | Language   |
|---------|------------|
| `en-IN` | English (India) |
| `hi-IN` | Hindi      |
| `ta-IN` | Tamil      |
| `te-IN` | Telugu     |
| `kn-IN` | Kannada    |
| `ml-IN` | Malayalam  |
| `mr-IN` | Marathi    |
| `gu-IN` | Gujarati   |
| `bn-IN` | Bengali    |
| `pa-IN` | Punjabi    |

Refer to the [Sarvam AI documentation](https://www.sarvam.ai/) for the complete list of supported language pairs.

### Translation Mode

The `mode` field is passed directly to the Sarvam AI API. Known accepted values:
- `"formal"` (default) — formal register
- `"colloquial"` — conversational register

No server-side validation is performed on this field. An unrecognised value will cause the Sarvam API to reject the request, which propagates as HTTP 500.

### Response — Success

```
HTTP 200 OK
Content-Type: application/vnd.openxmlformats-officedocument.wordprocessingml.document
Content-Disposition: attachment; filename="translated.docx"
```

Body: binary `.docx` file containing the translated paragraphs.

### Response — Errors

| Condition | HTTP Status | Body |
|---|---|---|
| Missing required field (`file`, `source_lang`, `target_lang`) | `422 Unprocessable Entity` | FastAPI validation error JSON |
| Translation or document processing failure | `500 Internal Server Error` | FastAPI default error JSON |

**Note:** There is currently no structured error body for 500 responses. The exception message propagates unformatted.

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

| Variable         | Required | Description                       |
|------------------|----------|-----------------------------------|
| `SARVAM_API_KEY` | Yes      | Sarvam AI API subscription key    |

The application raises `Exception("SARVAM_API_KEY not set")` at startup if this variable is absent.

---

## 7. Non-Functional Requirements

| Concern | Current Behaviour |
|---|---|
| **Scalability** | Single-process, no worker pool. Scale by running multiple uvicorn instances behind a load balancer. |
| **Reliability** | No retry logic on Sarvam API failures; errors propagate as HTTP 500. |
| **Observability** | Standard Python `logging` is used. Log level `WARNING` is emitted on paragraph count mismatches. No structured logging or metrics. |
| **Security** | No authentication. CORS restricts browser access to two domains. API key is environment-variable only, never logged or returned. |
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

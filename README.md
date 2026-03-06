# word-translator

A lightweight Python microservice that translates Microsoft Word documents (`.docx`) between languages using the [Sarvam AI](https://www.sarvam.ai/) translation API. Built with FastAPI and intended to be consumed by a frontend at [job-joseph.com](https://job-joseph.com).

---

## Features

- Translate `.docx` documents between any Sarvam-supported BCP-47 language pair
- Paragraph-level batching with a 900-character buffer to respect API limits
- Automatic chunking of long paragraphs (> 900 chars) on whitespace boundaries
- Empty paragraphs preserved as blank lines without API calls
- Per-IP rate limiting (default: 5 requests/minute) via `slowapi`
- File size limit (default: 5 MB) to prevent memory exhaustion
- Document character limit (default: 50,000 chars) to cap API cost per request
- Request timeout (default: 120 s) to prevent hung connections
- Language code and mode validation with clear 422 error messages
- Structured JSON error bodies for all error cases
- CORS restricted to `https://job-joseph.com` and `https://www.job-joseph.com`

---

## Quick Start

### 1. Install dependencies

```bash
python -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure

Create a `.env` file in the project root:

```
SARVAM_API_KEY=your_sarvam_api_key_here

# Optional — tune these to control abuse exposure:
RATE_LIMIT_PER_MINUTE=5
MAX_FILE_SIZE_MB=5
MAX_DOC_CHARS=50000
REQUEST_TIMEOUT_SECONDS=120
```

### 3. Run

```bash
uvicorn app:app --reload
```

The API is available at `http://localhost:8000`.

---

## API

### `POST /translate-doc`

Translate a `.docx` file from one language to another.

**Form fields:**

| Field         | Type   | Required | Default    | Description                              |
|---------------|--------|----------|------------|------------------------------------------|
| `file`        | file   | Yes      | —          | A `.docx` Word document                  |
| `source_lang` | string | Yes      | —          | BCP-47 source language (e.g. `en-IN`)    |
| `target_lang` | string | Yes      | —          | BCP-47 target language (e.g. `hi-IN`)    |
| `mode`        | string | No       | `"formal"` | Translation mode (`formal`/`colloquial`) |

**Response:** `translated.docx` — a `.docx` file download.

**Example:**

```bash
curl -X POST http://localhost:8000/translate-doc \
  -F "file=@document.docx" \
  -F "source_lang=en-IN" \
  -F "target_lang=hi-IN" \
  -F "mode=formal" \
  --output translated.docx
```

---

## Running Tests

```bash
pytest -v
```

No API key required — all Sarvam API interactions are mocked.

---

## Project Structure

```
word-translator/
├── app.py                # FastAPI app, routing, CORS, temp file handling
├── translate_doc.py      # Translation logic: batching, chunking, Sarvam calls
├── requirements.txt      # Python dependencies
├── pytest.ini            # pytest config
├── SPEC.md               # Authoritative technical specification
├── ROADMAP.md            # Development plans and backlog
├── CLAUDE.md             # AI assistant guide
├── LEARNINGS.md          # Design decisions and lessons learned
└── tests/
    ├── test_translate_doc.py
    └── test_app.py
```

---

## Known Limitations

- **Formatting is not preserved** — bold, italic, fonts, and styles are stripped in the output.
- **Partial document coverage** — only top-level paragraphs are translated; tables, headers, footers, and text boxes are skipped.
- **Rate limiter is per-process** — with multiple uvicorn workers each worker enforces its own independent limit.
- **No version pinning** — `requirements.txt` has no version specifiers.
- **No CI** — run `pytest -v` locally before pushing.

See [ROADMAP.md](./ROADMAP.md) for planned improvements and [LEARNINGS.md](./LEARNINGS.md) for design decisions and bug history.

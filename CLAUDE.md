# CLAUDE.md — word-translator

This file provides guidance for AI assistants working in this repository.

## Project Overview

`word-translator` is a lightweight Python API service that translates Word documents (`.docx`) between languages using the [Sarvam AI](https://www.sarvam.ai/) translation API. It exposes a single HTTP endpoint built with FastAPI and is intended to be consumed by a frontend at `job-joseph.com`.

## Repository Structure

```
word-translator/
├── app.py              # FastAPI application, route definitions, CORS config
├── translate_doc.py    # Core translation logic (paragraph batching + Sarvam API calls)
├── requirements.txt    # Python dependencies (no version pinning)
├── README.md           # Brief project description
├── .gitignore          # Ignores venv/, .env, __pycache__/, *.docx
└── CLAUDE.md           # This file
```

There are no subdirectories, test files, CI/CD configuration, or build tooling.

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
```

Both `app.py` and `translate_doc.py` call `load_dotenv()` on import and will raise an exception at startup if `SARVAM_API_KEY` is not set.

## Running the Application

```bash
uvicorn app:app --reload
```

The API will be available at `http://localhost:8000`.

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

### Translation Batching (`translate_doc.py`)

Documents are translated paragraph-by-paragraph with a **900-character buffer limit** to stay within Sarvam API constraints:

1. Paragraphs are read from the input `.docx` and accumulated into a text buffer.
2. When adding the next paragraph would exceed 900 characters, the current buffer is flushed to the Sarvam API as a single `\n`-joined text block.
3. The translated response is split back on `\n` and written as individual paragraphs into a new `Document`.
4. Empty paragraphs are preserved as blank lines without being sent to the API.
5. Any remaining buffer content is flushed after all paragraphs are processed.

**Important caveats:**
- Paragraph **formatting** (bold, italic, fonts, styles) is **not preserved** — all output paragraphs use the default document style.
- The output paragraph count may differ from input if the API merges or splits lines on translation.
- Only the `.paragraphs` property of the document is processed; tables, headers, footers, and text boxes are **not translated**.

### Temporary File Handling (`app.py`)

Each request creates a `tempfile.mkdtemp()` directory containing `input.docx` and `translated.docx`. Cleanup is scheduled via FastAPI `BackgroundTasks`.

**Known bug (line 56 of `app.py`):** The cleanup command uses a Windows shell syntax:
```python
os.system(f'rmdir /s /q "{tmpdir}"')
```
This does nothing on Linux/macOS. Temporary directories will accumulate until the process restarts or the OS cleans `/tmp`. Do not change this without confirming the deployment OS.

## Dependencies

| Package            | Purpose                                        |
|--------------------|------------------------------------------------|
| `fastapi`          | Web framework for the API                     |
| `uvicorn`          | ASGI server to run FastAPI                    |
| `python-docx`      | Read and write `.docx` files                  |
| `python-dotenv`    | Load `SARVAM_API_KEY` from `.env`             |
| `python-multipart` | Parse `multipart/form-data` file uploads      |
| `sarvamai`         | Official Sarvam AI Python SDK                 |

**Note:** `requirements.txt` has no version pins. If you encounter compatibility issues, pin versions after verifying a working combination.

## Conventions and Patterns

- **Flat structure:** Keep all Python source files at the project root. Do not introduce subdirectories without a compelling reason.
- **Single responsibility:** `app.py` handles HTTP concerns only; `translate_doc.py` handles document processing. Keep this separation.
- **No tests:** The project currently has no test suite. If adding tests, use `pytest` and place files in a `tests/` directory.
- **No linting config:** No linter or formatter is configured. Follow PEP 8 style conventions manually.
- **Environment-based config:** All secrets and deployment-specific values go in `.env`. Never hardcode credentials.
- **Language codes:** Use BCP-47 format as expected by the Sarvam AI API (e.g., `en-IN`, `hi-IN`, `ta-IN`).

## Known Issues and Limitations

1. **Cleanup bug:** Temp directory cleanup uses Windows syntax and silently fails on Linux (see above).
2. **No version pinning:** `requirements.txt` may break on future dependency updates.
3. **Formatting loss:** Document styles and inline formatting are stripped during translation.
4. **Partial document coverage:** Only top-level paragraphs are translated; tables and other content blocks are ignored.
5. **No error handling:** If the Sarvam API call fails, the exception propagates and returns a 500 with no user-friendly message.
6. **No tests or CI:** Changes cannot be automatically validated.

## Development Workflow

Since there is no test suite or CI pipeline, validate changes manually:

1. Activate your virtual environment and install dependencies.
2. Set up `.env` with a valid `SARVAM_API_KEY`.
3. Start the server with `uvicorn app:app --reload`.
4. Test using `curl` or a tool like Postman against `http://localhost:8000/translate-doc`.
5. Commit with a descriptive message following the pattern used in git history (imperative, short, focused on what changed).

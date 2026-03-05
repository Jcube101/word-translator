# LEARNINGS.md — word-translator

This file records design decisions, bugs discovered, and lessons learned during development. It is intended to be updated as the project evolves.

---

## Project Context

`word-translator` was built as a focused Python microservice to translate `.docx` Word documents via the Sarvam AI API. It was developed rapidly (10 commits across ~11 days) as a backend for a frontend at `job-joseph.com`.

---

## Design Decisions

### 1. Paragraph-level batching with a 900-character limit
**Decision:** Instead of sending the entire document in one API call, paragraphs are accumulated into a buffer and flushed when the next paragraph would exceed 900 characters.

**Rationale:** The Sarvam AI API imposes a character limit per request. Sending paragraphs in batches rather than one-by-one minimises the number of API round-trips while respecting that limit. 900 was chosen conservatively below any documented limit.

**Trade-off:** If a single paragraph exceeds 900 characters it will be added to an empty buffer and sent alone, potentially still breaching the limit. There is no safeguard for this edge case.

---

### 2. `\n`-joined text blocks for batch translation
**Decision:** Paragraphs in each buffer are joined with `\n` before being sent to the API, and the translated response is split back on `\n` to recover individual paragraphs.

**Rationale:** Sending a single multi-line string allows the API to maintain context across adjacent paragraphs, which can improve translation quality for connected sentences.

**Trade-off:** If the Sarvam API normalises or removes newlines in its output, the split produces fewer paragraphs than were submitted. The output document will then silently have fewer paragraphs than the input, with no error raised.

---

### 3. No formatting preservation
**Decision:** The output document is a fresh `Document()` with paragraphs added via `add_paragraph()` using the default style.

**Rationale:** `python-docx` requires non-trivial run-level manipulation to replicate formatting. At the prototype stage this complexity was not justified.

**Trade-off:** Bold, italic, font size, heading styles, lists, and all other inline/block formatting is lost. This is the single most visible limitation for end users.

---

### 4. Flat project structure
**Decision:** All Python source lives in the project root with no subdirectories.

**Rationale:** The service has exactly two modules (`app.py`, `translate_doc.py`). Introducing a `src/` package or sub-packages would add indirection with no benefit at this size.

**Trade-off:** Scales poorly if the project grows. A `tests/` directory (already recommended in CLAUDE.md) is the one justified exception.

---

### 5. Separation of HTTP and translation concerns
**Decision:** `app.py` handles only HTTP (file upload, temp files, response, CORS). `translate_doc.py` handles only document processing.

**Rationale:** Keeps each module testable in isolation. `translate_doc` can be called directly in tests without spinning up an HTTP server.

---

### 6. No version pinning in `requirements.txt`
**Decision:** Dependencies are listed without version specifiers (`fastapi`, `uvicorn`, etc.).

**Rationale:** Acceptable for a rapid prototype; simplifies initial setup.

**Trade-off:** Any upstream breaking change will silently break the service on the next `pip install`. Should be pinned (e.g. `pip freeze > requirements.txt`) before long-term deployment.

---

## Bugs Discovered

### BUG-1: Windows-only temp directory cleanup (active)
**File:** `app.py`, line 56
**Code:** `os.system(f'rmdir /s /q "{tmpdir}"')`
**Impact:** On Linux/macOS (the likely deployment environment), this command is a no-op. Every request that processes a document leaves behind a directory under `/tmp` containing both the input and output `.docx` files. These accumulate until the OS purges `/tmp` or the process restarts.
**Fix:** Replace with `shutil.rmtree(tmpdir, ignore_errors=True)` which is cross-platform. Confirm deployment OS before changing.

---

### BUG-2: No guard against oversized single paragraphs (active)
**File:** `translate_doc.py`, lines 45–54
**Impact:** A paragraph whose text length alone exceeds 900 characters will be buffered and sent as a single block to the Sarvam API, potentially exceeding the API's per-request character limit and causing a runtime error.
**Fix:** Either truncate at the character limit (lossy) or split long paragraphs on sentence boundaries before buffering.

---

### BUG-3: Silent paragraph count mismatch (active)
**File:** `translate_doc.py`, line 36
**Impact:** If the Sarvam API returns fewer or more `\n`-separated lines than were submitted (e.g. it merges two short sentences), the output document will have a different number of paragraphs than the input without any warning.
**Fix:** Add a post-translation assertion or logging statement comparing submitted vs. returned paragraph counts.

---

### BUG-4: Module-level side effects make `translate_doc` hard to test (active)
**File:** `translate_doc.py`, lines 6–12
**Impact:** `load_dotenv()`, `os.getenv()`, and `SarvamAI(...)` all execute at import time. Any test that imports `translate_doc` will fail immediately unless `SARVAM_API_KEY` is set in the environment, and it will instantiate a real API client even in unit tests.
**Fix:** Move client initialisation inside the `translate_doc()` function or accept the client as a parameter (dependency injection), which also enables easy mocking in tests.

---

## Observations & Lessons

### Testing the Sarvam API in isolation
Manual testing with `curl` is the current validation path. There is no mock for the Sarvam SDK, which means every test run touching `translate_doc` requires a live API key and makes real network calls. Introducing a mock (via `unittest.mock.patch`) is the minimum step needed to make the test suite runnable in CI without credentials.

### CORS scope is deliberately narrow
Only `https://job-joseph.com` and `https://www.job-joseph.com` are in the allow-list. This was a deliberate tightening after the original broad CORS was added (`Enable CORS for browser access` → `Fix CORS for Lovable domain`). Any new consumer of the API (e.g. a staging frontend) must be added explicitly.

### Translation mode is user-controlled
The `mode` field (defaulting to `"formal"`) is passed directly to the Sarvam API without validation. If the API rejects an unknown mode, the exception propagates as a 500. Accepted values should be documented and validated at the endpoint.

### Git history as documentation
Because there are no inline comments and the README is minimal, the git log (`git log --oneline`) is the primary record of *why* certain values were chosen (e.g. `Changed char limit to 900`). Keep commit messages descriptive.

---

## Recommended Next Steps

| Priority | Action |
|----------|--------|
| High | Fix BUG-1: replace `rmdir /s /q` with `shutil.rmtree` |
| High | Fix BUG-4: move client init inside function to unblock testing |
| Medium | Add `pytest` test suite covering batching logic and API endpoint |
| Medium | Pin dependency versions with `pip freeze` |
| Low | Add error handling: catch Sarvam API errors and return HTTP 502 with a message |
| Low | Validate `mode` parameter against known values |
| Low | Log paragraph count mismatches (BUG-3) |

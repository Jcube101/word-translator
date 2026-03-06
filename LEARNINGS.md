# LEARNINGS.md — word-translator

This file records design decisions, bugs discovered, and lessons learned during development. It is updated as the project evolves.

---

## Project Context

`word-translator` was built as a focused Python microservice to translate `.docx` Word documents via the Sarvam AI API. It was developed rapidly (10 commits across ~11 days) as a backend for a frontend at `job-joseph.com`.

---

## Design Decisions

### 1. Paragraph-level batching with a 900-character limit
**Decision:** Instead of sending the entire document in one API call, paragraphs are accumulated into a buffer and flushed when the next paragraph would exceed 900 characters.

**Rationale:** The Sarvam AI API imposes a character limit per request. Sending paragraphs in batches rather than one-by-one minimises the number of API round-trips while respecting that limit. 900 was chosen conservatively below any documented limit.

**Trade-off:** A single paragraph exceeding 900 characters used to be sent unguarded. This is now addressed by BUG-2's fix (see below).

---

### 2. `\n`-joined text blocks for batch translation
**Decision:** Paragraphs in each buffer are joined with `\n` before being sent to the API, and the translated response is split back on `\n` to recover individual paragraphs.

**Rationale:** Sending a single multi-line string allows the API to maintain context across adjacent paragraphs, which can improve translation quality for connected sentences.

**Trade-off:** If the Sarvam API normalises or removes newlines in its output, the split produces fewer paragraphs than were submitted. The output document will then silently have fewer paragraphs than the input. A warning log (BUG-3's fix) now flags this at runtime.

---

### 3. No formatting preservation
**Decision:** The output document is a fresh `Document()` with paragraphs added via `add_paragraph()` using the default style.

**Rationale:** `python-docx` requires non-trivial run-level manipulation to replicate formatting. At the prototype stage this complexity was not justified.

**Trade-off:** Bold, italic, font size, heading styles, lists, and all other inline/block formatting is lost. This is the single most visible limitation for end users. Tracked in ROADMAP.md as a long-term consideration.

---

### 4. Flat project structure
**Decision:** All Python source lives in the project root. `tests/` is the only subdirectory.

**Rationale:** The service has exactly two modules (`app.py`, `translate_doc.py`). Introducing a `src/` package would add indirection with no benefit at this size.

---

### 5. Separation of HTTP and translation concerns
**Decision:** `app.py` handles only HTTP (file upload, temp files, response, CORS). `translate_doc.py` handles only document processing.

**Rationale:** Keeps each module testable in isolation. `translate_doc` can be called directly in tests without spinning up an HTTP server.

---

### 6. Dependency injection for the Sarvam client
**Decision:** `translate_doc()` accepts an optional `client` parameter. When `None`, a real client is created from the environment. In tests, a mock is passed.

**Rationale:** This was introduced as a fix for BUG-4, replacing the previous module-level client instantiation. It eliminates the need for patching and makes the dependency explicit.

**Pattern:**
```python
def translate_doc(..., client=None):
    if client is None:
        client = _get_client()
```

---

### 7. No version pinning in `requirements.txt`
**Decision:** Dependencies are listed without version specifiers.

**Rationale:** Acceptable for a rapid prototype; simplifies initial setup.

**Trade-off:** Any upstream breaking change will silently break the service on the next `pip install`. Should be pinned before long-term deployment.

---

## Bugs Discovered and Fixed

### BUG-1: Windows-only temp directory cleanup ✅ Fixed
**File:** `app.py`
**Original code:** `os.system(f'rmdir /s /q "{tmpdir}"')`
**Impact:** On Linux/macOS, this command is a no-op. Every request left behind a directory under `/tmp` containing both `.docx` files. These accumulated until the OS purged `/tmp`.
**Fix (2026-03-05):** Replaced with `shutil.rmtree(tmpdir, True)` — cross-platform, silent on errors, called via `background_tasks.add_task`.

---

### BUG-2: No guard against oversized single paragraphs ✅ Fixed
**File:** `translate_doc.py`
**Impact:** A paragraph whose text length alone exceeded 900 characters was buffered and sent as a single block to the Sarvam API, potentially exceeding the API's per-request character limit and causing a runtime error.
**Fix (2026-03-05):** Introduced `_chunk_text(text, max_chars)` which splits long text on whitespace boundaries (falling back to a hard character split). Each chunk is handled independently within the buffer loop. This ensures no single API request ever exceeds 900 characters.

---

### BUG-3: Silent paragraph count mismatch ✅ Fixed
**File:** `translate_doc.py`
**Impact:** If the Sarvam API returned fewer or more `\n`-separated lines than were submitted, the output document silently had a different paragraph count with no indication to the caller or operator.
**Fix (2026-03-05):** After each `flush_buffer()`, the submitted and returned counts are compared. If they differ, a `WARNING`-level log message is emitted via `logging.getLogger(__name__)`.

---

### BUG-4: Module-level side effects make `translate_doc` untestable ✅ Fixed
**File:** `translate_doc.py`
**Impact:** `load_dotenv()`, `os.getenv()`, and `SarvamAI(...)` all executed at import time. Any test importing `translate_doc` would fail unless `SARVAM_API_KEY` was present in the environment, and a real API client was instantiated even in unit tests. This also made the module impossible to import safely in environments without credentials.
**Fix (2026-03-05):**
- Removed the module-level `client = SarvamAI(...)` instantiation.
- Introduced `_get_client()` — a private factory function that creates the client from the environment on demand.
- Added `client=None` parameter to `translate_doc()`. When `None`, `_get_client()` is called. Tests pass a `MagicMock` instead.
- `load_dotenv()` is retained at module level (it is safe to call without a key — it simply does nothing if `.env` is absent).

---

## Observations & Lessons

### Dependency injection is the right pattern for external clients
The original pattern (module-level instantiation) is common in quick scripts but breaks unit testing. The `client=None` default parameter is a minimal, Pythonic solution: production callers pass nothing, tests pass mocks, and the function signature documents the dependency explicitly.

### shutil.rmtree vs os.system for cleanup
Using `shutil.rmtree` is always preferable to shell commands for filesystem cleanup in Python: it is cross-platform, raises no subprocess overhead, handles non-empty directories, and accepts `ignore_errors=True` to silently handle races between the background task and the OS.

### Testing the Sarvam API in isolation
Manual testing with `curl` was the only validation path before the test suite was added. Now, `pytest -v` validates all core logic with zero network calls. The mock client pattern via `client=None` dependency injection is far cleaner than patching at the module level.

### CORS scope is deliberately narrow
Only `https://job-joseph.com` and `https://www.job-joseph.com` are in the allow-list. This was a deliberate tightening after the original broad CORS was added (`Enable CORS for browser access` → `Fix CORS for Lovable domain`). Any new consumer (e.g. a staging frontend) must be added explicitly.

### Translation mode is user-controlled but unvalidated
The `mode` field is passed directly to the Sarvam API without validation. If the API rejects an unknown mode, the exception propagates as HTTP 500. Accepted values should be documented and validated at the endpoint. Tracked in ROADMAP.md.

### Git history as documentation
Because there were no inline comments and the README was minimal before this documentation effort, the git log was the primary record of *why* certain values were chosen (e.g. `Changed char limit to 900`). Keep commit messages descriptive.

---

## Recommended Next Steps

| Priority | Action | Status |
|----------|--------|--------|
| High | Fix BUG-1: `shutil.rmtree` | ✅ Done |
| High | Fix BUG-4: dependency injection for client | ✅ Done |
| High | Add test suite | ✅ Done |
| Medium | Fix BUG-2: long paragraph chunking | ✅ Done |
| Medium | Fix BUG-3: log paragraph count mismatches | ✅ Done |
| Medium | Write SPEC.md, ROADMAP.md, update CLAUDE.md | ✅ Done |
| Medium | Pin dependency versions | 📋 Planned (see ROADMAP.md) |
| Medium | Add CI pipeline (GitHub Actions) | 📋 Planned |
| Low | Structured error responses (HTTP 502 for Sarvam failures) | 📋 Planned |
| Low | Validate `mode` parameter against known values | 📋 Planned |

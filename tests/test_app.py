"""
Integration tests for app.py — FastAPI endpoint behaviour.

Uses FastAPI's TestClient (backed by httpx). The translate_doc function is
patched at the app module level so no real translation or Sarvam API calls occur.

Run with:
    pytest tests/test_app.py -v
"""

import io
import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from docx import Document

# Provide a dummy key to satisfy app.py's module-level guard.
os.environ.setdefault("SARVAM_API_KEY", "test-key-for-integration-tests")

import app as app_module

client = TestClient(app_module.app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_docx_bytes(paragraphs: list[str]) -> bytes:
    """Return a valid .docx file as raw bytes, ready for a multipart upload."""
    buf = io.BytesIO()
    doc = Document()
    for para in paragraphs:
        doc.add_paragraph(para)
    doc.save(buf)
    buf.seek(0)
    return buf.read()


def _fake_translate(input_path, output_path, source_lang, target_lang, mode, **kwargs):
    """Side-effect for patched translate_doc: writes a minimal valid .docx output."""
    doc = Document()
    doc.add_paragraph("translated output")
    doc.save(output_path)


DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


# ---------------------------------------------------------------------------
# Happy-path tests
# ---------------------------------------------------------------------------

class TestTranslateDocEndpoint:

    def test_valid_request_returns_200_and_docx(self):
        """A well-formed request returns HTTP 200 with a .docx content type."""
        with patch("app.translate_doc", side_effect=_fake_translate):
            response = client.post(
                "/translate-doc",
                files={"file": ("test.docx", _make_docx_bytes(["Hello"]), DOCX_MIME)},
                data={"source_lang": "en-IN", "target_lang": "hi-IN"},
            )
        assert response.status_code == 200
        assert "wordprocessingml.document" in response.headers["content-type"]

    def test_response_filename_is_translated_docx(self):
        """Content-Disposition header specifies filename as translated.docx."""
        with patch("app.translate_doc", side_effect=_fake_translate):
            response = client.post(
                "/translate-doc",
                files={"file": ("test.docx", _make_docx_bytes(["Hello"]), DOCX_MIME)},
                data={"source_lang": "en-IN", "target_lang": "hi-IN"},
            )
        assert "translated.docx" in response.headers.get("content-disposition", "")

    def test_mode_defaults_to_formal(self):
        """When `mode` is not supplied it defaults to 'formal'."""
        captured = {}

        def _capture(input_path, output_path, source_lang, target_lang, mode, **kwargs):
            captured["mode"] = mode
            _fake_translate(input_path, output_path, source_lang, target_lang, mode)

        with patch("app.translate_doc", side_effect=_capture):
            client.post(
                "/translate-doc",
                files={"file": ("test.docx", _make_docx_bytes(["Hello"]), DOCX_MIME)},
                data={"source_lang": "en-IN", "target_lang": "hi-IN"},
            )
        assert captured.get("mode") == "formal"

    def test_explicit_mode_is_forwarded(self):
        """An explicitly supplied `mode` value is forwarded to translate_doc."""
        captured = {}

        def _capture(input_path, output_path, source_lang, target_lang, mode, **kwargs):
            captured["mode"] = mode
            _fake_translate(input_path, output_path, source_lang, target_lang, mode)

        with patch("app.translate_doc", side_effect=_capture):
            client.post(
                "/translate-doc",
                files={"file": ("test.docx", _make_docx_bytes(["Hello"]), DOCX_MIME)},
                data={"source_lang": "en-IN", "target_lang": "hi-IN", "mode": "colloquial"},
            )
        assert captured.get("mode") == "colloquial"

    def test_languages_are_forwarded(self):
        """source_lang and target_lang are forwarded to translate_doc unchanged."""
        captured = {}

        def _capture(input_path, output_path, source_lang, target_lang, mode, **kwargs):
            captured["source_lang"] = source_lang
            captured["target_lang"] = target_lang
            _fake_translate(input_path, output_path, source_lang, target_lang, mode)

        with patch("app.translate_doc", side_effect=_capture):
            client.post(
                "/translate-doc",
                files={"file": ("test.docx", _make_docx_bytes(["Hello"]), DOCX_MIME)},
                data={"source_lang": "ta-IN", "target_lang": "en-IN"},
            )
        assert captured.get("source_lang") == "ta-IN"
        assert captured.get("target_lang") == "en-IN"

    def test_response_body_is_valid_docx(self):
        """The response body can be parsed as a valid .docx document."""
        with patch("app.translate_doc", side_effect=_fake_translate):
            response = client.post(
                "/translate-doc",
                files={"file": ("test.docx", _make_docx_bytes(["Hello"]), DOCX_MIME)},
                data={"source_lang": "en-IN", "target_lang": "hi-IN"},
            )
        doc = Document(io.BytesIO(response.content))
        texts = [p.text for p in doc.paragraphs if p.text]
        assert texts == ["translated output"]


# ---------------------------------------------------------------------------
# Validation / error tests
# ---------------------------------------------------------------------------

class TestInputValidation:

    def test_missing_file_returns_422(self):
        """Omitting the required `file` field returns HTTP 422."""
        response = client.post(
            "/translate-doc",
            data={"source_lang": "en-IN", "target_lang": "hi-IN"},
        )
        assert response.status_code == 422

    def test_missing_source_lang_returns_422(self):
        """Omitting `source_lang` returns HTTP 422."""
        response = client.post(
            "/translate-doc",
            files={"file": ("test.docx", _make_docx_bytes(["Hello"]), DOCX_MIME)},
            data={"target_lang": "hi-IN"},
        )
        assert response.status_code == 422

    def test_missing_target_lang_returns_422(self):
        """Omitting `target_lang` returns HTTP 422."""
        response = client.post(
            "/translate-doc",
            files={"file": ("test.docx", _make_docx_bytes(["Hello"]), DOCX_MIME)},
            data={"source_lang": "en-IN"},
        )
        assert response.status_code == 422

    def test_translate_doc_exception_returns_500(self):
        """If translate_doc raises, the endpoint returns HTTP 500."""
        with patch("app.translate_doc", side_effect=RuntimeError("Sarvam API error")):
            response = client.post(
                "/translate-doc",
                files={"file": ("test.docx", _make_docx_bytes(["Hello"]), DOCX_MIME)},
                data={"source_lang": "en-IN", "target_lang": "hi-IN"},
            )
        assert response.status_code == 500


# ---------------------------------------------------------------------------
# CORS tests
# ---------------------------------------------------------------------------

class TestCORS:

    def test_allowed_origin_job_joseph(self):
        """Preflight from https://job-joseph.com gets the origin reflected."""
        response = client.options(
            "/translate-doc",
            headers={
                "Origin": "https://job-joseph.com",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert response.headers.get("access-control-allow-origin") == "https://job-joseph.com"

    def test_allowed_origin_www_job_joseph(self):
        """Preflight from https://www.job-joseph.com gets the origin reflected."""
        response = client.options(
            "/translate-doc",
            headers={
                "Origin": "https://www.job-joseph.com",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert response.headers.get("access-control-allow-origin") == "https://www.job-joseph.com"

    def test_disallowed_origin_not_reflected(self):
        """Preflight from an unknown origin does not get an allow-origin header."""
        response = client.options(
            "/translate-doc",
            headers={
                "Origin": "https://evil.example.com",
                "Access-Control-Request-Method": "POST",
            },
        )
        allow_origin = response.headers.get("access-control-allow-origin", "")
        assert allow_origin != "https://evil.example.com"

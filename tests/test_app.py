"""
Integration tests for app.py — FastAPI endpoint behaviour.

These tests use FastAPI's TestClient (backed by httpx) and mock out
`translate_doc` so no real translation or file I/O beyond temp dirs occurs.

Run with:
    pytest tests/test_app.py -v
"""

import io
import os
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient
from docx import Document

# ---------------------------------------------------------------------------
# Provide a dummy API key before the app module is imported, to satisfy the
# module-level guard in both app.py and translate_doc.py (BUG-4).
# ---------------------------------------------------------------------------

os.environ.setdefault("SARVAM_API_KEY", "test-key-for-integration-tests")


def _make_docx_bytes(paragraphs: list[str]) -> bytes:
    """Return a valid .docx file as bytes, ready to POST as a file upload."""
    buf = io.BytesIO()
    doc = Document()
    for para in paragraphs:
        doc.add_paragraph(para)
    doc.save(buf)
    buf.seek(0)
    return buf.read()


# ---------------------------------------------------------------------------
# Fixture: TestClient with translate_doc patched at the app level
# ---------------------------------------------------------------------------

@pytest.fixture()
def client():
    """
    Import and return a TestClient for the FastAPI app, with the SarvamAI
    client patched so no real API calls are made.
    """
    with patch("sarvamai.SarvamAI"):
        import app as app_module
        return TestClient(app_module.app)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestTranslateDocEndpoint:

    def test_valid_request_returns_200_and_docx(self, client):
        """A well-formed request returns HTTP 200 with a .docx content type."""
        docx_bytes = _make_docx_bytes(["Hello"])

        with patch("app.translate_doc") as mock_td:
            # translate_doc writes the output file; simulate that here.
            def _fake_translate(input_path, output_path, **kwargs):
                doc = Document()
                doc.add_paragraph("नमस्ते")
                doc.save(output_path)

            mock_td.side_effect = _fake_translate

            response = client.post(
                "/translate-doc",
                files={"file": ("test.docx", docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
                data={"source_lang": "en-IN", "target_lang": "hi-IN"},
            )

        assert response.status_code == 200
        assert "wordprocessingml.document" in response.headers["content-type"]

    def test_response_filename_is_translated_docx(self, client):
        """The Content-Disposition header specifies the filename as translated.docx."""
        docx_bytes = _make_docx_bytes(["Hello"])

        with patch("app.translate_doc") as mock_td:
            def _fake_translate(input_path, output_path, **kwargs):
                doc = Document()
                doc.add_paragraph("नमस्ते")
                doc.save(output_path)

            mock_td.side_effect = _fake_translate

            response = client.post(
                "/translate-doc",
                files={"file": ("test.docx", docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
                data={"source_lang": "en-IN", "target_lang": "hi-IN"},
            )

        assert "translated.docx" in response.headers.get("content-disposition", "")

    def test_mode_defaults_to_formal(self, client):
        """When `mode` is not supplied, it defaults to 'formal' in the translate_doc call."""
        docx_bytes = _make_docx_bytes(["Hello"])
        captured = {}

        with patch("app.translate_doc") as mock_td:
            def _fake_translate(input_path, output_path, source_lang, target_lang, mode):
                captured["mode"] = mode
                doc = Document()
                doc.add_paragraph("output")
                doc.save(output_path)

            mock_td.side_effect = _fake_translate

            client.post(
                "/translate-doc",
                files={"file": ("test.docx", docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
                data={"source_lang": "en-IN", "target_lang": "hi-IN"},
            )

        assert captured.get("mode") == "formal"

    def test_explicit_mode_is_forwarded(self, client):
        """An explicitly supplied `mode` value is forwarded to translate_doc."""
        docx_bytes = _make_docx_bytes(["Hello"])
        captured = {}

        with patch("app.translate_doc") as mock_td:
            def _fake_translate(input_path, output_path, source_lang, target_lang, mode):
                captured["mode"] = mode
                doc = Document()
                doc.add_paragraph("output")
                doc.save(output_path)

            mock_td.side_effect = _fake_translate

            client.post(
                "/translate-doc",
                files={"file": ("test.docx", docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
                data={"source_lang": "en-IN", "target_lang": "hi-IN", "mode": "colloquial"},
            )

        assert captured.get("mode") == "colloquial"

    def test_languages_are_forwarded(self, client):
        """source_lang and target_lang are forwarded to translate_doc unchanged."""
        docx_bytes = _make_docx_bytes(["வணக்கம்"])
        captured = {}

        with patch("app.translate_doc") as mock_td:
            def _fake_translate(input_path, output_path, source_lang, target_lang, mode):
                captured["source_lang"] = source_lang
                captured["target_lang"] = target_lang
                doc = Document()
                doc.add_paragraph("output")
                doc.save(output_path)

            mock_td.side_effect = _fake_translate

            client.post(
                "/translate-doc",
                files={"file": ("test.docx", docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
                data={"source_lang": "ta-IN", "target_lang": "en-IN"},
            )

        assert captured.get("source_lang") == "ta-IN"
        assert captured.get("target_lang") == "en-IN"

    def test_missing_file_returns_422(self, client):
        """Omitting the required `file` field returns HTTP 422 Unprocessable Entity."""
        response = client.post(
            "/translate-doc",
            data={"source_lang": "en-IN", "target_lang": "hi-IN"},
        )
        assert response.status_code == 422

    def test_missing_source_lang_returns_422(self, client):
        """Omitting `source_lang` returns HTTP 422."""
        docx_bytes = _make_docx_bytes(["Hello"])

        response = client.post(
            "/translate-doc",
            files={"file": ("test.docx", docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
            data={"target_lang": "hi-IN"},
        )
        assert response.status_code == 422

    def test_missing_target_lang_returns_422(self, client):
        """Omitting `target_lang` returns HTTP 422."""
        docx_bytes = _make_docx_bytes(["Hello"])

        response = client.post(
            "/translate-doc",
            files={"file": ("test.docx", docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
            data={"source_lang": "en-IN"},
        )
        assert response.status_code == 422

    def test_translate_doc_exception_returns_500(self, client):
        """If translate_doc raises, the endpoint returns HTTP 500."""
        docx_bytes = _make_docx_bytes(["Hello"])

        with patch("app.translate_doc", side_effect=RuntimeError("Sarvam API error")):
            response = client.post(
                "/translate-doc",
                files={"file": ("test.docx", docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
                data={"source_lang": "en-IN", "target_lang": "hi-IN"},
            )

        assert response.status_code == 500


class TestCORS:

    def test_allowed_origin_returns_cors_header(self, client):
        """A preflight request from an allowed origin returns the correct CORS headers."""
        response = client.options(
            "/translate-doc",
            headers={
                "Origin": "https://job-joseph.com",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert response.headers.get("access-control-allow-origin") == "https://job-joseph.com"

    def test_disallowed_origin_does_not_reflect_origin(self, client):
        """A preflight from an unknown origin does not get an allow-origin header."""
        response = client.options(
            "/translate-doc",
            headers={
                "Origin": "https://evil.example.com",
                "Access-Control-Request-Method": "POST",
            },
        )
        allow_origin = response.headers.get("access-control-allow-origin", "")
        assert allow_origin != "https://evil.example.com"

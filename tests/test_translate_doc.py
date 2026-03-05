"""
Unit tests for translate_doc.py — batching and document-processing logic.

These tests mock the SarvamAI client so they run without a real API key
and make no network calls.

Run with:
    pytest tests/test_translate_doc.py -v
"""

import os
import sys
import tempfile
from unittest.mock import MagicMock, patch

import pytest
from docx import Document

# ---------------------------------------------------------------------------
# Patch the SarvamAI client before translate_doc is imported so that the
# module-level instantiation (BUG-4) does not require a real SARVAM_API_KEY.
# ---------------------------------------------------------------------------

os.environ.setdefault("SARVAM_API_KEY", "test-key-for-unit-tests")

with patch("sarvamai.SarvamAI"):
    from translate_doc import translate_doc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_docx(paragraphs: list[str]) -> str:
    """Write a temporary .docx file containing the given paragraphs and return its path."""
    tmpdir = tempfile.mkdtemp()
    path = os.path.join(tmpdir, "input.docx")
    doc = Document()
    for para in paragraphs:
        doc.add_paragraph(para)
    doc.save(path)
    return path


def _mock_translate_response(text: str) -> MagicMock:
    """Return a mock that mimics the Sarvam API response structure."""
    mock_response = MagicMock()
    mock_response.translated_text = text
    return mock_response


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestTranslateDocBatching:
    """Validate that the 900-character batching logic flushes at the right time."""

    def test_single_short_paragraph(self, tmp_path):
        """A single short paragraph is translated and written to the output."""
        input_path = _make_docx(["Hello world"])
        output_path = str(tmp_path / "out.docx")

        with patch("translate_doc.client") as mock_client:
            mock_client.text.translate.return_value = _mock_translate_response("नमस्ते दुनिया")
            translate_doc(input_path, output_path, "en-IN", "hi-IN", "formal")

        result = Document(output_path)
        texts = [p.text for p in result.paragraphs if p.text]
        assert texts == ["नमस्ते दुनिया"]
        mock_client.text.translate.assert_called_once()

    def test_empty_paragraphs_are_preserved_without_api_call(self, tmp_path):
        """Empty paragraphs are written as blank lines and never sent to the API."""
        input_path = _make_docx(["Hello", "", "World"])
        output_path = str(tmp_path / "out.docx")

        with patch("translate_doc.client") as mock_client:
            mock_client.text.translate.return_value = _mock_translate_response("नमस्ते\nदुनिया")
            translate_doc(input_path, output_path, "en-IN", "hi-IN", "formal")

        # The API should only have been called for the non-empty paragraphs.
        assert mock_client.text.translate.call_count == 1

        result = Document(output_path)
        all_texts = [p.text for p in result.paragraphs]
        # Blank paragraph must be present somewhere in the output.
        assert "" in all_texts

    def test_buffer_flushes_when_limit_exceeded(self, tmp_path):
        """When accumulated text exceeds 900 chars, a flush occurs before adding the next paragraph."""
        # Create two paragraphs whose combined length exceeds 900 characters.
        para_a = "A" * 500
        para_b = "B" * 500  # 500 + 500 = 1000 > 900, so flush is expected mid-loop.
        input_path = _make_docx([para_a, para_b])
        output_path = str(tmp_path / "out.docx")

        with patch("translate_doc.client") as mock_client:
            mock_client.text.translate.return_value = _mock_translate_response("translated")
            translate_doc(input_path, output_path, "en-IN", "hi-IN", "formal")

        # para_a is flushed when para_b would exceed the limit, then para_b is flushed
        # at the end — so exactly 2 API calls are expected.
        assert mock_client.text.translate.call_count == 2

    def test_multiple_short_paragraphs_batched_in_one_call(self, tmp_path):
        """Several short paragraphs that fit within 900 chars are sent in a single API call."""
        paragraphs = [f"Line {i}" for i in range(10)]  # ~70 chars total — well under limit
        input_path = _make_docx(paragraphs)
        output_path = str(tmp_path / "out.docx")

        with patch("translate_doc.client") as mock_client:
            translated = "\n".join([f"पंक्ति {i}" for i in range(10)])
            mock_client.text.translate.return_value = _mock_translate_response(translated)
            translate_doc(input_path, output_path, "en-IN", "hi-IN", "formal")

        mock_client.text.translate.assert_called_once()

    def test_output_file_is_created(self, tmp_path):
        """The output .docx file is written to the specified path."""
        input_path = _make_docx(["Test"])
        output_path = str(tmp_path / "translated.docx")

        with patch("translate_doc.client") as mock_client:
            mock_client.text.translate.return_value = _mock_translate_response("परीक्षण")
            translate_doc(input_path, output_path, "en-IN", "hi-IN", "formal")

        assert os.path.exists(output_path)

    def test_translation_mode_is_forwarded(self, tmp_path):
        """The `mode` parameter is passed through to the Sarvam API call."""
        input_path = _make_docx(["Hello"])
        output_path = str(tmp_path / "out.docx")

        with patch("translate_doc.client") as mock_client:
            mock_client.text.translate.return_value = _mock_translate_response("नमस्ते")
            translate_doc(input_path, output_path, "en-IN", "hi-IN", "colloquial")

        call_kwargs = mock_client.text.translate.call_args.kwargs
        assert call_kwargs.get("mode") == "colloquial"

    def test_source_and_target_language_forwarded(self, tmp_path):
        """source_lang and target_lang are forwarded to the Sarvam API."""
        input_path = _make_docx(["வணக்கம்"])
        output_path = str(tmp_path / "out.docx")

        with patch("translate_doc.client") as mock_client:
            mock_client.text.translate.return_value = _mock_translate_response("Hello")
            translate_doc(input_path, output_path, "ta-IN", "en-IN", "formal")

        call_kwargs = mock_client.text.translate.call_args.kwargs
        assert call_kwargs.get("source_language_code") == "ta-IN"
        assert call_kwargs.get("target_language_code") == "en-IN"

    def test_document_with_only_empty_paragraphs_makes_no_api_call(self, tmp_path):
        """A document containing only blank paragraphs triggers no API calls."""
        input_path = _make_docx(["", "", ""])
        output_path = str(tmp_path / "out.docx")

        with patch("translate_doc.client") as mock_client:
            translate_doc(input_path, output_path, "en-IN", "hi-IN", "formal")

        mock_client.text.translate.assert_not_called()

    def test_exact_900_char_paragraph_is_not_prematurely_flushed(self, tmp_path):
        """A paragraph of exactly 900 characters fits in the buffer and is sent in one call."""
        input_path = _make_docx(["C" * 900])
        output_path = str(tmp_path / "out.docx")

        with patch("translate_doc.client") as mock_client:
            mock_client.text.translate.return_value = _mock_translate_response("translated")
            translate_doc(input_path, output_path, "en-IN", "hi-IN", "formal")

        mock_client.text.translate.assert_called_once()

    def test_paragraph_just_over_900_chars_causes_single_flush(self, tmp_path):
        """
        BUG-2 awareness test: a single 901-char paragraph will be buffered alone
        and flushed in one API call (no split, no error raised by this code).
        """
        input_path = _make_docx(["D" * 901])
        output_path = str(tmp_path / "out.docx")

        with patch("translate_doc.client") as mock_client:
            mock_client.text.translate.return_value = _mock_translate_response("translated")
            translate_doc(input_path, output_path, "en-IN", "hi-IN", "formal")

        # Current behaviour: still sends in one call (no safeguard).
        mock_client.text.translate.assert_called_once()

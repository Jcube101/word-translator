"""
Unit tests for translate_doc.py — batching logic, chunking, and document processing.

The SarvamAI client is supplied via the `client` parameter (dependency injection),
so these tests make no network calls and require no real SARVAM_API_KEY.

Run with:
    pytest tests/test_translate_doc.py -v
"""

import os
import tempfile
from unittest.mock import MagicMock

import pytest
from docx import Document

from translate_doc import translate_doc, _chunk_text

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_docx(paragraphs: list[str]) -> str:
    """Write a temporary .docx file with the given paragraphs; return its path."""
    tmpdir = tempfile.mkdtemp()
    path = os.path.join(tmpdir, "input.docx")
    doc = Document()
    for para in paragraphs:
        doc.add_paragraph(para)
    doc.save(path)
    return path


def _mock_client(translated_text: str) -> MagicMock:
    """Return a mock SarvamAI client whose translate() returns *translated_text*."""
    response = MagicMock()
    response.translated_text = translated_text
    client = MagicMock()
    client.text.translate.return_value = response
    return client


# ---------------------------------------------------------------------------
# _chunk_text unit tests
# ---------------------------------------------------------------------------

class TestChunkText:

    def test_short_text_returned_as_single_chunk(self):
        assert _chunk_text("hello", 900) == ["hello"]

    def test_exact_limit_returned_as_single_chunk(self):
        text = "A" * 900
        assert _chunk_text(text, 900) == [text]

    def test_text_over_limit_is_split(self):
        text = "A" * 1800
        chunks = _chunk_text(text, 900)
        assert len(chunks) == 2
        assert all(len(c) <= 900 for c in chunks)

    def test_split_prefers_whitespace_boundary(self):
        # "hello world" is 11 chars; limit of 7 should split at the space.
        chunks = _chunk_text("hello world", 7)
        assert chunks[0] == "hello"
        assert chunks[1] == "world"

    def test_hard_split_when_no_space(self):
        text = "A" * 20
        chunks = _chunk_text(text, 10)
        assert all(len(c) <= 10 for c in chunks)
        assert "".join(chunks) == text

    def test_reconstructed_text_matches_original_whitespace_split(self):
        words = ["word"] * 300  # 1500 chars with spaces
        text = " ".join(words)
        chunks = _chunk_text(text, 900)
        assert all(len(c) <= 900 for c in chunks)
        # Joining chunks with a space should reconstruct the original.
        assert " ".join(chunks) == text


# ---------------------------------------------------------------------------
# translate_doc unit tests
# ---------------------------------------------------------------------------

class TestTranslateDocBatching:

    def test_single_short_paragraph(self, tmp_path):
        """A single short paragraph is translated and written to the output."""
        input_path = _make_docx(["Hello world"])
        output_path = str(tmp_path / "out.docx")
        client = _mock_client("नमस्ते दुनिया")

        translate_doc(input_path, output_path, "en-IN", "hi-IN", "formal", client=client)

        result = Document(output_path)
        texts = [p.text for p in result.paragraphs if p.text]
        assert texts == ["नमस्ते दुनिया"]
        client.text.translate.assert_called_once()

    def test_empty_paragraphs_preserved_without_api_call(self, tmp_path):
        """Empty paragraphs are written as blank lines and never sent to the API."""
        input_path = _make_docx(["Hello", "", "World"])
        output_path = str(tmp_path / "out.docx")
        client = _mock_client("नमस्ते\nदुनिया")

        translate_doc(input_path, output_path, "en-IN", "hi-IN", "formal", client=client)

        assert client.text.translate.call_count == 1
        result = Document(output_path)
        assert "" in [p.text for p in result.paragraphs]

    def test_buffer_flushes_when_limit_exceeded(self, tmp_path):
        """Two paragraphs that together exceed 900 chars cause two separate API calls."""
        input_path = _make_docx(["A" * 500, "B" * 500])
        output_path = str(tmp_path / "out.docx")
        client = _mock_client("translated")

        translate_doc(input_path, output_path, "en-IN", "hi-IN", "formal", client=client)

        assert client.text.translate.call_count == 2

    def test_multiple_short_paragraphs_batched_in_one_call(self, tmp_path):
        """Several short paragraphs that fit within 900 chars go in a single API call."""
        paragraphs = [f"Line {i}" for i in range(10)]
        input_path = _make_docx(paragraphs)
        output_path = str(tmp_path / "out.docx")
        translated = "\n".join([f"पंक्ति {i}" for i in range(10)])
        client = _mock_client(translated)

        translate_doc(input_path, output_path, "en-IN", "hi-IN", "formal", client=client)

        client.text.translate.assert_called_once()

    def test_output_file_is_created(self, tmp_path):
        """The output .docx file is written to the specified path."""
        input_path = _make_docx(["Test"])
        output_path = str(tmp_path / "translated.docx")
        client = _mock_client("परीक्षण")

        translate_doc(input_path, output_path, "en-IN", "hi-IN", "formal", client=client)

        assert os.path.exists(output_path)

    def test_translation_mode_forwarded(self, tmp_path):
        """The `mode` parameter is passed through to the Sarvam API call."""
        input_path = _make_docx(["Hello"])
        output_path = str(tmp_path / "out.docx")
        client = _mock_client("नमस्ते")

        translate_doc(input_path, output_path, "en-IN", "hi-IN", "colloquial", client=client)

        call_kwargs = client.text.translate.call_args.kwargs
        assert call_kwargs.get("mode") == "colloquial"

    def test_source_and_target_language_forwarded(self, tmp_path):
        """source_lang and target_lang are forwarded to the Sarvam API."""
        input_path = _make_docx(["வணக்கம்"])
        output_path = str(tmp_path / "out.docx")
        client = _mock_client("Hello")

        translate_doc(input_path, output_path, "ta-IN", "en-IN", "formal", client=client)

        call_kwargs = client.text.translate.call_args.kwargs
        assert call_kwargs.get("source_language_code") == "ta-IN"
        assert call_kwargs.get("target_language_code") == "en-IN"

    def test_all_empty_paragraphs_make_no_api_call(self, tmp_path):
        """A document with only blank paragraphs triggers no API calls."""
        input_path = _make_docx(["", "", ""])
        output_path = str(tmp_path / "out.docx")
        client = _mock_client("")

        translate_doc(input_path, output_path, "en-IN", "hi-IN", "formal", client=client)

        client.text.translate.assert_not_called()

    def test_exact_900_char_paragraph_sent_in_one_call(self, tmp_path):
        """A paragraph of exactly 900 characters is sent in a single API call."""
        input_path = _make_docx(["C" * 900])
        output_path = str(tmp_path / "out.docx")
        client = _mock_client("translated")

        translate_doc(input_path, output_path, "en-IN", "hi-IN", "formal", client=client)

        client.text.translate.assert_called_once()

    def test_oversized_single_paragraph_is_chunked(self, tmp_path):
        """BUG-2 fix: a paragraph > 900 chars is split and each chunk sent separately."""
        long_para = "word " * 250  # ~1250 chars; must be chunked
        input_path = _make_docx([long_para.strip()])
        output_path = str(tmp_path / "out.docx")
        client = _mock_client("translated")

        translate_doc(input_path, output_path, "en-IN", "hi-IN", "formal", client=client)

        # Must have made more than one API call because the para exceeds 900 chars.
        assert client.text.translate.call_count > 1
        # Every submitted chunk must be <= 900 chars.
        for call in client.text.translate.call_args_list:
            submitted = call.kwargs.get("input", "")
            assert len(submitted) <= 900

    def test_paragraph_count_mismatch_logs_warning(self, tmp_path, caplog):
        """BUG-3 fix: a mismatch between submitted and returned paragraph counts is logged."""
        import logging
        input_path = _make_docx(["Line one", "Line two"])
        output_path = str(tmp_path / "out.docx")
        # API returns only one line instead of two → mismatch.
        client = _mock_client("Only one line returned")

        with caplog.at_level(logging.WARNING, logger="translate_doc"):
            translate_doc(input_path, output_path, "en-IN", "hi-IN", "formal", client=client)

        assert any("mismatch" in record.message.lower() for record in caplog.records)

    def test_no_api_key_raises_without_client(self, tmp_path, monkeypatch):
        """When no client is provided and SARVAM_API_KEY is absent, an exception is raised."""
        monkeypatch.delenv("SARVAM_API_KEY", raising=False)
        input_path = _make_docx(["Hello"])
        output_path = str(tmp_path / "out.docx")

        with pytest.raises(Exception, match="SARVAM_API_KEY not set"):
            translate_doc(input_path, output_path, "en-IN", "hi-IN", "formal")

import logging
import os

from docx import Document
from dotenv import load_dotenv
from sarvamai import SarvamAI

logger = logging.getLogger(__name__)

load_dotenv()

MAX_CHARS = 900


def _get_client():
    """Create and return a SarvamAI client using the environment API key."""
    api_key = os.getenv("SARVAM_API_KEY")
    if not api_key:
        raise Exception("SARVAM_API_KEY not set")
    return SarvamAI(api_subscription_key=api_key)


def _chunk_text(text: str, max_chars: int) -> list[str]:
    """
    Split *text* into a list of strings each no longer than *max_chars*.

    Splitting is done on whitespace boundaries where possible; if a single
    word exceeds *max_chars* it is split at the hard character limit.
    """
    if len(text) <= max_chars:
        return [text]

    chunks = []
    while text:
        if len(text) <= max_chars:
            chunks.append(text)
            break
        # Try to split on the last space within the limit.
        split_at = text.rfind(" ", 0, max_chars)
        if split_at == -1:
            split_at = max_chars  # No space found; hard split.
        chunks.append(text[:split_at].rstrip())
        text = text[split_at:].lstrip()
    return chunks


def translate_doc(input_path, output_path, source_lang, target_lang, mode, client=None):
    """
    Translate all paragraphs in *input_path* (.docx) and write the result to
    *output_path* (.docx).

    Parameters
    ----------
    input_path  : str  Path to the source Word document.
    output_path : str  Path where the translated document will be saved.
    source_lang : str  BCP-47 language code of the source text (e.g. "en-IN").
    target_lang : str  BCP-47 language code for the output (e.g. "hi-IN").
    mode        : str  Sarvam translation mode (e.g. "formal", "colloquial").
    client      : SarvamAI | None
                       Optional pre-built API client; one is created from the
                       environment when None.  Pass a mock here in tests.
    """
    if client is None:
        client = _get_client()

    doc = Document(input_path)
    new_doc = Document()

    buffer: list[str] = []
    buffer_len: int = 0

    def flush_buffer() -> list[str]:
        if not buffer:
            return []
        text_block = "\n".join(buffer)
        response = client.text.translate(
            input=text_block,
            source_language_code=source_lang,
            target_language_code=target_lang,
            mode=mode,
        )
        result_lines = response.translated_text.split("\n")
        if len(result_lines) != len(buffer):
            logger.warning(
                "Paragraph count mismatch after translation: submitted %d, received %d. "
                "Output document may have a different number of paragraphs than the input.",
                len(buffer),
                len(result_lines),
            )
        return result_lines

    for para in doc.paragraphs:
        text = para.text.strip()

        if not text:
            # Preserve blank lines without sending them to the API.
            new_doc.add_paragraph("")
            continue

        # BUG-2 fix: if a single paragraph is itself longer than MAX_CHARS,
        # split it into sub-chunks so each chunk fits within the limit.
        sub_chunks = _chunk_text(text, MAX_CHARS)

        for chunk in sub_chunks:
            if buffer_len + len(chunk) > MAX_CHARS:
                for translated in flush_buffer():
                    new_doc.add_paragraph(translated)
                buffer.clear()
                buffer_len = 0

            buffer.append(chunk)
            buffer_len += len(chunk)

    # Flush any remaining buffered text.
    for translated in flush_buffer():
        new_doc.add_paragraph(translated)

    new_doc.save(output_path)

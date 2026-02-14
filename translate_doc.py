from docx import Document
from sarvamai import SarvamAI
import os
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("SARVAM_API_KEY")
if not api_key:
    raise Exception("SARVAM_API_KEY not set")

client = SarvamAI(api_subscription_key=api_key)


def translate_doc(input_path, output_path, source_lang, target_lang):
    doc = Document(input_path)
    new_doc = Document()

    MAX_CHARS = 900
    buffer = []
    buffer_len = 0

    def flush_buffer():
        if not buffer:
            return []

        text_block = "\n".join(buffer)

        response = client.text.translate(
            input=text_block,
            source_language_code=source_lang,
            target_language_code=target_lang
        )

        return response.translated_text.split("\n")

    for para in doc.paragraphs:
        text = para.text.strip()

        if not text:
            new_doc.add_paragraph("")
            continue

        if buffer_len + len(text) > MAX_CHARS:
            translated_paras = flush_buffer()
            for t in translated_paras:
                new_doc.add_paragraph(t)

            buffer.clear()
            buffer_len = 0

        buffer.append(text)
        buffer_len += len(text)

    translated_paras = flush_buffer()
    for t in translated_paras:
        new_doc.add_paragraph(t)

    new_doc.save(output_path)
import os
import tempfile
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import FileResponse
from fastapi import BackgroundTasks
from dotenv import load_dotenv
from docx import Document
from sarvamai import SarvamAI
from translate_doc import translate_doc

load_dotenv()

api_key = os.getenv("SARVAM_API_KEY")
if not api_key:
    raise Exception("SARVAM_API_KEY not set")

client = SarvamAI(api_subscription_key=api_key)

app = FastAPI()


@app.post("/translate-doc")
async def translate_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    source_lang: str = Form(...),
    target_lang: str = Form(...)
):
    tmpdir = tempfile.mkdtemp()
    input_path = os.path.join(tmpdir, "input.docx")
    output_path = os.path.join(tmpdir, "translated.docx")

    contents = await file.read()
    with open(input_path, "wb") as f:
        f.write(contents)

    translate_doc(
        input_path,
        output_path,
        source_lang,
        target_lang
    )

    # schedule cleanup AFTER response is sent
    background_tasks.add_task(lambda: os.system(f'rmdir /s /q "{tmpdir}"'))

    return FileResponse(
        output_path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename="translated.docx"
    )


@app.post("/translate-doc")
async def translate_document(
    file: UploadFile = File(...),
    source_lang: str = Form(...),
    target_lang: str = Form(...)
):
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = os.path.join(tmpdir, file.filename)
            output_path = os.path.join(tmpdir, "translated.docx")

            contents = await file.read()
            with open(input_path, "wb") as f:
                f.write(contents)

            translate_doc(
                input_path,
                output_path,
                source_lang,
                target_lang
            )

            return FileResponse(
                output_path,
                media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                filename="translated.docx"
            )
    except Exception as e:
        print("ERROR:", e)
        raise e

    with tempfile.TemporaryDirectory() as tmpdir:
        input_path = os.path.join(tmpdir, file.filename)
        output_path = os.path.join(tmpdir, "translated.docx")

        with open(input_path, "wb") as f:
            f.write(await file.read())

        translate_doc(
            input_path,
            output_path,
            source_lang,
            target_lang
        )

        return FileResponse(
            output_path,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            filename="translated.docx"
        )
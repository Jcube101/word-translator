import os
import tempfile

from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from translate_doc import translate_doc

load_dotenv()

api_key = os.getenv("SARVAM_API_KEY")
if not api_key:
    raise Exception("SARVAM_API_KEY not set")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://job-joseph.com",
        "https://www.job-joseph.com"
    ],
    allow_credentials=True,
    allow_methods=["POST", "OPTIONS"],
    allow_headers=["*"],
)


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

    background_tasks.add_task(
        lambda: os.system(f'rmdir /s /q "{tmpdir}"')
    )

    return FileResponse(
        output_path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename="translated.docx"
    )

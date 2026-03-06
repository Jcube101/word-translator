import asyncio
import logging
import os
import shutil
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor

from docx import Document
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Form, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from translate_doc import translate_doc

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

api_key = os.getenv("SARVAM_API_KEY")
if not api_key:
    raise Exception("SARVAM_API_KEY not set")

# ---------------------------------------------------------------------------
# Configurable limits — set via environment variables or .env
# ---------------------------------------------------------------------------
RATE_LIMIT_PER_MINUTE = os.getenv("RATE_LIMIT_PER_MINUTE", "5")
MAX_FILE_SIZE_BYTES = int(float(os.getenv("MAX_FILE_SIZE_MB", "5")) * 1024 * 1024)
MAX_DOC_CHARS = int(os.getenv("MAX_DOC_CHARS", "50000"))
REQUEST_TIMEOUT_SECONDS = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "120"))

VALID_LANG_CODES = {
    "en-IN", "hi-IN", "ta-IN", "te-IN", "kn-IN", "ml-IN",
    "mr-IN", "gu-IN", "bn-IN", "pa-IN", "as-IN", "od-IN", "ur-IN",
}
VALID_MODES = {"formal", "colloquial"}

_executor = ThreadPoolExecutor()

# ---------------------------------------------------------------------------
# App and middleware
# ---------------------------------------------------------------------------
limiter = Limiter(key_func=get_remote_address)

app = FastAPI()
app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded. Please wait before retrying."},
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://job-joseph.com",
        "https://www.job-joseph.com",
    ],
    allow_credentials=True,
    allow_methods=["POST", "OPTIONS"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------
@app.post("/translate-doc")
@limiter.limit(f"{RATE_LIMIT_PER_MINUTE}/minute")
async def translate_document(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    source_lang: str = Form(...),
    target_lang: str = Form(...),
    mode: str = Form("formal"),
):
    # 1. Validate language codes and mode — zero I/O cost, fail fast
    if source_lang not in VALID_LANG_CODES:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported source_lang '{source_lang}'. "
                   f"Accepted values: {sorted(VALID_LANG_CODES)}",
        )
    if target_lang not in VALID_LANG_CODES:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported target_lang '{target_lang}'. "
                   f"Accepted values: {sorted(VALID_LANG_CODES)}",
        )
    if mode not in VALID_MODES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid mode '{mode}'. Must be one of: {', '.join(sorted(VALID_MODES))}",
        )

    # 2. Read file and check size
    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE_BYTES:
        max_mb = MAX_FILE_SIZE_BYTES / (1024 * 1024)
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is {max_mb:.0f} MB.",
        )

    client_ip = request.client.host if request.client else "unknown"
    logger.info(
        "Request received — ip=%s filename=%s size=%d source=%s target=%s mode=%s",
        client_ip, file.filename, len(contents), source_lang, target_lang, mode,
    )

    # 3. Write to temp dir
    tmpdir = tempfile.mkdtemp()
    input_path = os.path.join(tmpdir, "input.docx")
    output_path = os.path.join(tmpdir, "translated.docx")

    with open(input_path, "wb") as f:
        f.write(contents)

    # 4. Check total document character count (caps API cost per request)
    doc = Document(input_path)
    total_chars = sum(len(p.text) for p in doc.paragraphs if p.text.strip())
    if total_chars > MAX_DOC_CHARS:
        shutil.rmtree(tmpdir, True)
        raise HTTPException(
            status_code=422,
            detail=f"Document too large: {total_chars:,} characters (limit: {MAX_DOC_CHARS:,}).",
        )

    logger.info("Document char count: %d (limit: %d)", total_chars, MAX_DOC_CHARS)
    start = time.monotonic()

    # 5. Run translation in a thread with a timeout
    loop = asyncio.get_running_loop()
    try:
        await asyncio.wait_for(
            loop.run_in_executor(
                _executor,
                lambda: translate_doc(
                    input_path=input_path,
                    output_path=output_path,
                    source_lang=source_lang,
                    target_lang=target_lang,
                    mode=mode,
                ),
            ),
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        shutil.rmtree(tmpdir, True)
        raise HTTPException(
            status_code=504,
            detail="Translation timed out. Please try a smaller document.",
        )
    except Exception as exc:
        shutil.rmtree(tmpdir, True)
        logger.error("Translation failed for ip=%s: %s", client_ip, exc)
        raise HTTPException(
            status_code=500,
            detail="Translation failed due to an internal error. Please try again later.",
        )

    logger.info(
        "Request complete — ip=%s elapsed=%.2fs",
        client_ip, time.monotonic() - start,
    )

    background_tasks.add_task(shutil.rmtree, tmpdir, True)

    return FileResponse(
        output_path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename="translated.docx",
    )

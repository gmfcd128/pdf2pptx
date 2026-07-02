"""FastAPI service wrapping pdf2pptx for use from an ASP.NET Core (or any HTTP)
front end.

Conversion is async/job-based: POST /convert accepts a PDF and returns a job id
immediately; the actual conversion runs on a single background worker (GPU work
is serialized -- one conversion at a time) while the client polls GET
/jobs/{job_id} for status and downloads the result from GET
/jobs/{job_id}/result once done.

Run with:
    uvicorn service.main:app --host 0.0.0.0 --port 8000
"""

import asyncio
import logging
import os
import shutil
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

import torch
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from pdf2pptx import PdfToPptxConverter, PipelineConfig

from .jobs import JobStatus, JobStore

logger = logging.getLogger(__name__)

JOBS_DIR = Path(os.environ.get("PDF2PPTX_JOBS_DIR", "/data/jobs"))
OCR_LANG = os.environ.get("PDF2PPTX_OCR_LANG", "chinese_cht")

converter: Optional[PdfToPptxConverter] = None
job_store = JobStore()
job_queue: "asyncio.Queue[str]" = asyncio.Queue()
# GPU work must be serialized -- max_workers=1 ensures only one conversion runs
# at a time no matter how many requests come in concurrently.
executor = ThreadPoolExecutor(max_workers=1)
_worker_task: Optional[asyncio.Task] = None


async def _worker_loop():
    loop = asyncio.get_running_loop()
    while True:
        job_id = await job_queue.get()
        job = job_store.get(job_id)
        if job is None:
            job_queue.task_done()
            continue
        job.status = JobStatus.PROCESSING
        try:
            def progress_cb(page, total, _job=job):
                _job.progress = f"{page}/{total}"

            await loop.run_in_executor(
                executor, converter.convert, job.input_path, job.output_path, None, progress_cb
            )
            job.status = JobStatus.DONE
        except Exception as exc:
            logger.exception("Job %s failed", job_id)
            job.status = JobStatus.FAILED
            job.error = str(exc)
        finally:
            job_queue.task_done()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global converter, _worker_task
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("Loading OCR/inpainting models (this can take a while on first run)...")
    converter = PdfToPptxConverter(PipelineConfig(ocr_lang=OCR_LANG))
    _worker_task = asyncio.create_task(_worker_loop())
    logger.info("Models loaded, service ready")
    yield
    _worker_task.cancel()


app = FastAPI(title="pdf2pptx", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok", "cuda": torch.cuda.is_available(), "ready": converter is not None}


@app.post("/convert", status_code=202)
async def submit_conversion(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only .pdf uploads are accepted")

    job_id = str(uuid.uuid4())
    job_dir = JOBS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    input_path = job_dir / "input.pdf"
    output_path = job_dir / "output.pptx"

    with input_path.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    job_store.create(job_id, input_path, output_path)
    await job_queue.put(job_id)

    return {"job_id": job_id, "status": JobStatus.QUEUED, "status_url": f"/jobs/{job_id}"}


@app.get("/jobs/{job_id}")
async def get_job(job_id: str):
    job = job_store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown job id")
    return {
        "job_id": job.id,
        "status": job.status,
        "progress": job.progress,
        "error": job.error,
        "result_url": f"/jobs/{job_id}/result" if job.status == JobStatus.DONE else None,
    }


@app.get("/jobs/{job_id}/result")
async def get_job_result(job_id: str):
    job = job_store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown job id")
    if job.status != JobStatus.DONE:
        raise HTTPException(status_code=409, detail=f"Job is not finished yet (status: {job.status})")
    return FileResponse(
        job.output_path,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        filename=job.output_path.name,
    )

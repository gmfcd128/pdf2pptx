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
import json
import logging
import os
import shutil
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np
import torch
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from pdf2pptx import PdfToPptxConverter, PipelineConfig
from pdf2pptx.inpainting import polygon_mask

from .jobs import JobStatus, JobStore
from .pptist import build_slide_json

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

            def page_asset_cb(page_idx, img_rgb, clean_bg_rgb, all_texts, W, H, _job=job):
                # Persists the raw render, the auto-inpainted background, and the
                # reconciled text blocks (as PPTist-ready slide JSON) per page --
                # this is what GET /jobs/{id}/slides and the manual inpaint/
                # restore-region endpoints below read from and write back to.
                # Runs on this same executor thread as the rest of the
                # conversion (only one job processes at a time), so plain
                # synchronous file IO is fine here.
                page_dir = _job.input_path.parent / "pages" / str(page_idx)
                page_dir.mkdir(parents=True, exist_ok=True)
                cv2.imwrite(str(page_dir / "original.png"), cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR))
                cv2.imwrite(str(page_dir / "background.png"), cv2.cvtColor(clean_bg_rgb, cv2.COLOR_RGB2BGR))
                slide = build_slide_json(page_idx, all_texts, W, H, converter.config)
                (page_dir / "slide.json").write_text(json.dumps(slide), encoding="utf-8")

            await loop.run_in_executor(
                executor, converter.convert, job.input_path, job.output_path, None, progress_cb, page_asset_cb
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


class RegionRequest(BaseModel):
    points: List[Tuple[float, float]]


def _require_page_dir(job_id: str, page_index: int) -> Path:
    job = job_store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown job id")
    if job.status != JobStatus.DONE:
        raise HTTPException(status_code=409, detail=f"Job is not finished yet (status: {job.status})")
    page_dir = job.input_path.parent / "pages" / str(page_index)
    if not page_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Unknown page {page_index} for job {job_id}")
    return page_dir


def _page_image_response(job_id: str, page_index: int, filename: str) -> FileResponse:
    page_dir = _require_page_dir(job_id, page_index)
    path = page_dir / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"No {filename} for job {job_id} page {page_index}")
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "no-store"})


@app.get("/")
async def root():
    # This service is a backend-only JSON API meant to sit behind the ASP.NET
    # proxy (web/backend) -- there is no browser UI here. A bare GET / (e.g.
    # someone opening http://localhost:8000 directly instead of the frontend's
    # port) used to 404 with no explanation; this just points them at what
    # actually exists instead.
    return {"service": "pdf2pptx", "docs": "/docs", "health": "/health"}


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
        "slides_url": f"/jobs/{job_id}/slides" if job.status == JobStatus.DONE else None,
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


@app.get("/jobs/{job_id}/slides")
async def get_job_slides(job_id: str):
    job = job_store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown job id")
    if job.status != JobStatus.DONE:
        raise HTTPException(status_code=409, detail=f"Job is not finished yet (status: {job.status})")

    pages_dir = job.input_path.parent / "pages"
    if not pages_dir.is_dir():
        raise HTTPException(status_code=404, detail="No page data for this job")

    slides = []
    for page_dir in sorted(pages_dir.iterdir(), key=lambda p: int(p.name)):
        slide_json_path = page_dir / "slide.json"
        if not slide_json_path.exists():
            continue
        slide = json.loads(slide_json_path.read_text(encoding="utf-8"))
        idx = slide["page_index"]
        bg_path = page_dir / "background.png"
        slide["background_path"] = f"pages/{idx}/background.png"
        slide["background_version"] = int(bg_path.stat().st_mtime * 1000)
        slide["original_path"] = f"pages/{idx}/original.png"
        slides.append(slide)

    # Both derived from the same PipelineConfig the slides themselves were
    # built with (see pptist.py's units_per_inch), not hardcoded -- the web
    # editor's client-side PPTX export (useExport.ts) needs canvas_width_in
    # to convert PPTist's fixed 1000-unit-wide canvas back into the same
    # real inches pptist.py used to place these elements; a mismatched
    # constant here is what silently made every exported box too narrow for
    # its own text.
    config = converter.config
    return {
        "viewport_ratio": config.slide_h_in / config.slide_w_in,
        "canvas_width_in": config.slide_w_in,
        "slides": slides,
    }


@app.get("/jobs/{job_id}/pages/{page_index}/background.png")
async def get_page_background(job_id: str, page_index: int):
    return _page_image_response(job_id, page_index, "background.png")


@app.get("/jobs/{job_id}/pages/{page_index}/original.png")
async def get_page_original(job_id: str, page_index: int):
    return _page_image_response(job_id, page_index, "original.png")


@app.post("/jobs/{job_id}/pages/{page_index}/inpaint")
async def inpaint_page_region(job_id: str, page_index: int, body: RegionRequest):
    """Re-inpaints a user-drawn quadrilateral, always sourced from the page's
    current background (whatever the last auto-inpaint or manual edit left
    there) -- restoring original pixels instead is a separate, distinct
    action (see restore_page_region below), not a source choice on this one.
    """
    if len(body.points) != 4:
        raise HTTPException(status_code=400, detail="points must contain exactly 4 [x, y] pairs")

    page_dir = _require_page_dir(job_id, page_index)
    bg_path = page_dir / "background.png"
    if not bg_path.exists():
        raise HTTPException(status_code=404, detail=f"No background.png for job {job_id} page {page_index}")

    img_bgr = cv2.imread(str(bg_path))
    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    H, W = img_rgb.shape[:2]

    loop = asyncio.get_running_loop()
    # Shares the single-worker executor with ordinary conversion jobs -- LaMa
    # inpainting is GPU work and must stay serialized with everything else that
    # touches the model, not just with other manual-inpaint calls.
    result_rgb = await loop.run_in_executor(
        executor, converter.inpainter.clean_polygon, img_rgb, body.points, W, H, converter.config
    )

    cv2.imwrite(str(bg_path), cv2.cvtColor(result_rgb, cv2.COLOR_RGB2BGR))
    return {
        "background_path": f"pages/{page_index}/background.png",
        "background_version": int(bg_path.stat().st_mtime * 1000),
    }


@app.post("/jobs/{job_id}/pages/{page_index}/restore-region")
async def restore_page_region(job_id: str, page_index: int, body: RegionRequest):
    """Copies the original (pre-inpaint) page render's pixels into a
    user-drawn quadrilateral on the current background -- a plain pixel
    composite, no LaMa involved, for undoing auto/manual inpainting in just
    that region rather than the whole page.
    """
    if len(body.points) != 4:
        raise HTTPException(status_code=400, detail="points must contain exactly 4 [x, y] pairs")

    page_dir = _require_page_dir(job_id, page_index)
    original_path = page_dir / "original.png"
    bg_path = page_dir / "background.png"
    if not original_path.exists():
        raise HTTPException(status_code=404, detail=f"No original render for job {job_id} page {page_index}")
    if not bg_path.exists():
        raise HTTPException(status_code=404, detail=f"No background.png for job {job_id} page {page_index}")

    original = cv2.imread(str(original_path))
    current = cv2.imread(str(bg_path))
    H, W = original.shape[:2]

    mask_3ch = cv2.cvtColor(polygon_mask(body.points, W, H), cv2.COLOR_GRAY2BGR)
    result = np.where(mask_3ch > 0, original, current)

    cv2.imwrite(str(bg_path), result)
    return {
        "background_path": f"pages/{page_index}/background.png",
        "background_version": int(bg_path.stat().st_mtime * 1000),
    }

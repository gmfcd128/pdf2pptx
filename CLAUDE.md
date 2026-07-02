# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A reusable pipeline that converts an image-flattened PDF (each page a flattened image with a thin layer of native PDF text on top) into a fully editable PPTX where every piece of visible text becomes a real, positioned, editable text box, and the original background graphics are preserved with the text cleanly erased.

It was built and tuned against `台南空品預警計畫架構與執行藍圖報告v4.pdf` (a Tainan air-quality early-warning project report), which remains in the repo as the reference/test document, but the pipeline itself takes an arbitrary input PDF and output path — it is not hardcoded to that file.

Three ways to use it:
- **`pdf2pptx/`** — the core library. Import `PdfToPptxConverter` and call `.convert(pdf_path, output_pptx_path)`.
- **`python -m pdf2pptx.cli input.pdf output.pptx`** — CLI over the same library, for local/manual one-off conversions.
- **`service/`** — a FastAPI HTTP service over the same library, meant to run in a container alongside an ASP.NET Core web front end (see "Containerized service" below).
- **`convert.py`** — thin convenience wrapper preserving the original no-arg `python convert.py` workflow against the bundled reference PDF.

There is no test suite. Dependencies are listed in `requirements.txt` (minus `torch`/`torchvision`, which need a CUDA-specific index URL — see below).

## Running it

Local, one-off, arbitrary file:
```
python -m pdf2pptx.cli input.pdf output.pptx
```

Local, bundled reference document (matches the old workflow):
```
python convert.py
```

Fully local — no API key or network dependency for OCR. Requires an NVIDIA GPU for reasonable performance (both PaddleOCR and LaMa inpainting run on CUDA via PyTorch; falls back to CPU/classical inpainting if unavailable). A full 23-page run takes roughly 1-3 minutes.

### Dependencies
See `requirements.txt` for everything except `torch`/`torchvision`, which need a CUDA build installed separately, e.g.:
```
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
```
(The Docker image's base already bundles a matching torch/CUDA/cuDNN build, so this step only applies to local installs.)

`simple-lama-inpainting` downloads its model checkpoint (`big-lama.pt`, ~200MB) from GitHub on first use; PaddleOCR downloads its PP-OCRv6 detection/recognition checkpoints on first use. Both are cached locally afterward (see the Dockerfile's `HF_HOME`/`TORCH_HOME`/`PADDLE_PDX_CACHE_HOME` for where that cache lives in the container).

## Pipeline (`pdf2pptx/`)

1. **Render** each PDF page via PyMuPDF at `PipelineConfig.zoom = 1.5` → ~1920×1080 (`pipeline.py`). This intentionally matches this document family's native detail (page size 1280×720 pts; embedded background image only ~1376×768px) rather than oversampling — an earlier version rendered at 4x (5120×2880), which quadrupled file size for zero real visual gain. A source PDF with genuinely higher-resolution backgrounds should use a higher `zoom`.
2. **Extract native text** (`native_text.extract_native_text`) — PyMuPDF vector text spans (position/font/color), pixel-perfect wherever it exists. Typically just page numbers on image-heavy pages, but full paragraphs on text-heavy pages.
3. **OCR the rest via PaddleOCR** (`ocr.OcrEngine.extract`) — one local `PaddleOCR.predict()` call per page (PP-OCRv6, `engine="transformers"`, see below) returning per-line boxes, text, and a real confidence score for each. Boxes below `PipelineConfig.ocr_min_conf` (default 0.8) or that look like symbol garbage (`text_utils.looks_like_garbage`) are dropped. PaddleOCR doesn't report font size or color, so both are derived: `ocr.sample_text_color` averages the darkest ~15% of pixels in the box (recovers colored headings, e.g. dark green, instead of flattening everything to black), and font size is estimated from box height.
4. **Reconcile native vs. OCR** (`reconcile.reconcile_native_and_ocr`) — a native line and an OCR box can overlap either because they're two detections of the same line (comparable size — keep the pixel-accurate native line, drop the OCR duplicate) or because the OCR box is a much larger block that happens to contain the native line as one small piece of it (keep the larger OCR block instead, since it has strictly more information; dropping it — the naive approach — silently throws away the rest of that text and leaves it unmasked/un-erased in the background). Told apart by relative box size (`PipelineConfig.size_ratio_thresh`, `containment_thresh`).
5. **Erase text from the background** (`inpainting.Inpainter.clean`) — build a mask from every accepted text box, padded by `max(mask_min_pad, mask_pad_frac * box height)`, then inpaint with LaMa (GPU neural inpainting via `simple-lama-inpainting`). Downscaled to `PipelineConfig.lama_max_dim` (default 2200) first if needed to bound VRAM use, then the result is force-resized back to the exact source `(W, H)` — LaMa pads its input to a multiple of 8 internally and doesn't always crop the output back down, so without this the background image and the text-box coordinate system silently drift apart by a few pixels.
6. **Assemble the PPTX** (`pipeline.PdfToPptxConverter.convert`) — one 16:9 slide per page via `python-pptx`: the inpainted image as a full-bleed background picture, then every text block as a native `add_textbox` (`slide_builder.add_text_box`) with font size/color/name set directly.

`PdfToPptxConverter.__init__` loads PaddleOCR and LaMa once (model load is expensive) — construct one instance per process and reuse it across every document/page, rather than constructing a fresh one per conversion. This matters most in the service, which loads the converter once at startup and reuses it for every job.

### Why PaddleOCR, and why its `transformers` engine specifically

Two other engines were tried and abandoned first:
- **EasyOCR** (tiled multi-pass local detection + recognition): fragmented lines mixing CJK and Latin script, and needed increasingly fragile confidence/merge heuristics to work around it.
- **Google Gemini** (cloud, whole page in one JSON-schema request): excellent accuracy and correct line-grouping, but 2 API calls per page (needed for reliable recall — a single call would stochastically omit whole legible blocks) made per-page latency unacceptable for this many pages.

**PaddleOCR** (PP-OCRv6) reads full, unfragmented lines directly and runs in ~1-2s/page locally on GPU, including on the densest chart page that gave the other two trouble. Its recognition has more character-level misreads than Gemini's did (an accepted speed-for-accuracy tradeoff — e.g. occasional simplified/traditional Chinese mixing, or a visually similar character substituted).

Getting a working local install on Windows/Python 3.14 took a specific path, worth knowing before touching this dependency:
- PaddleOCR 3.x requires PaddlePaddle ≥ 3.0, which **has no Windows wheel at all** — every PaddlePaddle package index (PyPI and PaddlePaddle's own) stops Windows builds at 2.6.x, GPU or CPU.
- Downgrading to the PaddleOCR 2.x line (which does work with PaddlePaddle 2.6.x) hits a different wall: PaddlePaddle's Windows GPU wheel needs a **system-wide CUDA 12.0 + cuDNN 8.9.1 install** that isn't pip-installable (unlike PyTorch, which bundles its own CUDA/cuDNN inside the wheel) — cuDNN specifically requires a manual download from NVIDIA's developer portal.
- The fix: PaddleOCR 3.x's `engine="transformers"` constructor argument (used in `ocr.OcrEngine.__init__`) runs the PP-OCRv6 models through Hugging Face Transformers on the **existing PyTorch/CUDA install already used for LaMa**, with no PaddlePaddle involved at all. This is why PaddleOCR is installed directly into the main Python environment rather than a separate venv — and why the Linux container base image can be a plain PyTorch CUDA image with no PaddlePaddle installed at all.

### Known limitation

On the densest infographic/chart page, a handful of very small chart-legend glyphs are still occasionally misread as plausible-but-wrong short CJK strings rather than being correctly skipped — likely below the resolution at which any current OCR engine (local or cloud) can reliably read them. This was confirmed consistent across every engine tried (EasyOCR, Gemini, PaddleOCR alike). `looks_like_garbage` and `ocr_min_conf` catch most of it but not all.

## Containerized service (`service/`)

`service/main.py` is a FastAPI app meant to run in a container as the conversion backend for an ASP.NET Core (or any HTTP) front end. It is **async/job-based**, not synchronous, because a single conversion takes 1-3 minutes on GPU:

- `POST /convert` (multipart PDF upload) → `202` with `{job_id, status, status_url}`, and enqueues the job.
- `GET /jobs/{job_id}` → `{status: queued|processing|done|failed, progress, error, result_url}`.
- `GET /jobs/{job_id}/result` → the finished `.pptx` file, once `status == done`.
- `GET /health` → `{status, cuda, ready}`, for container orchestration liveness/readiness checks.

Models are loaded **once at startup** (`PdfToPptxConverter` constructed in the FastAPI `lifespan` handler) and reused for every job. GPU work is **serialized** through a single-worker `ThreadPoolExecutor` + `asyncio.Queue` — only one conversion runs at a time regardless of how many requests arrive concurrently, since PaddleOCR/LaMa share one GPU. The ASP.NET Core side is expected to: POST the PDF, poll (or long-poll) the status endpoint, then GET the result once done.

The in-memory `JobStore` (`service/jobs.py`) and in-process queue are fine for a single-replica container. If this is ever scaled to multiple replicas, both need to move to a shared backend (e.g. Redis) — a single GPU-bound worker per replica doesn't compose across replicas without that.

Job working files live under `PDF2PPTX_JOBS_DIR` (env var, default `/data/jobs` in the container) as `{job_id}/input.pdf` and `{job_id}/output.pptx`. Model checkpoint caches (`HF_HOME`, `TORCH_HOME`, `PADDLE_PDX_CACHE_HOME`) are pointed at `/data/model_cache/...` — mount `/data` as a persistent volume so checkpoints aren't re-downloaded on every container restart/rebuild.

Build and run:
```
docker build -t pdf2pptx .
docker run --gpus all -p 8000:8000 -v pdf2pptx_data:/data pdf2pptx
```
(`--gpus all` requires the NVIDIA Container Toolkit on the host; omit it to fall back to CPU.)

## Repo layout

- `pdf2pptx/` — the core library (config, text extraction, OCR, reconciliation, inpainting, slide assembly, pipeline orchestrator, CLI).
- `service/` — FastAPI job service wrapping the library for container/ASP.NET Core use.
- `convert.py` — thin wrapper preserving the original no-arg local workflow against the bundled reference PDF.
- `Dockerfile`, `.dockerignore`, `requirements.txt` — container packaging.
- `台南空品預警計畫架構與執行藍圖報告v4.pdf` — reference/test input.
- `台南空品預警計畫架構與執行藍圖報告v4.pptx` — reference output (overwritten by `python convert.py`).
- `output_backgrounds/` — per-page inpainted background PNGs from the last `convert.py` run; regenerated scratch output (embedded into the pptx, not referenced by it afterward — safe to delete between runs). The library and service instead use a temp directory per conversion unless `background_dir` is explicitly passed.

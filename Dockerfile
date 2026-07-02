# Base image bundles a matching torch + CUDA + cuDNN build so PaddleOCR's
# "transformers" engine and LaMa (both PyTorch-based) run on GPU with no
# separate CUDA toolkit/cuDNN install needed. Update the tag if you need a
# different CUDA version to match your host's NVIDIA driver / container runtime.
FROM pytorch/pytorch:2.4.1-cuda12.1-cudnn9-runtime

# Minimal system libs OpenCV needs at import/encode time. libgl1 specifically is
# for libGL.so.1: requirements.txt only lists opencv-python-headless directly,
# but paddleocr's paddlex[ocr-core] extra pulls in plain opencv-contrib-python
# transitively (it needs GL-dependent modules headless doesn't ship), and
# whichever `cv2` ends up resolved needs libGL.so.1 present even though nothing
# here does GUI rendering.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libglib2.0-0 libsm6 libxext6 libxrender1 libgomp1 libgl1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# The base image's bundled torch (cu121, matching the FROM tag above) has no
# compiled kernels for newer GPU architectures -- e.g. RTX 50-series/Blackwell
# (compute capability 12.x) fails with "CUDA error: no kernel image is
# available for execution on the device" even though CUDA itself is visible.
# This mirrors the exact fix CLAUDE.md documents for local (non-Docker)
# installs on such GPUs: reinstall torch/torchvision from the cu128 wheel
# index, which does carry those kernels and remains compatible with older
# GPUs too. If you know your deployment target's GPU is already covered by
# the base image's own cu121 torch, this extra ~2.5GB layer can be dropped.
# --force-reinstall is required, not optional: pip sees "torch" is already
# satisfied by the base image's existing 2.4.1+cu121 install (pip matches by
# package name/version, not CUDA build variant) and silently no-ops without it,
# leaving the incompatible cu121 build in place. Deliberately *not* --no-deps:
# this torch is a much newer major version than the base image's, and pulls in
# at least one CUDA library package (nvidia-cusparselt-cu12) the older torch
# didn't depend on at all -- skipping dependency resolution leaves that missing
# and torch fails to import (libcusparseLt.so.0: cannot open shared object).
RUN pip install --no-cache-dir --force-reinstall torch torchvision \
        --index-url https://download.pytorch.org/whl/cu128

# The base image also bundles torchaudio (2.4.1+cu121, unused by this project --
# nothing here processes audio), which the reinstall above leaves in place at
# its old version since it's not one of the two packages named. Its compiled
# extension is linked against the *old* torch's ABI, so once torch itself is
# upgraded it fails to load (OSError: Could not load this library:
# .../libtorchaudio.so) -- and transformers (paddleocr's "transformers" engine)
# transitively imports torchaudio from an unrelated audio-model code path
# (loss_rnnt.py) as a side effect of just importing transformers at all,
# crashing the whole service on startup. Uninstalling it outright makes that
# import a clean "not installed" (ModuleNotFoundError), which transformers'
# lazy-loading already handles gracefully as an optional dependency, instead of
# a hard ABI-mismatch crash.
RUN pip uninstall -y torchaudio

COPY pdf2pptx/ pdf2pptx/
COPY service/ service/

# PaddleOCR/HF/torch model checkpoints download on first use (~200MB+ total) and
# are cached under these dirs afterward -- point them at a mounted volume so
# they survive container restarts/rebuilds instead of re-downloading every time.
ENV HF_HOME=/data/model_cache/huggingface \
    TORCH_HOME=/data/model_cache/torch \
    PADDLE_PDX_CACHE_HOME=/data/model_cache/paddlex \
    PDF2PPTX_JOBS_DIR=/data/jobs \
    PDF2PPTX_OCR_LANG=chinese_cht

VOLUME ["/data"]
EXPOSE 8000

CMD ["uvicorn", "service.main:app", "--host", "0.0.0.0", "--port", "8000"]

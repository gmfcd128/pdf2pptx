# Deployment Guide

This deploys the full web stack — Vue frontend, ASP.NET Core backend, and the
Python GPU conversion service — on a fresh machine using Docker Compose. If
you only want the bare Python conversion API (no browser UI), see the
"Containerized service" section in `CLAUDE.md` instead; this guide covers the
three-container stack in `docker-compose.yml`.

## 1. Prerequisites

### Required on every machine
- **Docker Desktop** (Windows/macOS) or **Docker Engine + the Compose plugin**
  (Linux). Verify with:
  ```
  docker --version
  docker compose version
  ```
  (`docker-compose` with a hyphen, the old standalone binary, also works but
  isn't what these instructions assume.)
- **~30GB free disk space.** The Python service's image alone is **~22GB**
  (it bundles the full CUDA 12.8 toolkit, PyTorch, and PaddleOCR/paddlex — see
  "Why is the image so large?" below), and the first build leaves a similar
  amount in Docker's build cache on top of that.
- **A few GB of free RAM** beyond what your OS/other apps need. 8GB+ total
  system RAM is a reasonable floor; the containers themselves are not
  RAM-heavy, but model loading briefly spikes usage.

### Optional but strongly recommended: an NVIDIA GPU
The pipeline runs on CPU if no GPU is available, but a full document that
takes ~1-3 minutes on a GPU (RTX 5050 8GB laptop-class or better) will take
substantially longer on CPU. If you have an NVIDIA GPU:

- **Windows (Docker Desktop):** Install/update your NVIDIA driver (any
  reasonably recent Game Ready or Studio driver), then enable GPU support in
  Docker Desktop: **Settings → Resources → WSL Integration**, and ensure
  WSL2 is your backend (**Settings → General → Use the WSL 2 based engine**).
  Docker Desktop's WSL2 integration exposes the GPU to containers
  automatically — no separate CUDA toolkit or NVIDIA Container Toolkit install
  is needed on Windows.
- **Linux:** Install the
  [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)
  and restart the Docker daemon (`sudo systemctl restart docker`) after
  installing it.
- Verify Docker can see your GPU *before* touching this project:
  ```
  docker run --rm --gpus all nvidia/cuda:12.6.0-base-ubuntu22.04 nvidia-smi
  ```
  (if that exact tag has been pruned from Docker Hub by the time you read
  this, any other `nvidia/cuda:*-base-*` tag works just as well for this
  check — you're only testing that Docker can hand the GPU to a container at
  all, not testing this project's own image). If this prints a GPU table,
  you're set. If it errors, fix that first —
  the app-level symptoms of a broken GPU passthrough (falling back to CPU, or
  a `CUDA error: no kernel image is available for execution on the device` if
  your GPU is newer than the toolkit expects) are harder to diagnose than this
  one direct check.

**No GPU, or don't want to bother with passthrough?** Skip straight to
section 2 — `docker-compose.yml`'s GPU reservation block is easy to remove
(see "Running without a GPU" below) and the pipeline works fine on CPU.

## 2. Get the code

Clone or copy the repository onto the target machine, e.g.:
```
git clone <your-repo-url> pdf2pptx
cd pdf2pptx
```
(If you don't have git set up as a repo yet, just copy the project directory
across — nothing in the build process depends on git itself.)

## 3. Build and start the stack

From the repository root (where `docker-compose.yml` lives):
```
docker compose up --build -d
```

**Expect this to take a long time on the first run** — realistically
15-40 minutes depending on internet speed, almost all of it building the
Python service's image (pulling the CUDA base image, then downloading and
installing PyTorch's CUDA 12.8 wheels and PaddleOCR's dependencies, several
GB of downloads total). The `.NET` and Vue images build in under a couple of
minutes each and won't be the bottleneck.

Subsequent builds (after a code change) are much faster — Docker reuses
cached layers for anything that hasn't changed, typically only re-running the
last one or two steps.

### Why is the image so large?
The base `pytorch/pytorch` image ships an older CUDA/PyTorch build that
doesn't include compute kernels for newer GPUs (e.g. RTX 50-series). The
Dockerfile reinstalls PyTorch from the CUDA 12.8 wheel index to fix that,
which pulls in the full CUDA 12.8 toolkit as a Python dependency (~10GB by
itself) on top of the base image. This is a one-time cost per machine — it's
not re-downloaded on every build, and the final running container's actual
memory/VRAM footprint is nowhere near 22GB (see `CLAUDE.md`'s pipeline
section — a real conversion uses a few GB of VRAM at most).

### Running without a GPU
If you don't have an NVIDIA GPU, or skipped the passthrough setup, remove (or
comment out) this block from `pdf2pptx-service` in `docker-compose.yml`
before running `docker compose up --build -d`:
```yaml
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
```
Leaving it in place on a machine without a working GPU/driver will make the
container fail to start; the pipeline itself doesn't need this block to fall
back to CPU, it's purely how Compose reserves the GPU for the container.

## 4. Verify it's running

```
docker compose ps
```
All three containers (`pdf2pptx-service`, `pdf2pptx-backend`,
`pdf2pptx-frontend`) should show `Up`, and `pdf2pptx-service` should show
`(healthy)` once its startup healthcheck passes (can take up to a minute or
two on first boot while models load — see `start_period` in
`docker-compose.yml`).

Then check each layer directly:

```powershell
# PowerShell
Invoke-RestMethod http://localhost:8000/health   # Python service directly
Invoke-RestMethod http://localhost:5080/api/health  # backend -> confirms it can reach the Python service
Invoke-WebRequest http://localhost:5173/ -UseBasicParsing  # frontend, expect 200
```
```bash
# bash
curl http://localhost:8000/health
curl http://localhost:5080/api/health
curl -I http://localhost:5173/
```

`http://localhost:8000/health` should report `"cuda": true` if GPU passthrough
worked, or `"cuda": false` if running on CPU (both are valid, just different
performance). `http://localhost:5080/api/health` should report
`"conversionServiceReachable": true` — if it's `false`, the backend container
can't reach the Python container over the internal Docker network (check
`docker compose logs pdf2pptx-backend` and confirm `pdf2pptx-service` is
healthy first).

## 5. Use it

Open **http://localhost:5173** in a browser. Drag and drop (or select) a PDF,
wait for it to process (progress updates roughly every 2 seconds), then
download the resulting `.pptx`.

## 6. Common operations

| Task | Command |
|---|---|
| View logs (all services) | `docker compose logs -f` |
| View logs (one service) | `docker compose logs -f pdf2pptx-service` |
| Stop everything (keep data) | `docker compose stop` |
| Start again | `docker compose start` |
| Stop and remove containers (keep data volume) | `docker compose down` |
| Full teardown, including cached models/job files | `docker compose down -v` |
| Rebuild after pulling code changes | `docker compose up --build -d` |
| Rebuild just one service | `docker compose up --build -d pdf2pptx-service` |

**Updating to newer code**: pull/copy the new source, then
`docker compose up --build -d` again. This rebuilds only what changed — a
`pdf2pptx/` or `service/` code change rebuilds quickly (the expensive
CUDA/PyTorch layer is cached and won't re-download) unless `requirements.txt`
itself changed.

**Model checkpoints and job files persist** in the named Docker volume
declared as `pdf2pptx_data` in `docker-compose.yml` (Compose actually creates
it as `<project-name>_pdf2pptx_data`, where `<project-name>` defaults to
whatever your project directory is called — run `docker volume ls` to see the
exact name) across `docker compose down` / `up` cycles and container
rebuilds. It's only lost if you explicitly run `docker compose down -v` (the
`-v` removes volumes too) or `docker volume rm <that-name>`. This means a
second `docker compose up` on the same machine skips the ~200MB checkpoint
download and starts in seconds, even after a full image rebuild.

## 7. Troubleshooting

**`pdf2pptx-service` never becomes healthy / exits immediately.**
Check its logs: `docker compose logs pdf2pptx-service`. The two most likely
causes, both already worked around in this project's `Dockerfile` but worth
knowing if you're debugging a modified version:
- GPU reservation configured but no working GPU/driver on the host — remove
  the `deploy` block (see section 3) or fix the GPU passthrough (section 1).
- `CUDA error: no kernel image is available for execution on the device` —
  your GPU is newer than the installed CUDA build supports. The Dockerfile
  already pins a CUDA 12.8 PyTorch build specifically to cover recent GPUs;
  if you still hit this on unusually new hardware, a newer wheel index may be
  needed (see the comments in `Dockerfile`).

**Port already in use.**
Something else on the host is already bound to 8000, 5080, or 5173. Either
stop that other process, or change the *left* side of the port mapping in
`docker-compose.yml` (e.g. `"18000:8000"` to expose the Python service on
18000 instead) — the right side (container-internal port) should stay as-is
since the other containers reference it internally.

**Upload fails with a size/413 error.**
The stack is configured for up to 200MB uploads (Kestrel, ASP.NET Core's own
`RequestSizeLimit`, and nginx's `client_max_body_size` are all set to 200MB —
see `web/backend/Pdf2Pptx.Api/Controllers/ConversionsController.cs` and
`web/frontend/nginx.conf`). A larger file needs all three raised together.

**Conversion stuck on "queued" forever.**
The Python service only runs one conversion at a time by design (GPU work is
serialized — see `CLAUDE.md`). Check `docker compose logs pdf2pptx-service`
for a stuck/crashed worker; restarting the container
(`docker compose restart pdf2pptx-service`) clears a stuck queue, though any
in-flight job is lost.

**First request to a freshly-built container is slow.**
Expected — the Python service downloads its OCR/inpainting model checkpoints
(~200MB+) on first use if they aren't already in the `pdf2pptx_data` volume,
then loads them into memory/GPU. This happens once per machine, not once per
container restart (see the persistence note in section 6).

## 8. Security note

This stack has **no authentication** and is intended for use on a trusted
internal network, not direct exposure to the public internet. If you need to
expose it externally, put it behind a reverse proxy or gateway that handles
authentication/TLS — none of the three containers here are configured for
that themselves.

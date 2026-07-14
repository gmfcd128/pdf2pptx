import logging

import cv2
import numpy as np
import torch
from PIL import Image
from simple_lama_inpainting import SimpleLama

logger = logging.getLogger(__name__)


def _detect_grid_lines(img_rgb, mask, W, H, config):
    """Detect straight background edges worth restoring after erasure, returning a
    list of (x1, y1, x2, y2) segments -- see PipelineConfig.protect_grid_lines for
    why these get special treatment.

    A table gridline and a small icon/card outline are the same underlying problem
    at different scales: both are precise straight edges that a text box's erasure
    mask can partially cover, and LaMa's reconstruction doesn't reliably keep a
    straight edge straight through a masked gap. What tells either of them apart
    from a text stroke -- which Canny/Hough will also happily find -- isn't length,
    it's that most of a real edge's pixels lie *outside* the mask (it's a
    persistent feature the mask only clips a piece of), whereas a text stroke lives
    entirely inside its own glyph's mask. So instead of requiring a line to span
    some fraction of the page (which misses small icon borders entirely), keep any
    candidate line whose pixels are mostly unmasked.

    A second check guards against a different false positive: a spot the mask
    *didn't* cover -- a stray already-unerased fragment, e.g. from an upstream
    text-detection gap -- is by definition "unmasked" too, and a candidate line
    that happens to graze one would otherwise get accepted and then smear that
    fragment's color across the whole restored line. A genuine edge has a
    consistent color along all of its unmasked sample points (it's one border,
    one color); a line whose unmasked samples mix that fragment's color with
    plain surrounding background does not, so reject high-variance candidates.
    """
    gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(gray, 30, 100)
    lines = cv2.HoughLinesP(
        edges, 1, np.pi / 180, threshold=40, minLineLength=config.grid_line_min_len_px, maxLineGap=10
    )
    if lines is None:
        return []
    segments = []
    for x1, y1, x2, y2 in lines[:, 0]:
        is_vertical = abs(x1 - x2) <= 2
        is_horizontal = abs(y1 - y2) <= 2
        if not (is_vertical or is_horizontal):
            continue
        length = max(abs(int(x2) - int(x1)), abs(int(y2) - int(y1)))
        if length < config.grid_line_min_len_px:
            continue
        n = max(2, length // 3)
        xs = np.clip(np.linspace(x1, x2, n).round().astype(int), 0, W - 1)
        ys = np.clip(np.linspace(y1, y2, n).round().astype(int), 0, H - 1)
        known = mask[ys, xs] == 0
        if known.mean() < config.grid_line_min_unmasked_frac:
            continue
        known_colors = img_rgb[ys[known], xs[known]].astype(np.float64)
        if known_colors.shape[0] < 2 or known_colors.std(axis=0).mean() > config.grid_line_max_color_std:
            continue
        segments.append((int(x1), int(y1), int(x2), int(y2)))
    return segments


def _extend_to_mask_run(mask_1d, lo0, hi0, margin):
    """Grow [lo0, hi0] out to cover the full contiguous masked run(s) it touches,
    plus a margin. A small icon's border can sit so close to its own text that the
    text mask (plus padding) covers almost the whole Hough-detected fragment of
    that border, leaving that fragment with barely any unmasked anchor pixels of
    its own to interpolate from (unlike a table gridline, where the fragment
    Hough finds is a tiny piece of a much longer line with plenty of unmasked
    line on either side). Extending out to -- and past -- the actual masked run's
    true boundary finds real anchor pixels the short Hough fragment missed."""
    n = len(mask_1d)
    idxs = np.where(mask_1d[lo0:hi0 + 1] != 0)[0]
    if len(idxs) == 0:
        return lo0, hi0
    lo, hi = lo0 + int(idxs.min()), lo0 + int(idxs.max())
    while lo > 0 and mask_1d[lo - 1] != 0:
        lo -= 1
    while hi < n - 1 and mask_1d[hi + 1] != 0:
        hi += 1
    return max(0, lo - margin), min(n - 1, hi + margin)


def _restore_line(result, orig, mask, x1, y1, x2, y2, radius, margin):
    """Redraw one grid-line segment's exact original color into `result`, even
    across pixels the erasure mask covered. Erasure (mask + LaMa) still runs
    normally first over the whole box, including any sliver of a border line
    right next to a text row -- that's necessary because in this document family
    text sometimes sits only a couple of pixels from a column border, so any
    fixed exclusion band around the line would clip real glyph pixels instead.
    Restoring the line afterward, by interpolating its known color from
    unmasked points along the same line, fixes the line without that tradeoff.
    """
    H, W = result.shape[:2]
    is_vertical = abs(x1 - x2) <= 2
    if is_vertical:
        xc = (x1 + x2) // 2
        y_lo, y_hi = _extend_to_mask_run(mask[:, xc], *sorted((y1, y2)), margin)
        idx = np.arange(y_hi - y_lo + 1)
        for xx in range(max(0, xc - radius), min(W, xc + radius + 1)):
            known = mask[y_lo:y_hi + 1, xx] == 0
            if not known.any() or known.all():
                continue
            for c in range(3):
                vals = orig[y_lo:y_hi + 1, xx, c].astype(np.float64)
                filled = vals.copy()
                filled[~known] = np.interp(idx[~known], idx[known], vals[known])
                result[y_lo:y_hi + 1, xx, c] = np.round(filled).astype(np.uint8)
    else:
        yc = (y1 + y2) // 2
        x_lo, x_hi = _extend_to_mask_run(mask[yc, :], *sorted((x1, x2)), margin)
        idx = np.arange(x_hi - x_lo + 1)
        for yy in range(max(0, yc - radius), min(H, yc + radius + 1)):
            known = mask[yy, x_lo:x_hi + 1] == 0
            if not known.any() or known.all():
                continue
            for c in range(3):
                vals = orig[yy, x_lo:x_hi + 1, c].astype(np.float64)
                filled = vals.copy()
                filled[~known] = np.interp(idx[~known], idx[known], vals[known])
                result[yy, x_lo:x_hi + 1, c] = np.round(filled).astype(np.uint8)


class Inpainter:
    """Thin wrapper around a SimpleLama instance.

    Construction loads the ~200MB LaMa checkpoint onto the GPU, so instantiate
    one of these per process/service and reuse it across every page/document.
    """

    def __init__(self):
        self._lama = SimpleLama()

    @property
    def device(self):
        return self._lama.device

    def clean(self, img_rgb, text_blocks, W, H, config, extra_boxes=None):
        # Mask padding around each box before inpainting. Padding scales with box
        # *height* only, on both axes -- not with box width, since the actual
        # antialiasing/box-imprecision margin needed is determined by font size
        # (the line's height), not by how many characters happen to be on the line.
        # A margin too large also risks bleeding into a real color boundary right
        # next to a text line (e.g. a colored table-header row).
        mask = np.zeros((H, W), dtype=np.uint8)
        for t in text_blocks:
            x0, y0, x1, y1 = t["px_bbox"]
            h = y1 - y0
            pad = max(config.mask_min_pad, h * config.mask_pad_frac)
            x0, y0 = max(0, int(x0 - pad)), max(0, int(y0 - pad))
            x1, y1 = min(W, int(x1 + pad)), min(H, int(y1 + pad))
            cv2.rectangle(mask, (x0, y0), (x1, y1), 255, -1)
        # extra_boxes (e.g. a fixed watermark region) erase unconditionally, on top
        # of whatever text_blocks contributed -- these aren't text, so they don't
        # go through the same per-box height-scaled padding; a flat pad is enough
        # to clear antialiased edges.
        for x0, y0, x1, y1 in extra_boxes or []:
            pad = config.mask_min_pad
            x0, y0 = max(0, int(x0 - pad)), max(0, int(y0 - pad))
            x1, y1 = min(W, int(x1 + pad)), min(H, int(y1 + pad))
            cv2.rectangle(mask, (x0, y0), (x1, y1), 255, -1)
        if not mask.any():
            return img_rgb

        grid_lines = _detect_grid_lines(img_rgb, mask, W, H, config) if config.protect_grid_lines else []
        return self._composite(img_rgb, mask, W, H, config, grid_lines)

    def clean_polygon(self, img_rgb, polygon, W, H, config):
        """Inpaint an arbitrary user-drawn polygon region (e.g. a manually
        click-selected quadrilateral in the web editor), rather than the
        padded text-line rectangles `clean` builds its mask from. Shares the
        same LaMa/grid-line-protection path as `clean` -- only the mask
        construction differs.
        """
        mask = np.zeros((H, W), dtype=np.uint8)
        pts = np.array(polygon, dtype=np.int32).reshape((-1, 1, 2))
        cv2.fillPoly(mask, [pts], 255)
        if not mask.any():
            return img_rgb

        grid_lines = _detect_grid_lines(img_rgb, mask, W, H, config) if config.protect_grid_lines else []
        return self._composite(img_rgb, mask, W, H, config, grid_lines)

    def _composite(self, img_rgb, mask, W, H, config, grid_lines):
        long_side = max(W, H)
        scale = min(1.0, config.lama_max_dim / long_side)
        if scale < 1.0:
            small_img = cv2.resize(img_rgb, (int(W * scale), int(H * scale)), interpolation=cv2.INTER_AREA)
            small_mask = cv2.resize(mask, (int(W * scale), int(H * scale)), interpolation=cv2.INTER_NEAREST)
        else:
            small_img, small_mask = img_rgb, mask

        try:
            result = self._lama(Image.fromarray(small_img), Image.fromarray(small_mask))
            result_np = np.array(result)
        except torch.cuda.OutOfMemoryError:
            logger.warning("LaMa ran out of GPU memory on this page, falling back to classical inpainting")
            result_np = cv2.inpaint(img_rgb, mask, 3, cv2.INPAINT_TELEA)
        finally:
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

        # LaMa internally pads its input up to a multiple of 8 and does not always
        # crop the output back down, so force it back to the exact source
        # dimensions unconditionally so background pixels always line up with the
        # text-box coordinates computed against (W, H).
        if result_np.shape[1] != W or result_np.shape[0] != H:
            result_np = cv2.resize(result_np, (W, H), interpolation=cv2.INTER_LANCZOS4)

        # simple_lama_inpainting returns the model's full reconstructed image, not
        # just the masked patch, and its whole-image reconstruction can subtly drift
        # even in technically-unmasked pixels near a strong edge. Composite
        # explicitly so only the actually-masked pixels come from LaMa; everything
        # else is the pixel-exact original.
        mask_3ch = cv2.cvtColor(mask, cv2.COLOR_GRAY2RGB)
        composited = np.where(mask_3ch > 0, result_np, img_rgb)

        for x1, y1, x2, y2 in grid_lines:
            _restore_line(
                composited, img_rgb, mask, x1, y1, x2, y2,
                config.grid_line_protect_radius, config.grid_line_restore_margin,
            )

        return composited

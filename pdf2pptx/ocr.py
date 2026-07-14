import math

import cv2
import numpy as np
from paddleocr import PaddleOCR

from .text_utils import estimate_font_size_pt, looks_like_garbage, resolve_font


def sample_text_color(img_rgb, bbox):
    """PaddleOCR doesn't report text color. Approximate it by averaging whichever
    tail of the box's brightness distribution -- the darkest ~3% or the lightest
    ~3% -- sits farther from the box's median brightness. Text is reliably the
    highest-contrast content in these boxes, and the median approximates the
    background color since the background is the majority of the box's area
    either way; comparing both tails against it (rather than always assuming the
    darkest pixels are the text) recovers colored headings on a light card (e.g.
    dark green text) *and* light text on a dark card background (e.g. a white
    table-header row on a navy band), instead of flattening the latter to the
    dark background color.

    The tail is deliberately narrow (~3%, not e.g. 15%): most pixels in a text
    box are the antialiased blend between ink and background, not pure ink, so a
    wide tail averages in enough of that blend to pull the result noticeably
    toward the background color -- harmless when text is already dark-on-light
    (a slightly-off dark gray still reads fine), but for light-on-dark headers it
    waters the result down from white toward the dark background, i.e. back
    toward the original bug. A narrower tail sits closer to the true ink color at
    the cost of averaging fewer pixels, which is the right tradeoff here.
    """
    x0, y0, x1, y1 = [int(v) for v in bbox]
    crop = img_rgb[max(0, y0):max(0, y1), max(0, x0):max(0, x1)]
    if crop.size == 0:
        return "000000"
    gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
    median = np.median(gray)
    dark_thresh = np.percentile(gray, 3)
    light_thresh = np.percentile(gray, 97)
    if (light_thresh - median) > (median - dark_thresh):
        mask = gray >= light_thresh
    else:
        mask = gray <= dark_thresh
    if not mask.any():
        return "000000"
    r, g, b = crop[mask].mean(axis=0)
    return f"{int(r):02x}{int(g):02x}{int(b):02x}"


def quad_geometry(poly, min_rotation_deg):
    """PaddleOCR reports each detection's location two ways: `rec_boxes` (the
    axis-aligned bounding box, which is what the rest of this pipeline uses for
    masking/reconciliation) and `rec_polys` (the actual four-corner quadrilateral
    PaddleOCR fit to the text line, corners ordered top-left/top-right/bottom-
    right/bottom-left). For rotated text -- e.g. a line of text drawn on a
    tilted face of a 3D-style illustration -- the axis-aligned box is much
    larger than the true text extent (it has to contain the whole tilted
    rectangle), and placing a native PPTX text box to fill it would look
    nothing like the source. Fitting the box to the quad's own edge lengths and
    rotating it by the quad's own angle instead reproduces the original size
    and orientation much more closely -- not a full perspective/keystone warp
    (PowerPoint text boxes don't support that), but a single rotation, which
    for a text line short enough to look "flat" within its own bounding box
    (as opposed to text following a curve) is normally a close approximation.

    Returns (center_x, center_y, width, height, angle_deg). angle_deg is 0 for
    anything under min_rotation_deg, both to leave the vast majority of
    ordinary horizontal text completely unaffected (its quad is never
    perfectly axis-aligned -- detection jitter alone is usually a degree or
    two) and because PowerPoint rotates around the shape's center, so applying
    a rotation at all changes the effective bounding box even when the visual
    difference is imperceptible.
    """
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = poly
    width = math.hypot(x1 - x0, y1 - y0)
    height = math.hypot(x3 - x0, y3 - y0)
    center_x = (x0 + x1 + x2 + x3) / 4
    center_y = (y0 + y1 + y2 + y3) / 4
    angle_deg = math.degrees(math.atan2(y1 - y0, x1 - x0))
    if abs(angle_deg) < min_rotation_deg:
        angle_deg = 0.0
    return center_x, center_y, width, height, angle_deg


class OcrEngine:
    """Thin wrapper around a PaddleOCR instance.

    Construction (and the underlying model load) is expensive, so instantiate one
    of these per process/service and reuse it across every page/document, rather
    than creating a fresh one per conversion.
    """

    def __init__(self, lang="chinese_cht"):
        # use_doc_orientation_classify/use_doc_unwarping/use_textline_orientation
        # must be disabled here, at construction, not just per predict() call --
        # PaddleOCR decides whether to even build/load those three submodels
        # (doc-orientation classifier, UVDoc unwarping, textline-orientation) at
        # construction time based on these flags (default None lets its own
        # pipeline default enable them); passing False only to predict() is too
        # late; the models are already downloaded/loaded by then, just unused.
        self._ocr = PaddleOCR(
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            lang=lang,
            engine="transformers",
        )

    def extract(self, img_rgb, W, H, config):
        """Returns (results, mask_boxes):

        - results: reconciliation/editable-text candidates -- one dict per
          detection that passed our own confidence/garbage filtering (see
          config.ocr_min_conf, text_utils.looks_like_garbage), same shape as
          before.
        - mask_boxes: every detection's px_bbox, unfiltered -- the erasure
          mask is built solely from this (see pipeline.py), on the premise
          that text-shaped ink still needs erasing even when it's too
          low-confidence or garbled to trust as a real transcription; only
          the *editable-text* decision benefits from filtering that out.

        The detection/recognition settings below are PP-OCRv6's own
        documented defaults, pinned explicitly here (rather than left as
        whatever this PaddleOCR version's implicit defaults happen to be),
        plus text_rec_score_thresh=0 so the model does no confidence-based
        filtering of its own -- our own config.ocr_min_conf below is the only
        gate on what becomes editable text, and mask_boxes sees everything.
        """
        result = self._ocr.predict(
            img_rgb,
            text_det_limit_type="min",
            text_det_limit_side_len=64,
            text_det_thresh=0.3,
            text_det_box_thresh=0.6,
            text_det_unclip_ratio=1.5,
            text_rec_score_thresh=0,
        )[0]
        texts = result.get("rec_texts", [])
        scores = result.get("rec_scores", [])
        boxes = result.get("rec_boxes", [])
        polys = result.get("rec_polys", [None] * len(texts))

        results = []
        mask_boxes = []
        for text, conf, box, poly in zip(texts, scores, boxes, polys):
            bbox = tuple(float(v) for v in box)
            mask_boxes.append(bbox)

            text = text.strip()
            if not text or conf < config.ocr_min_conf or looks_like_garbage(text, config.junk_chars):
                continue
            x0, y0, x1, y1 = bbox
            w_px = x1 - x0
            h_px = y1 - y0

            # render_geom/rotation_deg describe the text's own tilted quad, used
            # by slide_builder to size/rotate the PPTX text box to match it
            # instead of filling the (larger, always axis-aligned) px_bbox --
            # px_bbox itself is left as the axis-aligned box regardless, since
            # that's what reconciliation needs (a rectangle guaranteed to fully
            # contain the tilted text).
            rotation_deg = 0.0
            render_geom = None
            if poly is not None:
                cx, cy, quad_w_px, quad_h_px, rotation_deg = quad_geometry(poly, config.ocr_min_rotation_deg)
                if rotation_deg != 0.0:
                    render_geom = (cx, cy, quad_w_px, quad_h_px)
                    # font size should track the text's own tilted quad, not
                    # the larger axis-aligned box -- same reasoning applies to
                    # width as already applied to height above.
                    w_px, h_px = quad_w_px, quad_h_px

            results.append({
                "text": text,
                "px_bbox": bbox,
                "rotation_deg": rotation_deg,
                "render_geom": render_geom,
                "color": sample_text_color(img_rgb, bbox),
                "font_size_pt": estimate_font_size_pt(text, w_px, h_px, W, H, config),
                "font_name": resolve_font(None, text),
            })
        return results, mask_boxes

from .text_utils import overlap_ratio


def resolve_watermark_boxes(config, W, H):
    """Convert PipelineConfig.watermark_regions (normalized (x0, y0, x1, y1)
    fractions of page width/height, so they apply regardless of zoom or the
    source PDF's native page size) into pixel-space boxes for this page."""
    return [
        (x0 * W, y0 * H, x1 * W, y1 * H)
        for x0, y0, x1, y1 in config.watermark_regions
    ]


def is_watermark_text(text, watermark_texts):
    """True if `text` (stripped and lowercased) exactly matches one of
    PipelineConfig.watermark_texts -- e.g. the "NotebookLM" attribution
    stamped by whatever tool generated the source PDF. Unlike
    watermark_regions (a fixed pixel region that has to be configured per
    document), this matches by content wherever it lands on the page."""
    return text.strip().lower() in watermark_texts


def find_content_watermark_boxes(texts, watermark_texts):
    """px_bbox of every detection that is a watermark by content (see
    is_watermark_text). Needed alongside strip_watermark_texts because,
    unlike a watermark_regions box, there's no pre-configured region to add to
    the inpainting mask for these -- the only place their location is known is
    the detection itself, which strip_watermark_texts is about to drop."""
    return [t["px_bbox"] for t in texts if is_watermark_text(t["text"], watermark_texts)]


def strip_watermark_texts(texts, watermark_boxes_px, watermark_texts=frozenset(), overlap_thresh=0.5):
    """Drop any detected text (native or OCR) that is a watermark -- either it
    mostly falls inside a configured watermark_regions box, or its own text
    content matches a known watermark string (see is_watermark_text). Without
    this, a watermark's own text (e.g. a logo's wordmark) gets OCR'd like any
    other page content and rebuilt as a genuine, editable text box --
    preserving the watermark instead of removing it."""
    return [
        t for t in texts
        if not is_watermark_text(t["text"], watermark_texts)
        and not any(overlap_ratio(t["px_bbox"], wb) > overlap_thresh for wb in watermark_boxes_px)
    ]

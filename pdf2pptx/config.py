from dataclasses import dataclass, field


@dataclass(frozen=True)
class PipelineConfig:
    """All tunable knobs for the PDF -> editable-PPTX pipeline.

    Defaults match what was tuned against the original Tainan air-quality report;
    override per-document if a different source PDF needs different thresholds
    (e.g. a different native page size, or a language other than Traditional
    Chinese for OCR).
    """

    slide_w_in: float = 10.0
    slide_h_in: float = 5.625

    # Render zoom relative to the PDF's native point size. 1.5x matches this
    # family of documents' native embedded-image detail (see CLAUDE.md); bump
    # this up for source PDFs with genuinely higher-resolution backgrounds.
    zoom: float = 1.5

    # Skip an OCR box as a duplicate if it overlaps a native-text box this much.
    overlap_skip: float = 0.3
    # Native-vs-OCR reconciliation thresholds -- see reconcile.py for the two
    # overlap cases these distinguish.
    size_ratio_thresh: float = 2.0
    containment_thresh: float = 0.9

    lama_max_dim: int = 2200  # cap LaMa's working resolution to bound VRAM use

    ocr_min_conf: float = 0.8
    ocr_lang: str = "chinese_cht"

    # Below this, a detected text line's own quadrilateral (see ocr.quad_geometry)
    # is treated as unrotated (0 degrees) rather than applying a rotation to its
    # PPTX text box. Ordinary horizontal text's detected quad is essentially
    # never perfectly axis-aligned -- a degree or two of detection jitter is
    # normal -- so without a floor, nearly every text box on every page would
    # get a barely-perceptible rotation for no visual benefit, for no reason
    # beyond noise in the detector.
    ocr_min_rotation_deg: float = 2.0

    junk_chars: frozenset = field(default_factory=lambda: frozenset("=|#*^~`\\{}<>[]_"))

    # Mask padding around each accepted text box before inpainting.
    mask_min_pad: int = 8
    mask_pad_frac: float = 0.08

    # Straight background edges (table gridlines, but also small icon/card outlines)
    # get their exact original color redrawn back on top after erasure, even across
    # pixels a text box's mask covered -- LaMa doesn't reliably keep a precise
    # straight edge straight through a masked gap, which otherwise shows up as a
    # visible jog (long lines) or a melted/warped outline (small icon borders)
    # wherever the mask crosses one. (Excluding the edge from the mask up front
    # instead of restoring it after was tried and rejected: in this document family
    # text sometimes sits only a couple of pixels from a border, so a fixed
    # exclusion band clips real glyph pixels instead.) A candidate line counts as a
    # real edge worth restoring -- rather than a text stroke, which Canny/Hough will
    # also happily find -- if most of its length lies *outside* the erasure mask
    # (grid_line_min_unmasked_frac): a persistent background edge only gets clipped
    # by a mask in passing, while a text stroke lives entirely inside its own
    # glyph's mask. A second guard, grid_line_max_color_std, catches the case
    # where the unmasked fraction is high only because the candidate grazes an
    # unrelated stray unerased fragment sitting outside the mask (a genuine edge
    # is one consistent color along its whole length; a line clipping a text
    # fragment mixes that fragment's color with plain background, so its
    # unmasked sample points have much higher color variance). grid_line_min_len_px
    # filters out short noise from either source. Once a candidate line clears
    # those bars, its *restore* range extends past the masked run it touches by
    # grid_line_restore_margin px in each direction -- a small icon's border can
    # sit so close to its own text that the Hough-detected fragment of that
    # border has barely any unmasked pixels of its own to anchor an
    # interpolation on, unlike a table gridline (a tiny piece of a much longer
    # line with plenty of unmasked line on either side); the margin reaches past
    # the masked run to find real anchor pixels the short fragment missed.
    # grid_line_protect_radius is the half-width, in pixels, of the redrawn line.
    protect_grid_lines: bool = True
    grid_line_min_len_px: int = 20
    grid_line_min_unmasked_frac: float = 0.15
    grid_line_max_color_std: float = 20.0
    grid_line_restore_margin: int = 20
    grid_line_protect_radius: int = 1

    # Fixed regions to strip from every page, e.g. a watermark/logo stamped at the
    # same spot by whatever tool generated the source PDF. Each entry is
    # (x0, y0, x1, y1) as a fraction (0-1) of page width/height -- not pixels, so
    # the same region works regardless of zoom or the source PDF's native page
    # size. Empty by default: this is source-PDF-specific, unlike the rest of this
    # config, and applying a fixed corner-region erasure unconditionally would
    # destroy real content on a source PDF that doesn't have that watermark.
    watermark_regions: tuple = ()

    # Text strings treated as a watermark wherever they land on a page
    # (matched case-insensitively against a detection's full text, after
    # stripping whitespace), regardless of position -- unlike
    # watermark_regions, no per-document region needs to be configured. This
    # is what actually catches the "NotebookLM" attribution stamped by
    # whatever tool generated this project's test documents: watermark_regions
    # is opt-in (nothing calls PdfToPptxConverter with it set, including the
    # FastAPI service), so without a content-based check that watermark's text
    # gets OCR'd like any other content and rebuilt as an editable text box on
    # every conversion. Non-empty by default -- unlike watermark_regions, an
    # exact-match short string is unlikely to collide with real body text, so
    # the false-positive risk of enabling this unconditionally is low.
    watermark_texts: frozenset = field(default_factory=lambda: frozenset({"notebooklm"}))

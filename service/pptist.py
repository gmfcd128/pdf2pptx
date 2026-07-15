"""Converts pdf2pptx's internal per-page text-block dicts (see
pdf2pptx.native_text/pdf2pptx.ocr) into PPTist-shaped slide JSON, so the web
editor can load a converted PDF's pages directly into its own Slide/PPTElement
store with no further geometry math on the browser side.

Pure functions only (no FastAPI/torch/cv2 imports) so this stays trivially
testable and has no bearing on GPU/model state.

PPTist's canvas is a fixed 1000x562.5-unit viewport (VIEWPORT_SIZE in
web/frontend's own configs/canvas.ts, always 1000 units wide regardless of
what real-world slide size that represents), and every number placed on it --
element left/top/width/height, but *also* a text element's inline
`font-size` and `inset` -- is rendered by the browser as a literal CSS pixel
in that same 1000-unit space. That space is only self-consistent if all of
those numbers convert real inches/points to units through the *same*
units_per_inch (1000 / config.slide_w_in). A fixed 96dpi-style `px = pt /
0.75` factor for font-size/inset (what this used to do, matching PPTist's own
PPTX exporter) implicitly assumes units_per_inch == 96 -- close enough to
stock PPTist's own 100 (a ~4% error, invisible) but badly wrong for
pdf2pptx's 13.333in-wide slide default (75 units/inch, a ~28% error): the
font rendered ~28% larger relative to its own box than the geometry alone
would suggest, which is what actually caused the web editor's live display to
show text overflowing its box even though the exported PPTX (which converts
units back to real inches/points independently, not through this canvas
pixel space at all) never had that problem -- see
web/frontend's vendored src/hooks/useExport.ts, which mirrors this same
units_per_inch on the way back out instead of its own former hardcoded
`* 0.75`. The geometry below mirrors pdf2pptx/slide_builder.add_text_box
exactly, just emitting PPTist units instead of python-pptx Inches/Pt.
"""

import html

# See slide_builder.MIN_TIGHT_W_IN/MIN_TIGHT_H_IN -- degenerate-detection
# floors for a text line's own tight width/height, kept in sync with those so
# this mirrors slide_builder.add_text_box's geometry exactly.
MIN_TIGHT_W_IN = 0.2 * 4 / 3
MIN_TIGHT_H_IN = 0.15 * 4 / 3


def text_to_element(t, page_idx, elem_idx, W, H, config):
    """Convert one reconciled text block (px_bbox/render_geom/rotation_deg,
    color, font_size_pt, font_name, text -- see native_text.extract_native_text
    and ocr.OcrEngine.extract) into a PPTist PPTTextElement dict."""
    rotation_deg = t.get("rotation_deg", 0.0) or 0.0
    render_geom = t.get("render_geom")
    units_per_inch = 1000 / config.slide_w_in

    # (top, right, bottom, left), same axis order as config.text_inset_pt and
    # PPTist's own TextInset -- see config.text_inset_pt's docstring.
    inset_top_in, inset_right_in, inset_bottom_in, inset_left_in = (
        v / 72 for v in config.text_inset_pt
    )

    if rotation_deg and render_geom:
        cx, cy, w_px, h_px = render_geom
        w_in = max(MIN_TIGHT_W_IN, w_px / W * config.slide_w_in) + inset_left_in + inset_right_in
        h_in = max(MIN_TIGHT_H_IN, h_px / H * config.slide_h_in) + inset_top_in + inset_bottom_in
        x_in = cx / W * config.slide_w_in - w_in / 2
        y_in = cy / H * config.slide_h_in - h_in / 2
    else:
        x0, y0, x1, y1 = t["px_bbox"]
        tight_w_in = (x1 - x0) / W * config.slide_w_in
        tight_h_in = (y1 - y0) / H * config.slide_h_in
        x_in = x0 / W * config.slide_w_in - inset_left_in
        y_in = y0 / H * config.slide_h_in - inset_top_in
        w_in = max(MIN_TIGHT_W_IN, tight_w_in) + inset_left_in + inset_right_in
        h_in = max(MIN_TIGHT_H_IN, tight_h_in) + inset_top_in + inset_bottom_in

    # pt -> inches -> units, the same two-step conversion as every geometry
    # value above (not a flat pt->px factor) -- see this module's docstring.
    inset = [round(v / 72 * units_per_inch, 2) for v in config.text_inset_pt]

    color = t.get("color") or "000000"
    font_name = t.get("font_name") or "Microsoft Yahei"
    font_size_px = t["font_size_pt"] / 72 * units_per_inch
    text = html.escape(t["text"])

    return {
        "type": "text",
        "id": f"pdf2pptx-p{page_idx}-{elem_idx}",
        "left": x_in * units_per_inch,
        "top": y_in * units_per_inch,
        "width": w_in * units_per_inch,
        "height": h_in * units_per_inch,
        "rotate": rotation_deg,
        "inset": inset,
        # PPTist's own default (1.5, applied when this key is absent -- see
        # BaseTextElement.vue) reserves noticeably more vertical space than
        # this single line's actual glyph height, the same overflow-below-a-
        # tight-box problem slide_builder.add_text_box's line_spacing/
        # vertical_anchor address on the PPTX side -- most visible on a short
        # label inside a small pill-shaped button, where the excess pushes
        # the label below the pill's own bounds. 1.0 keeps the rendered line
        # close to the height this box was actually sized around.
        "lineHeight": 1.0,
        # font-family holds exactly one name, not a CSS fallback list: this
        # same string is read back out downstream as *the* font both by
        # useExport.ts's PPTX export (options.fontFace, which python-pptx/
        # PowerPoint expects as a single typeface name -- a comma-separated
        # list there isn't a real font, so PowerPoint silently substitutes
        # its own generic default, with different, wider metrics than
        # estimate_font_size_pt (pdf2pptx/text_utils.py) budgeted for, which
        # is what actually caused text to overflow its box) and by
        # TextStylePanel's font-name display in the editor UI (which would
        # otherwise show the whole fallback list as if it were one giant font
        # name). The style attribute is still double-quoted on general
        # principle -- font_name is plain here, but the frontend's HTML
        # parser (web/frontend's utils/htmlParser/lexer.ts) tracks one quote
        # char at a time with no nesting, so any future value containing a
        # single quote would otherwise truncate the whole attribute silently.
        "content": (
            f'<p><span style="font-size: {font_size_px:.2f}px; '
            f'font-family: {font_name}; color: #{color}">{text}</span></p>'
        ),
        "defaultFontName": font_name,
        "defaultColor": f"#{color}",
    }


def build_slide_json(page_idx, all_texts, W, H, config):
    """Build the persisted per-page slide.json: element geometry/content plus
    the page's source pixel size (needed by the browser to map a manual-inpaint
    click back to source-image pixel coordinates). Image paths/versions are
    added separately by the caller, since those are job-directory-specific and
    change over the job's lifetime (manual inpaint/revert overwrite the
    background), unlike the elements, which are fixed once the page is
    converted.
    """
    elements = [text_to_element(t, page_idx, i, W, H, config) for i, t in enumerate(all_texts)]
    return {
        "id": f"page-{page_idx}",
        "page_index": page_idx,
        "source_width": W,
        "source_height": H,
        "elements": elements,
    }

"""Converts pdf2pptx's internal per-page text-block dicts (see
pdf2pptx.native_text/pdf2pptx.ocr) into PPTist-shaped slide JSON, so the web
editor can load a converted PDF's pages directly into its own Slide/PPTElement
store with no further geometry math on the browser side.

Pure functions only (no FastAPI/torch/cv2 imports) so this stays trivially
testable and has no bearing on GPU/model state.

PPTist's canvas is a fixed 1000x562.5-unit viewport where 100 units == 1 inch
(pdf2pptx's own slide is 10in x 5.625in, i.e. exactly 1000x562.5 units at that
scale) and a text element's inline `font-size` in its HTML `content` is a CSS
px value at that same 1inch-per-100-units scale (PPTist's own PPTX exporter
converts it back with `* 0.75`, the standard 96dpi px->pt factor -- see
web/frontend's vendored src/hooks/useExport.ts). The geometry below mirrors
pdf2pptx/slide_builder.add_text_box exactly, just emitting PPTist units
instead of python-pptx Inches/Pt. `inset` follows the same `* 0.75` px<->pt
convention (px = pt / 0.75) so PPTist's TextStylePanel shows and edits the
same margin, in the same units, as what slide_builder.add_text_box actually
bakes into the exported PPTX's text-frame margins.
"""

import html

UNITS_PER_INCH = 100  # PPTist canvas: 1000 units wide == a 10in-wide slide


def text_to_element(t, page_idx, elem_idx, W, H, config):
    """Convert one reconciled text block (px_bbox/render_geom/rotation_deg,
    color, font_size_pt, font_name, text -- see native_text.extract_native_text
    and ocr.OcrEngine.extract) into a PPTist PPTTextElement dict."""
    rotation_deg = t.get("rotation_deg", 0.0) or 0.0
    render_geom = t.get("render_geom")

    # (top, right, bottom, left), same axis order as config.text_inset_pt and
    # PPTist's own TextInset -- see config.text_inset_pt's docstring.
    inset_top_in, inset_right_in, inset_bottom_in, inset_left_in = (
        v / 72 for v in config.text_inset_pt
    )

    if rotation_deg and render_geom:
        cx, cy, w_px, h_px = render_geom
        w_in = max(0.2, w_px / W * config.slide_w_in) + inset_left_in + inset_right_in
        h_in = max(0.15, h_px / H * config.slide_h_in) + inset_top_in + inset_bottom_in
        x_in = cx / W * config.slide_w_in - w_in / 2
        y_in = cy / H * config.slide_h_in - h_in / 2
    else:
        x0, y0, x1, y1 = t["px_bbox"]
        tight_w_in = (x1 - x0) / W * config.slide_w_in
        tight_h_in = (y1 - y0) / H * config.slide_h_in
        x_in = x0 / W * config.slide_w_in - inset_left_in
        y_in = y0 / H * config.slide_h_in - inset_top_in
        w_in = max(0.2, tight_w_in) + inset_left_in + inset_right_in
        h_in = max(0.15, tight_h_in) + inset_top_in + inset_bottom_in

    inset = [round(v / 0.75, 2) for v in config.text_inset_pt]

    color = t.get("color") or "000000"
    font_name = t.get("font_name") or "Microsoft Yahei"
    # content's font-size is CSS px; pdf2pptx's own font_size_pt is already a
    # real point size for the final slide, so this is just the inverse of the
    # 0.75 px->pt factor PPTist's PPTX exporter applies on the way back out.
    font_size_px = t["font_size_pt"] / 0.75
    text = html.escape(t["text"])

    return {
        "type": "text",
        "id": f"pdf2pptx-p{page_idx}-{elem_idx}",
        "left": x_in * UNITS_PER_INCH,
        "top": y_in * UNITS_PER_INCH,
        "width": w_in * UNITS_PER_INCH,
        "height": h_in * UNITS_PER_INCH,
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
        "content": (
            f"<p><span style='font-size: {font_size_px:.2f}px; "
            f"font-family: {font_name}; color: #{color}'>{text}</span></p>"
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

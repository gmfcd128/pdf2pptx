from .text_utils import resolve_font


def extract_native_text(page, W, H, pw, ph, config):
    """Extract pixel-perfect native PDF vector text (position/font/color) via PyMuPDF."""
    results = []
    for block in page.get_text("dict").get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            if not spans:
                continue
            text = "".join(s.get("text", "") for s in spans).strip()
            if not text:
                continue
            x0, y0, x1, y1 = line["bbox"]
            color_int = spans[0].get("color", 0)
            color_hex = f"{color_int:06x}"
            font_size_pt = spans[0].get("size", 12) * (config.slide_h_in / ph) * 72
            results.append({
                "text": text,
                "px_bbox": (x0 / pw * W, y0 / ph * H, x1 / pw * W, y1 / ph * H),
                "color": color_hex,
                "font_size_pt": max(8, font_size_pt),
                "font_name": resolve_font(spans[0].get("font", ""), text),
            })
    return results

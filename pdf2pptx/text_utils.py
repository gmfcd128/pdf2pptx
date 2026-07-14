def has_cjk(s):
    return any("一" <= ch <= "鿿" for ch in s)


# Standard full-width/half-width approximation for CJK UI fonts: a CJK
# character is roughly as wide as it is tall (~1em advance), other characters
# (Latin letters, digits, punctuation) roughly half that.
_CJK_CHAR_EM = 1.0
_OTHER_CHAR_EM = 0.55


def estimate_line_em_width(text):
    """Rough rendered-width estimate for one line of text, in em (multiply by
    the font size in points to get a width in points). See
    estimate_font_size_pt's docstring for why this exists."""
    return sum(_CJK_CHAR_EM if "一" <= ch <= "鿿" else _OTHER_CHAR_EM for ch in text)


def estimate_font_size_pt(text, w_px, h_px, img_w_px, img_h_px, config):
    """Estimate a PPTX font size (pt) for one detected OCR text line.

    PaddleOCR reports a box but no font size, so this starts from box height
    (a fixed height/font-size ratio, tuned empirically against this document
    family) -- but height alone doesn't guarantee the text actually fits the
    box's own detected *width* once rendered in whatever font PowerPoint
    substitutes (this document family's real source fonts aren't embedded or
    otherwise knowable), and a substituted font can be wider per character
    than the tuned height ratio assumes -- most visible on long CJK/mixed-
    script lines, e.g. page titles. Capping by a width estimate
    (estimate_line_em_width) keeps the rendered line within the box PaddleOCR
    actually detected, at the cost of a slightly smaller font on the (rare,
    mostly title-length) lines where the two estimates disagree -- much less
    visually different from the source PDF than word-wrapping into an extra
    line that doesn't exist there.
    """
    height_pt = max(6.0, h_px * (config.slide_h_in / img_h_px) * 72 * 0.8)
    em_width = estimate_line_em_width(text)
    if em_width <= 0:
        return height_pt
    avail_w_pt = (w_px / img_w_px) * config.slide_w_in * 72
    # Target a bit under the full available width, not the exact boundary --
    # this estimate is a rough approximation of real font metrics, not a
    # measurement of them.
    width_pt = (avail_w_pt / em_width) * 0.95
    return max(6.0, min(height_pt, width_pt))


def resolve_font(font_name, text):
    if has_cjk(text):
        return "Microsoft JhengHei"
    if not font_name or "CID" in font_name or "Identity" in font_name:
        return "Arial"
    return font_name.split(",")[0].split("+")[-1].split("-")[0] or "Arial"


def looks_like_garbage(text, junk_chars):
    if not text:
        return True
    junk = sum(ch in junk_chars for ch in text)
    return junk >= 2 or junk / max(1, len(text)) > 0.25


def bbox_area(bbox):
    x0, y0, x1, y1 = bbox
    return max(1e-6, (x1 - x0) * (y1 - y0))


def overlap_ratio(a, b):
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    iw, ih = max(0, ix1 - ix0), max(0, iy1 - iy0)
    inter = iw * ih
    if inter == 0:
        return 0.0
    area_a = bbox_area(a)
    area_b = bbox_area(b)
    return inter / min(area_a, area_b)

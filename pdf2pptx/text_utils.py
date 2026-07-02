def has_cjk(s):
    return any("一" <= ch <= "鿿" for ch in s)


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

def has_cjk(s):
    return any("一" <= ch <= "鿿" for ch in s)


# Standard full-width/half-width approximation for CJK UI fonts: a CJK
# character is roughly as wide as it is tall (~1em advance). Other characters
# (Latin letters, digits, punctuation) were originally modeled at 0.55em
# ("roughly half" a CJK char), but measured against Arial/Microsoft
# JhengHei's actual glyph metrics, all-caps runs -- common in this kind of
# business-deck content as English acronyms/brand names (e.g. "APLUS MATRIX
# INTERNATIONAL CORP.", "HOTEL", "WMS/TMS/LMS") -- render at ~0.6-0.67em/char,
# well above 0.55. Since this estimate only ever needs to be a *safe* upper
# bound (see estimate_font_size_pt), 0.6 trades a smaller font on ordinary
# lowercase-heavy text for not underestimating the width of exactly the
# strings most likely to actually overflow.
_CJK_CHAR_EM = 1.0
_OTHER_CHAR_EM = 0.6


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
    # 0.8 -> 0.88: measured directly against APM_公司簡介_AI_Evolution.pdf --
    # rendered each detected line's own glyph ink height at the pipeline's
    # zoom, compared it against the same font (Microsoft JhengHei) rendered
    # at known point sizes to back out the line's true source font size, then
    # rescaled by config.slide_h_in against that source page's own physical
    # height (the two aren't the same slide size -- this pipeline's default
    # output slide is smaller). That true size consistently came out ~10-30%
    # above what ratio 0.8 produced (e.g. a body paragraph: true ~16.7pt vs.
    # 0.8's 12.75pt) -- 0.8 was leaving more headroom than the box height
    # actually needed, which is what made the layout feel sparse. 0.88 still
    # keeps a margin below 1:1 rather than chasing the exact measured value,
    # since the measurement is itself an approximation (single-document
    # sample, assumed font, assumed OCR-box-to-ink-height margin).
    height_pt = max(6.0, h_px * (config.slide_h_in / img_h_px) * 72 * 0.88)
    em_width = estimate_line_em_width(text)
    if em_width <= 0:
        return height_pt
    avail_w_pt = (w_px / img_w_px) * config.slide_w_in * 72
    # Target well under the full available width, not the exact boundary --
    # this estimate is a rough approximation of real font metrics, not a
    # measurement of them, and the font it's approximating (resolve_font's
    # "Microsoft JhengHei"/"Arial") may not even be the one actually used to
    # render the line: neither PowerPoint nor a browser has it installed on
    # every machine, and whatever they substitute instead is reliably a bit
    # wider per character, not narrower. 0.85 (now 0.92, see below) leaves
    # slack against that substitution risk, instead of 0.95's ~5%, which was
    # too thin to survive a substituted font in practice.
    #
    # 0.85 -> 0.92: same real-glyph-measurement check as height_pt above --
    # the width-bound lines (most lines; see estimate_font_size_pt's own
    # docstring) were coming out even further under their measured true size
    # than the height-bound ones (e.g. this document's title: true ~37.7pt
    # vs. 0.85's 27.84pt), so the width margin was the bigger contributor to
    # the layout reading as too empty. Some of that gap is intentional
    # substitution-risk slack this doesn't try to fully close; 0.92 narrows
    # it without giving it up entirely.
    width_pt = (avail_w_pt / em_width) * 0.92
    # No outer max(6.0, ...) here (height_pt already floors itself above) --
    # re-flooring the *combined* result would let a long line in a narrow
    # detected box get bumped back up past width_pt, silently reintroducing
    # the overflow/wrap this whole function exists to prevent (found via a
    # real-font-metrics check against pptist.pptx: a long all-caps English
    # subtitle was capped to exactly 6.0pt by this floor even though its own
    # width math wanted ~4.7pt, and it wrapped to a second line on export).
    return min(height_pt, width_pt)


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

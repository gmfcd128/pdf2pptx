from .text_utils import bbox_area, overlap_ratio


def _containment(container_bbox, nt_bbox, na):
    cx0, cy0, cx1, cy1 = container_bbox
    nx0, ny0, nx1, ny1 = nt_bbox
    ix0, iy0 = max(nx0, cx0), max(ny0, cy0)
    ix1, iy1 = min(nx1, cx1), min(ny1, cy1)
    iw, ih = max(0, ix1 - ix0), max(0, iy1 - iy0)
    return (iw * ih) / na


def _subsumed_by_any(nt, candidates, size_ratio_thresh, containment_thresh):
    na = bbox_area(nt["px_bbox"])
    for c in candidates:
        if bbox_area(c["px_bbox"]) <= na * size_ratio_thresh:
            continue  # comparable size -- handled by the OCR-side dup check instead
        if _containment(c["px_bbox"], nt["px_bbox"], na) > containment_thresh:
            return True
    return False


def reconcile_native_and_ocr(native_texts, ocr_candidates, config):
    """Decide which native-PDF-text lines and which OCR candidates to actually keep.

    A native line and an OCR block can legitimately overlap in two very different ways:
    (1) they're two detections of the *same* line (comparable size, near-identical
        extent) -- OCR is redundant here, keep the pixel-accurate native line and drop
        the OCR duplicate; or
    (2) the OCR block is a much larger block that happens to visually contain the
        native line as one small piece of it. Here the native line is the one that's
        redundant (its content is already inside the larger OCR text), and dropping
        the *OCR* block instead would throw away the rest of that text and leave it
        unmasked/un-erased in the background.

    The two cases are told apart by relative box size: a same-size overlap is case 1,
    a much-bigger-OCR-box overlap is case 2.
    """
    kept_native = [
        nt for nt in native_texts
        if not _subsumed_by_any(nt, ocr_candidates, config.size_ratio_thresh, config.containment_thresh)
    ]

    kept_ocr = []
    for c in ocr_candidates:
        ca = bbox_area(c["px_bbox"])
        is_dup = False
        for nt in kept_native:
            na = bbox_area(nt["px_bbox"])
            if ca > na * config.size_ratio_thresh:
                continue  # c is a much-bigger block containing nt (case 2, already
                          # resolved on the native side above) -- not a same-size duplicate
            if overlap_ratio(c["px_bbox"], nt["px_bbox"]) > config.overlap_skip:
                is_dup = True
                break
        if not is_dup:
            kept_ocr.append(c)

    # A kept OCR block's box is sometimes cropped a few px short of the line's true
    # extent, so a trailing native fragment at its edge can land just under
    # containment_thresh on the first pass even though it's clearly already part of
    # that block's text. Recheck survivors against the now-final kept_ocr with a
    # looser bar -- safe here since kept_ocr is a small, already-vetted set of
    # confirmed larger blocks (unlike the raw, unfiltered ocr_candidates above).
    kept_native = [
        nt for nt in kept_native
        if not _subsumed_by_any(nt, kept_ocr, config.size_ratio_thresh, config.containment_thresh * 0.6)
    ]

    return kept_native, kept_ocr

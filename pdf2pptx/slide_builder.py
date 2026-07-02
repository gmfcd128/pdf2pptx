from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor


def add_text_box(slide, t, W, H, config):
    rotation_deg = t.get("rotation_deg", 0.0)
    render_geom = t.get("render_geom")

    if rotation_deg and render_geom:
        # render_geom is the text's own tilted quad (center + true edge-length
        # width/height, in px) rather than px_bbox's axis-aligned box, which is
        # always larger than -- and wouldn't visually match -- rotated text.
        # PowerPoint rotates a shape around its own center, so the box is
        # placed/sized here as if unrotated (centered on the quad's center)
        # and rotation is applied last.
        cx, cy, w_px, h_px = render_geom
        w_in = max(0.2, w_px / W * config.slide_w_in + 0.3)
        h_in = max(0.15, h_px / H * config.slide_h_in + 0.1)
        x_in = cx / W * config.slide_w_in - w_in / 2
        y_in = cy / H * config.slide_h_in - h_in / 2
    else:
        x0, y0, x1, y1 = t["px_bbox"]
        x_in = x0 / W * config.slide_w_in
        y_in = y0 / H * config.slide_h_in
        w_in = max(0.2, (x1 - x0) / W * config.slide_w_in + 0.3)
        h_in = max(0.15, (y1 - y0) / H * config.slide_h_in + 0.1)

    box = slide.shapes.add_textbox(Inches(x_in), Inches(y_in), Inches(w_in), Inches(h_in))
    if rotation_deg:
        box.rotation = rotation_deg
    tf = box.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    run = tf.paragraphs[0].add_run()
    run.text = t["text"]
    run.font.size = Pt(t["font_size_pt"])
    run.font.name = t["font_name"]
    try:
        run.font.color.rgb = RGBColor.from_string(t["color"])
    except Exception:
        run.font.color.rgb = RGBColor(0, 0, 0)

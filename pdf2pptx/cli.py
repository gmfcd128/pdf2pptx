"""CLI entry point: convert an arbitrary PDF into an editable PPTX.

Usage:
    python -m pdf2pptx.cli input.pdf output.pptx [--background-dir DIR] [--lang chinese_cht]
"""

import argparse
import logging
import sys

from .config import PipelineConfig
from .pipeline import PdfToPptxConverter


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_pdf", help="Path to the source PDF")
    parser.add_argument("output_pptx", help="Path to write the editable PPTX to")
    parser.add_argument(
        "--background-dir",
        default=None,
        help="Directory to keep the per-page inpainted background PNGs in "
        "(default: a temp dir that's cleaned up after the run)",
    )
    parser.add_argument(
        "--lang",
        default="chinese_cht",
        help="PaddleOCR language code (default: chinese_cht)",
    )
    parser.add_argument(
        "--watermark-region",
        action="append",
        default=None,
        metavar="X0,Y0,X1,Y1",
        help="Strip a fixed region from every page (e.g. a watermark/logo stamped "
        "by whatever tool generated the source PDF), given as x0,y0,x1,y1 "
        "fractions (0-1) of page width/height. Repeatable for multiple regions.",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")
    args = parser.parse_args(argv)

    # Windows consoles often use a legacy codepage (e.g. cp1252) that can't
    # encode CJK characters -- without this, a source/output filename containing
    # them crashes the final summary print below with UnicodeEncodeError even
    # though the conversion itself completed successfully.
    sys.stdout.reconfigure(errors="replace")
    sys.stderr.reconfigure(errors="replace")

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    watermark_regions = ()
    if args.watermark_region:
        watermark_regions = tuple(
            tuple(float(v) for v in region.split(",")) for region in args.watermark_region
        )

    config = PipelineConfig(ocr_lang=args.lang, watermark_regions=watermark_regions)
    converter = PdfToPptxConverter(config)
    result = converter.convert(args.input_pdf, args.output_pptx, background_dir=args.background_dir)
    print(f"Saved {result.page_count} slides to {result.output_pptx_path}")


if __name__ == "__main__":
    sys.exit(main())

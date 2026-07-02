"""Local convenience entry point: converts the bundled Tainan air-quality report
using the default settings, matching the previously documented `python convert.py`
workflow. For arbitrary PDFs, use `python -m pdf2pptx.cli <input.pdf> <output.pptx>`
instead, or run the containerized service (see CLAUDE.md).
"""

import logging
import sys
from pathlib import Path

from pdf2pptx import PdfToPptxConverter

BASE_DIR = Path(__file__).resolve().parent
PDF_PATH = BASE_DIR / "台南空品預警計畫架構與執行藍圖報告v4.pdf"
OUT_PPTX = BASE_DIR / "台南空品預警計畫架構與執行藍圖報告v4.pptx"
BG_DIR = BASE_DIR / "output_backgrounds"


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if not PDF_PATH.exists():
        sys.exit(f"Source PDF not found: {PDF_PATH}")
    converter = PdfToPptxConverter()
    converter.convert(PDF_PATH, OUT_PPTX, background_dir=BG_DIR)


if __name__ == "__main__":
    main()

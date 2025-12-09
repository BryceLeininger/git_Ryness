#!/usr/bin/env python
"""Utility to convert a Ryness PDF into a per-page text file."""

from __future__ import annotations

import argparse
from pathlib import Path

try:
    from pypdf import PdfReader
except ImportError as exc:  # pragma: no cover - dependency enforced via requirements
    raise SystemExit(
        "pypdf is required. Install dependencies with `pip install -r requirements.txt`."
    ) from exc


def extract_text(pdf_path: Path, output_path: Path | None = None) -> Path:
    reader = PdfReader(str(pdf_path))

    if output_path is None:
        output_path = pdf_path.with_suffix(".txt")

    with output_path.open("w", encoding="utf-8") as fh:
        for index, page in enumerate(reader.pages, start=1):
            fh.write(f"--- Page {index} ---\n")
            fh.write(page.extract_text() or "")
            fh.write("\n")

    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path, help="Path to the source PDF report")
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional output path. Defaults to <pdf>.txt",
    )
    args = parser.parse_args()

    output = extract_text(args.pdf, args.output)
    print(f"Extracted text written to {output}")


if __name__ == "__main__":  # pragma: no cover
    main()

"""
CLI for matplotlib post-processing of ngspice raw ``*.plot`` files.

Implementation: :func:`gplugin.ngspice_raw_plot.plot_spice4qucs_matplotlib`.

Usage:
  python plot_spice4qucs.py [path/to/spice4qucs.sp1.plot]
  python plot_spice4qucs.py   # defaults to spice4qucs.sp1.plot next to this script
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _root not in sys.path:
    sys.path.insert(0, _root)

from gplugin.ngspice_raw_plot import plot_spice4qucs_matplotlib


def main() -> None:
    ap = argparse.ArgumentParser(description="Plot Ngspice/Qucs raw spice4qucs.sp1.plot")
    ap.add_argument(
        "plot_file",
        nargs="?",
        default=None,
        help="Path to raw plot file (default: spice4qucs.sp1.plot beside this script)",
    )
    ap.add_argument(
        "-o",
        "--out-dir",
        default=None,
        help="Output directory (default: <plot_dir>/plots_spice4qucs)",
    )
    ap.add_argument("--no-pdf", action="store_true", help="Skip multi-page PDF")
    ap.add_argument("--no-png", action="store_true", help="Skip per-variable PNGs")
    args = ap.parse_args()
    script_dir = Path(__file__).resolve().parent
    p = Path(args.plot_file) if args.plot_file else script_dir / "spice4qucs.sp1.plot"
    if not p.is_file():
        print(f"File not found: {p}", file=sys.stderr)
        sys.exit(1)
    r = plot_spice4qucs_matplotlib(
        p,
        out_dir=args.out_dir,
        save_pdf=not args.no_pdf,
        save_png=not args.no_png,
    )
    if r["pdf_path"] is not None:
        print(f"Wrote PDF: {r['pdf_path']}")
    print(f"Output directory: {r['out_dir']}")


if __name__ == "__main__":
    main()

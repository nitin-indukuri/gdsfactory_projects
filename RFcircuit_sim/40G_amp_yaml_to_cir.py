
# Generate an ngspice ``.cir`` from ``40G_amp.yaml`` (or another YAML netlist).

# Uses :func:`gplugin.yml_spice_plugin.yaml_to_ngspice_deck`: IHP ``.lib`` lines, ``hbt`` / ``rsil`` /
# ``cap_cmim`` / ``L`` / ``V`` mapping like ``40G_Amp.py``, optional RF stimulus and amplifier
# ``.control`` block.

# Usage::

#     python3 RFcircuit_sim/40G_amp_yaml_to_cir.py
#     python3 RFcircuit_sim/40G_amp_yaml_to_cir.py path/to/netlist.yaml out.cir
#     python3 RFcircuit_sim/40G_amp_yaml_to_cir.py --batch   # ``.op`` only for ``ngspice -b``

from __future__ import annotations

import argparse
import os
import sys

_script_dir = os.path.dirname(os.path.abspath(__file__))
_repo_root = os.path.abspath(os.path.join(_script_dir, ".."))
_default_yaml = os.path.join(_script_dir, "40G_amp.yaml")
_default_cir = os.path.join(_script_dir, "40G_amp_yaml_PDK.cir")

if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)


def main() -> None:
    ap = argparse.ArgumentParser(description="YAML netlist → ngspice .cir (IHP-style, like 40G_Amp.py)")
    ap.add_argument("yaml", nargs="?", default=_default_yaml, help="Input YAML")
    ap.add_argument("cir", nargs="?", default=_default_cir, help="Output .cir")
    ap.add_argument(
        "--batch",
        action="store_true",
        help="Force ``.op`` + ``.END`` only (for ``ngspice -b``); ignore YAML amplifier_control",
    )
    args = ap.parse_args()

    yaml_path = os.path.abspath(args.yaml)
    out_path = os.path.abspath(args.cir)

    if not os.path.isfile(yaml_path):
        print(f"Missing YAML: {yaml_path}", file=sys.stderr)
        sys.exit(1)

    from gplugin.yml_spice_plugin import yaml_to_ngspice_deck

    yaml_to_ngspice_deck(
        yaml_path,
        output_path=out_path,
        amplifier_control=False if args.batch else None,
    )
    print(out_path)


if __name__ == "__main__":
    main()

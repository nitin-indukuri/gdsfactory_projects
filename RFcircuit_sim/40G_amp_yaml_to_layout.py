"""
Load ``40G_amp.yaml`` with gdsfactory and open the layout in KLayout.

Uses :mod:`gplugin.yaml_myAPI` / :mod:`gplugin.yml_spice_plugin` to expand ``connections:`` into
per-link ``routes`` with ``bridge_strategy`` (taper / via from :mod:`gplugin.ihp_yaml_bridge`),
which fixes IHP **width mismatch between ports** errors from naive auto-routing.

Requires:
  - IHP gdsfactory PDK (``ihp``)
  - KLayout + klive (or equivalent) for ``.show()``

Usage::

    python3 RFcircuit_sim/40G_amp_yaml_to_netlist.py
"""
from __future__ import annotations

import os
import sys
import tempfile

_script_dir = os.path.dirname(os.path.abspath(__file__))
_repo_root = os.path.abspath(os.path.join(_script_dir, ".."))
_yaml_path = os.path.join(_script_dir, "40G_amp.yaml")

if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)


def main() -> None:
    if not os.path.isfile(_yaml_path):
        print(f"Missing YAML: {_yaml_path}", file=sys.stderr)
        sys.exit(1)

    try:
        from ihp import PDK
    except ImportError:
        print(
            "Could not import IHP PDK (``from ihp import PDK``). "
            "Install/configure the IHP sg13g2 gdsfactory package.",
            file=sys.stderr,
        )
        sys.exit(1)

    import yaml
    import gdsfactory as gf

    from gplugin.ihp_yaml_bridge import routing_strategies_with_bridge
    from gplugin.yaml_myAPI import load_yaml_prepared_for_gdsfactory_layout

    PDK.activate()

    prepared = load_yaml_prepared_for_gdsfactory_layout(_yaml_path)
    strategies = routing_strategies_with_bridge()

    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix="_40g_amp_layout.yaml",
        delete=False,
        dir=_script_dir,
    ) as tmp:
        yaml.safe_dump(
            prepared,
            tmp,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        )
        tmp_path = tmp.name

    try:
        component = gf.read.from_yaml(tmp_path, routing_strategies=strategies)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    print(f"Loaded component {component.name!r} — opening KLayout…")
    component.show()


if __name__ == "__main__":
    main()

# RFcircuit_sim

40 GHz HBT PA–style examples: a **gdsfactory YAML netlist** (`40G_amp.yaml`), **ngspice** decks, and optional **layout** preview. Shared logic lives under the repo’s `gplugin/` package (add the **repository root** to `PYTHONPATH`, or run scripts from this directory—they insert `..` automatically).

## Source netlist

| File | Role |
|------|------|
| **`40G_amp.yaml`** | Schematic-style netlist: `instances`, `connections`, `ports`, `placements` (µm). Topology matches the RF PA reference (HBT, Rs, MIM caps, spiral inductors). |

## Scripts (entry points)

| Script | What it does |
|--------|----------------|
| **`40G_amp_yaml_to_cir.py`** | Calls `gplugin.yml_spice_plugin.yaml_to_ngspice_deck`: IHP `.lib` lines, PDK devices (`hbt`, `rsil`, `cap_cmim`, `inductor2`), port-based RF/VDD stimulus, optional S-parameter `.control` when `RF_*` ports exist. Default output: `40G_amp_yaml_PDK.cir`. Use **`--batch`** for `.op` + `.END` only (`ngspice -b`). |
| **`amp_gen_idealcomponents.py`** | Same YAML → ngspice, but passives are **ideal** `R` / `C` / `L` via `gplugin.spice_gen` (values aligned with the RFamp reference). Default output: `40G_amp_yaml_ideal.cir`. **`--batch`** as above. |
| **`40G_amp_yaml_to_layout.py`** | Loads the YAML through `gplugin.yaml_myAPI` (bridged routing), builds a gdsfactory **component**, and opens it in **KLayout** (needs IHP PDK + `gdsfactory` + viewer). |

## Generated / checked-in ngspice decks

| File | Typical source |
|------|----------------|
| **`40G_amp_yaml_PDK.cir`** | Default output of `40G_amp_yaml_to_cir.py` (PDK subcircuits). |
| **`40G_amp_yaml_ideal.cir`** | Default output of `amp_gen_idealcomponents.py` (ideal passives). |
| **`spicegen_test.cir`** | Written by **`40G_amp_spicegen_test.py`** (hand-built `spice_gen` deck for the same PA idea). |
| **`qucs_gen_amp.cir`** | Qucs/ngspice–style reference deck (companion to older Qucs flows). |

Regenerate PDK/ideal decks after editing the YAML:

```bash
python3 RFcircuit_sim/40G_amp_yaml_to_cir.py
python3 RFcircuit_sim/amp_gen_idealcomponents.py
```

## Other utilities

| File | Role |
|------|------|
| **`40G_amp_spicegen_test.py`** | Builds a 40G PA–style circuit with `gplugin.spice_gen` (libs, sources, `amplifier_plots`), runs ngspice if available, optional matplotlib post-processing. |
| **`plot_spice4qucs.py`** | CLI wrapper for `gplugin.ngspice_raw_plot.plot_spice4qucs_matplotlib` on ngspice **`spice4qucs.sp1.plot`** output. |

## `plots_spice4qucs/` (generated output)

- **Not** checked in by default: created when you run **`plot_spice4qucs.py`** (or call `plot_spice4qucs_matplotlib` directly).
- **Other Use** If you remove the plot command in the spice generation of the netlists, you will generate all these plots in the post process step
- **Location:** by default, a folder named **`plots_spice4qucs`** next to the raw file (e.g. if `spice4qucs.sp1.plot` lives in the repo root, you get **`plots_spice4qucs/`** beside it). Override with `--out-dir` / `out_dir=`.
- **Contents:** multi-page PDF (`spice4qucs_plots.pdf` by default) plus PNGs for the vectors in the ngspice/Qucs raw export (S-parameters, Y/Z, noise, stability-style traces, etc.).

## Config / cache (local)

| Path | Role |
|------|------|
| **`.spiceinit`** | ngspice init for this folder (if used). |
| **`.mplconfig/`** | Matplotlib font cache when plotting is used. |

## `old tests/`

Older experiments: PySpice/Qucs samples, `divider` demos, pytest helpers for `spice_gen`, and archived `.cir` / YAML snippets. Not required for the main 40G YAML → ngspice flow.

## Dependencies (summary)

- **YAML → ngspice:** `gplugin` (`yml_spice_plugin`, `spice_gen`), PyYAML, **IHP Open PDK** model libraries on disk (`PDK_ROOT` / `PDK` env vars; defaults match typical installs).
- **YAML → layout:** `ihp` (gdsfactory PDK), `gdsfactory`, KLayout (or klive) for `.show()`.
- **Plots:** `matplotlib`, `numpy` (optional, for raw-file plotting).

## Simulation quick check

```bash
ngspice -b RFcircuit_sim/40G_amp_yaml_PDK.cir
```

For interactive runs (e.g. decks with `.control` / S-parameter sweep): `ngspice`, then `source RFcircuit_sim/40G_amp_yaml_PDK.cir`.

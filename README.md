# gdsfactory_projects
*Framework for GDSFactory development, IHP PDK integration, and RFIC simulation testing.*

## 🚀 Project Overview

### Project 1: Hello World Example
* **Location:** `helloworld.py`
* **Usage:** Run with KLayout open and `klive` active to visualize the layout.
* **Documentation:** Includes a reference image of the output in the project folder.

### Project 2: PCell and SAX Model
* **PCell Development:** Created a PCell model for the PMOS cell in the **IHP PDK** (`modular_pmos.py`).
* **Environment:** Developed using [IIC-OSIC-TOOLS](https://github.com/iic-jku/IIC-OSIC-TOOLS) via Docker.
* **Validation:** * Utilizes `compare.py` for GDS comparisons using the **XOR method**.
    * Includes numerous GDS variations exported from the Docker environment.
* **Modeling:** Features a SAX Model of the PMOS transistor located in `saxmodel.py`.

### Project 3: RF Circuit Design
* **Setup:** IHP PDK + ngspice; env (`PDK_ROOT`, `PDK`) for model `.lib` paths.
* **Folder `RFcircuit_sim/`:** 40 GHz PA example — `40G_amp.yaml` (instances, connections, placements), scripts to emit ngspice `.cir` (PDK passives vs ideal `R`/`C`/`L`), optional KLayout preview, and a short folder README. See that README for commands.
* **Earlier checks:** PySpice smoke test (`voltage_divider_ex.py`); legacy `old tests/` YAML/GDS experiments and routed-layout workarounds where IHP routing mismatched widths.

### Project 4: RF Models
* **Status:** Finished
* **Goal:** Development of an RF model for LC Josephson Junction (Details in the LC_joseph_model folder)

### Project 5: Tool Interface & Extensions (`gplugin/`)
* **`spice_gen`:** ngspice line helpers (libs, HBT, passives, Qucs-style RF ports, `amplifier_plots` / S-parameter control block).
* **`yml_spice_plugin`:** YAML netlist → flat ngspice deck (IHP devices + port-based stimulus); optional ideal passives; union-find fix for `ports`/`connections` in `yaml_myAPI`.
* **`yaml_myAPI` / `ihp_yaml_bridge`:** Prepare YAML for gdsfactory layout (bridged routing). **`ngspice_raw_plot`:** plot `spice4qucs` raw output.
* **Usage:** Consumed by `RFcircuit_sim` generators; repo root on `PYTHONPATH` when running scripts.

---

## 🐛 Known Bugs & Troubleshooting

### Integration Issues
1.  **GDSFactory Routing:** Width and type mismatches occur in IHP PDK electrical routing, preventing clean YAML reads.
2.  **YAML Translation:** Initial routing calls occasionally fail to connect components as defined.
3.  **PySpice/IHP OSDI:** * NGSPICE OSDI Verilog models are not parsed correctly by PySpice.
    * Importing `.osdi` files directly results in label errors.
    * **Workaround:** Currently bypassing these by parsing `stdout` calls from NGSPICE directly.

### Critical Fix: PySpice "Run Failed" Error
If PySpice crashes due to `stderr` sensitivity while using shared libraries:
1.  Run `pip show PySpice` to find the install directory.
2.  Navigate to `Spice/NgSpice/Shared.py`.
3.  Locate the `exec_command` function (approx. line 850).
4.  **Comment out** the line that triggers `raise NgSpiceCommandError`.
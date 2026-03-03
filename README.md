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

### Project 3: RF Circuit Design (In Progress)
* **Setup:** Manual installation of IHP PDK and NGSPICE with configured environment variables.
* **Verification:** Verified **PySpice** functionality via `voltage_divider_ex.py`.
* **YAML Workflow:**
    * Testing `yamltest.py` to generate KLayout GDS from YAML files.
    * *Note:* Using custom routing strategies to bypass GDSFactory IHP PDK integration bugs.
* **Simulations:** Currently debugging `IHP_HBT_DC_curves.py`. 
    * **Status:** $V_{be}$ vs $I_c$ curve is functional; other curves are pending.

### Project 4: RF Models
* **Status:** Pending.
* **Goal:** Development of an RF model (e.g., LC oscillator or Josephson Junction Model) once PySpice RF simulations are stabilized.

### Project 5: Tool Interface & Extensions
* **Current Task:** Developing a plugin to convert GDSFactory YAML files directly to PySpice netlists.
* **Status:** Logic is nearly complete; being tested concurrently with Project 3.

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
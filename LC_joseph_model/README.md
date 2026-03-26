# Josephson junction RCSJ simulation

Numerical solver and plots for the **resistively and capacitively shunted junction (RCSJ)** model, including **Fraunhofer** modulation of the critical current by a normalized magnetic field **H / H₀**.

## Project overview

This repo implements a normalized RCSJ in the time domain, sweeps bias current to build **V–I** curves, and compares **damping** (quality factor **Q**) and **field** (**H / H₀**) in two linked subplots. The main script is [`JJ_RCSJ_model.py`](JJ_RCSJ_model.py).

---

## 1. Physics: the RCSJ model

The junction is modeled as three parallel paths:

| Channel | Role |
|--------|------|
| **Superconducting** | Pair current **I_s = I_c sin φ** |
| **Resistive** (**R**) | Quasiparticle / normal current **V / R** |
| **Capacitive** (**C**) | Displacement current **C · dV/dt** |

---

## 2. Equations

**Total bias current** (Josephson + resistive + capacitive):

```text
I(t) = I_c sin φ + V/R + C · dV/dt
```

**Second Josephson relation** (phase and voltage):

```text
V = (ℏ / 2e) · dφ/dt
```

Together these give a second-order nonlinear ODE in the phase **φ**.

### Normalized form (used in the solver)

Time is scaled by the plasma frequency **ω_p = √(2e I_c / ℏC)**, with **τ = ω_p t**. The dimensionless equation integrated in code is:

```text
d²φ/dτ² + (1/Q) · dφ/dτ + sin φ = I / I_c(H)
```

- **Q = ω_p R C** — quality factor (damping).
  - **Q ≪ 1** (overdamped): resistive-like branch, little hysteresis.
  - **Q ≫ 1** (underdamped): more capacitive, hysteresis between switching and retrapping.

---

## 3. Magnetic field: Fraunhofer pattern

Interference modulates the critical current as:

```text
I_c(H) = I_c(0) · | sin(π · H/H₀) / (π · H/H₀) |
```

In the limit **H → 0**, **I_c(H) → I_c(0)**. The simulation scales the effective **I_c** for each chosen **H / H₀**.

---

## Features and workflow

### Simulation

- **ODE integration:** `scipy.integrate.odeint` for **φ(τ)** and **dφ/dτ**.
- **DC voltage:** inferred from the mean phase velocity **⟨dφ/dτ⟩** (or equivalent) over a **late-time window** of the trajectory, with optional cycle-based averaging via local maxima of **dφ/dτ**.
- **Bias sweep:** default normalized current grid from **−2** to **+2** (in units of the zero-field scale used in the model).

### Visualization

- **Damping sweep:** several **Q** values at fixed **H / H₀**.
- **Field sweep:** several **H / H₀** values at fixed **Q**.
- **Shared horizontal axis:** both panels use the same normalized voltage axis (`sharex`) for easy comparison.
- **Vertical axis:** normalized current **I / I_c(H)** so the drive matches the ODE term **I / I_c(H)**.

---

## Implementation notes

- **Constants:** `scipy.constants` for **ℏ**, **e**, and the flux quantum **Φ₀** (available for extensions).
- **`timeparams()`:** integration length and sampling fraction depend on **Q** so trajectories can settle before averaging.
- **Fraunhofer nulls:** at integer **H / H₀**, **I_c → 0**. The code floors **I_c** at **10⁻⁹** to avoid division by zero in **I / I_c(H)**; for physics, prefer field values **between** nulls (see comments in `JJ_RCSJ_model.py`).

---

## Requirements

- Python 3  
- `numpy`, `scipy`, `matplotlib`

---

## Usage

From this directory:

```bash
python JJ_RCSJ_model.py
```

This runs the sweeps and shows the figure.

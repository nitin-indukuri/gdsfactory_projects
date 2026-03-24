import numpy as np
import scipy.constants as const
from scipy.integrate import odeint
from scipy.signal import argrelextrema
import matplotlib.pyplot as plt

# 1. CONSTANTS AND PARAMETER SETUP 
# -----------------------------------------------------------------------------
hbar = const.hbar                      # Reduced Planck constant 
ec = const.e                           # Elementary charge 
phi0 = const.value('mag. flux quantum') # Magnetic flux quantum 

# Simulation parameters
damping_values = (0.5, 1.0, 1.5, 3.0)  # Multiple Q values (first plot)
hk_val = 0.5                # Fixed H/H0 for the Q-sweep plot

# Single Q used for the magnetic-field sweep; must match one of damping_values so the
# hk=hk_val curve in figure 2 matches the corresponding curve in figure 1.
reference_q = 1.5
damping_q_for_h_sweep = reference_q

# Fraunhofer zeros at integer H/H0 → Ic→0; avoid those or results are ill-defined.
# Use several fields between zeros (e.g. 0.2–0.9) to see clear Ic(H) differences.
hk_values = (0.0, 0.3, 0.5, 0.7)

# One current sweep for every simulation — same bias points so curves are comparable.
currents = np.arange(-2.0, 2.05, 0.05)

def timeparams(damping):
    """Reasonable integration time parameters from the model."""
    val = damping[1]
    if val < 0.1:   return np.arange(0, 8000, 0.01), 0.8
    elif val < 1.:  return np.arange(0, 2000, 0.01), 0.6
    else:           return np.arange(0, 500, 0.01), 0.2

def findIc(hk):
    """Fraunhofer factor Ic(H)/Ic(0) = |sin(π H/H0)/(π H/H0)| (limit 1 at H=0)."""
    ic = 1.0
    if hk != 0:
        k = np.pi * hk
        ic *= abs(np.sin(k) / k)
    # Avoid division by zero at Fraunhofer nulls (integer H/H0).
    return max(float(abs(ic)), 1e-9)


def normalized_current_axis(currents, hk):
    """True I/Ic(H): same vertical axis as the ODE drive i / Ic(hk)."""
    return currents / findIc(hk)

# 2. ODE CALCULATIONS (RCSJ Model )
# -----------------------------------------------------------------------------
def rcsj_ode(y, t, i, damping, hk):
    """
    RCSJ Model Derivatives.
    y[0] = phase (phi), y[1] = dphi/dt (proportional to voltage) 
    """
    phi, dphi_dt = y
    Ic_normalized = findIc(hk)
    drive = i / Ic_normalized
    
    Q = damping[1]
    # Equation: d2phi/dt2 + (1/Q)dphi/dt + sin(phi) = I/Ic 
    return [dphi_dt, -dphi_dt / Q - np.sin(phi) + drive]

# 3. BI-DIRECTIONAL SIMULATION 
# -----------------------------------------------------------------------------
def run_full_sweep(current_array, damping, hk):
    t, tsamp = timeparams(damping)
    y0 = (0, 0) 
    idx_start = int(-tsamp * len(t))
    voltages = []
    
    for i in current_array:
        # Solve the ODE for the current step 
        sol = odeint(rcsj_ode, y0, t, args=(i, damping, hk))
        y0 = sol[-1, :] # Start next step from the final state of previous step 
        
        # Extract DC voltage (mean of the derivative dphi/dt) 
        vel = sol[idx_start:, 1]
        idx = argrelextrema(vel, np.greater)
        
        if len(idx[0]) < 2:
            avg_v = np.mean(vel)
            voltages.append(avg_v if abs(avg_v) > 1e-5 else 0)
        else:
            x1, x2 = idx[0][-2], idx[0][-1]
            voltages.append(np.mean(vel[x1:x2]))
            
    return np.array(voltages)


# 4. PLOTS — same `currents` for every curve; shared V/Q x-axis via sharex (no manual xlim)
# -----------------------------------------------------------------------------
i_over_ic_fig1 = normalized_current_axis(currents, hk_val)
damping_fixed = ('Q', damping_q_for_h_sweep)

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8, 10), sharex=True)
cmap_q = plt.cm.viridis(np.linspace(0.15, 0.9, len(damping_values)))

for j, damping_val in enumerate(damping_values):
    damping = ('Q', damping_val)
    v_out = run_full_sweep(currents, damping, hk_val)
    ax1.plot(
        v_out / damping_val,
        i_over_ic_fig1,
        '.-',
        color=cmap_q[j],
        label=f'Q={damping_val}, H/H0={hk_val}',
    )

ax1.axhline(0, color='black', lw=1)
ax1.axvline(0, color='black', lw=1)
ax1.set_ylabel(r'Normalized current $I/I_c(H)$')
ax1.set_title('V–I: sweep damping Q (fixed field)')
ax1.grid(True, linestyle='--', alpha=0.7)
ax1.legend()

cmap_h = plt.cm.plasma(np.linspace(0.15, 0.9, len(hk_values)))

for j, hk in enumerate(hk_values):
    v_out = run_full_sweep(currents, damping_fixed, hk)
    i_norm = normalized_current_axis(currents, hk)
    ax2.plot(
        v_out / damping_q_for_h_sweep,
        i_norm,
        '.-',
        color=cmap_h[j],
        label=f'H/H0={hk}, Q={damping_q_for_h_sweep}',
    )

if hk_val in hk_values:
    v_check = run_full_sweep(currents, ('Q', reference_q), hk_val)
    ax2.plot(
        v_check / reference_q,
        normalized_current_axis(currents, hk_val),
        'k--',
        lw=2,
        alpha=0.85,
        label=f'Cross-check: Q={reference_q}, H/H0={hk_val} (same as fig1)',
    )

ax2.axhline(0, color='black', lw=1)
ax2.axvline(0, color='black', lw=1)
ax2.set_xlabel('Normalized Voltage ($V/Q$)')
ax2.set_ylabel(r'Normalized current $I/I_c(H)$')
ax2.set_title('V–I: sweep magnetic field (fixed Q)')
ax2.grid(True, linestyle='--', alpha=0.7)
ax2.legend()

fig.tight_layout()
plt.show()
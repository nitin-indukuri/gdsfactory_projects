"""
Post-process Ngspice ``write … .plot`` binary raw files (e.g. ``spice4qucs.sp1.plot``)
and plot all vectors with matplotlib.

Requires: numpy, matplotlib

Example::

    from gplugin.ngspice_raw_plot import plot_spice4qucs_matplotlib
    plot_spice4qucs_matplotlib(\"spice4qucs.sp1.plot\")
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import numpy as np

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib.backends.backend_pdf import PdfPages


def read_ngspice_raw(path: str | Path) -> tuple[dict[str, Any], np.ndarray]:
    """
    Parse a raw file: ASCII header through ``Binary:``, then float64 (re, im) per variable per point.

    Returns
    -------
    meta : dict
        ``npoints``, ``nvars``, ``title``, ``plotname``, ``flags``, ``variables`` (list of
        ``{index, name, type}``).
    arr : ndarray, shape (npoints, nvars, 2)
        Real and imaginary part for each variable at each frequency/sample point.
    """
    path = Path(path)
    raw_bytes = path.read_bytes()
    if b"Binary:" not in raw_bytes:
        raise ValueError(f"No 'Binary:' section in {path}")

    bin_idx = raw_bytes.index(b"Binary:")
    header_bytes = raw_bytes[:bin_idx]
    nl = raw_bytes.find(b"\n", bin_idx)
    if nl == -1:
        raise ValueError("Malformed raw file: no newline after Binary:")
    data_bytes = raw_bytes[nl + 1 :]

    text = header_bytes.decode("latin-1", errors="replace")
    m_pts = re.search(r"No\.\s*Points:\s*(\d+)", text, re.I)
    m_vars = re.search(r"No\.\s*Variables:\s*(\d+)", text, re.I)
    if not m_pts or not m_vars:
        raise ValueError("Could not parse No. Points / No. Variables from header")
    npoints = int(m_pts.group(1))
    nvars = int(m_vars.group(1))

    meta: dict[str, Any] = {
        "npoints": npoints,
        "nvars": nvars,
        "title": "",
        "plotname": "",
        "flags": "",
        "variables": [],
    }
    m_title = re.search(r"^Title:\s*(.*)$", text, re.M)
    if m_title:
        meta["title"] = m_title.group(1).strip()
    m_plot = re.search(r"^Plotname:\s*(.*)$", text, re.M)
    if m_plot:
        meta["plotname"] = m_plot.group(1).strip()
    m_flags = re.search(r"^Flags:\s*(.*)$", text, re.M)
    if m_flags:
        meta["flags"] = m_flags.group(1).strip()

    in_vars = False
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("Variables"):
            in_vars = True
            continue
        if in_vars:
            if not s:
                continue
            parts = s.split()
            if len(parts) >= 2 and parts[0].isdigit():
                idx = int(parts[0])
                name = parts[1]
                vtype = parts[2] if len(parts) > 2 else ""
                meta["variables"].append({"index": idx, "name": name, "type": vtype})

    doubles = np.frombuffer(data_bytes, dtype=np.float64)
    expected = npoints * nvars * 2
    if doubles.size != expected:
        raise ValueError(
            f"Binary size mismatch: got {doubles.size} doubles, "
            f"expected {expected} (= {npoints} points × {nvars} vars × 2)"
        )
    arr = doubles.reshape(npoints, nvars, 2)
    return meta, arr


def _as_complex(arr: np.ndarray, i: int) -> np.ndarray:
    return arr[:, i, 0] + 1j * arr[:, i, 1]


def _freq_hz(arr: np.ndarray) -> np.ndarray:
    return arr[:, 0, 0]


def _idx_by_name(meta: dict, name: str) -> int | None:
    for v in meta["variables"]:
        if v["name"] == name:
            return v["index"]
    return None


def _set_log_y_tight(ax, pad_decades: float = 0.06) -> None:
    """Log y-axis with limits spanning data with small symmetric padding in log space."""
    ys = []
    for ln in ax.get_lines():
        y = np.asarray(ln.get_ydata(), dtype=float)
        y = y[np.isfinite(y)]
        if y.size:
            ys.append(y)
    if not ys:
        ax.set_yscale("linear")
        return
    yall = np.concatenate(ys)
    ypos = yall[yall > 0]
    if ypos.size == 0:
        ax.set_yscale("linear")
        ylo, yhi = float(np.min(yall)), float(np.max(yall))
        if ylo == yhi:
            ylo, yhi = ylo - 1.0, yhi + 1.0
        pad = 0.05 * max(abs(yhi - ylo), 1e-30)
        ax.set_ylim(ylo - pad, yhi + pad)
        return
    lo = float(np.min(ypos))
    hi = float(np.max(ypos))
    if lo == hi:
        lo, hi = lo * 0.5, hi * 2.0
        lo = max(lo, 1e-30)
    log_lo = np.log10(lo)
    log_hi = np.log10(hi)
    span = max(log_hi - log_lo, 1e-6)
    p = max(pad_decades, span * 0.08)
    ax.set_yscale("log")
    ax.set_ylim(10.0 ** (log_lo - p), 10.0 ** (log_hi + p))
    ax.yaxis.set_major_locator(mticker.LogLocator(base=10))
    ax.yaxis.set_minor_locator(mticker.LogLocator(base=10, subs=np.arange(2, 10)))
    ax.grid(True, which="major", ls="-", alpha=0.35)
    ax.grid(True, which="minor", ls=":", alpha=0.15)


def _set_linear_y_tight(ax, pad_frac: float = 0.06) -> None:
    ax.set_yscale("linear")
    ys = []
    for ln in ax.get_lines():
        y = np.asarray(ln.get_ydata(), dtype=float)
        y = y[np.isfinite(y)]
        if y.size:
            ys.append(y)
    if not ys:
        return
    yall = np.concatenate(ys)
    lo, hi = float(np.min(yall)), float(np.max(yall))
    if lo == hi:
        pad = max(abs(lo) * 0.1, 1.0)
        lo, hi = lo - pad, hi + pad
    else:
        span = hi - lo
        pad = max(span * pad_frac, 1e-30)
        lo, hi = lo - pad, hi + pad
    ax.set_ylim(lo, hi)
    ax.grid(True, which="major", ls="-", alpha=0.35)
    ax.grid(True, which="minor", ls=":", alpha=0.12)


def _set_phase_y_tight(ax) -> None:
    """Unwrapped phase in degrees: linear y, tight to curve."""
    _set_linear_y_tight(ax, pad_frac=0.04)


def _style_axes(
    ax,
    freq_ghz: np.ndarray,
    title: str,
    ylabel: str,
    *,
    y_mode: str = "linear_tight",
    xlabel: bool = True,
) -> None:
    """
    Linear frequency on x.

    y_mode: ``linear_tight`` (default), ``phase`` (degrees), or ``log_tight``.
    """
    ax.set_xlabel("Frequency (GHz)" if xlabel else "")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.set_xlim(float(freq_ghz.min()), float(freq_ghz.max()))
    ax.set_axisbelow(True)
    ax.grid(True, which="major", ls="-", alpha=0.25)
    if y_mode == "log_tight":
        _set_log_y_tight(ax)
    elif y_mode == "phase":
        ax.set_yscale("linear")
        _set_phase_y_tight(ax)
    else:
        _set_linear_y_tight(ax)


def plot_spice4qucs_matplotlib(
    plot_path: str | Path,
    *,
    out_dir: str | Path | None = None,
    pdf_name: str = "spice4qucs_plots.pdf",
    save_pdf: bool = True,
    save_png: bool = True,
) -> dict[str, Any]:
    """
    Load ``spice4qucs.sp1.plot`` (or any ngspice binary raw export) and plot every variable.

    Writes a multi-page PDF (S/Y/Z, noise, stability, etc.) and one PNG per variable under
    ``out_dir`` (default: ``<plot_dir>/plots_spice4qucs``).

    Parameters
    ----------
    plot_path
        Path to the ``.plot`` raw file.
    out_dir
        Output directory for PDF and PNGs.
    pdf_name
        Filename for the summary PDF (only if ``save_pdf``).
    save_pdf
        If True, write the multi-page overview PDF.
    save_png
        If True, write one PNG per variable.

    Returns
    -------
    dict with keys ``pdf_path`` (Path or None), ``out_dir``, ``meta``, ``frequency_hz``, ``data`` (ndarray).
    """
    path = Path(plot_path)
    meta, arr = read_ngspice_raw(path)
    f_hz = _freq_hz(arr)
    f_ghz = f_hz / 1e9

    base_out = Path(out_dir) if out_dir is not None else path.parent / "plots_spice4qucs"
    base_out.mkdir(parents=True, exist_ok=True)

    def db20(z: np.ndarray) -> np.ndarray:
        return 20.0 * np.log10(np.maximum(np.abs(z), 1e-30))

    pdf_path_out: Path | None = None
    if save_pdf:
        pdf_path_out = base_out / pdf_name
        with PdfPages(pdf_path_out) as pdf:
            fig, ax = plt.subplots(figsize=(10, 6))
            for lbl in ("s11_db", "s12_db", "s21_db", "s22_db"):
                j = _idx_by_name(meta, lbl)
                if j is not None:
                    ax.plot(f_ghz, arr[:, j, 0], label=lbl)
            ax.legend(loc="best")
            _style_axes(
                ax,
                f_ghz,
                meta.get("title", "") + " — S-parameter (dB)",
                "dB",
                y_mode="linear_tight",
            )
            fig.tight_layout()
            pdf.savefig(fig)
            plt.close(fig)

            fig, axes = plt.subplots(2, 2, figsize=(10, 8), sharex=True)
            spairs = [
                ("s_1_1", "S11"),
                ("s_1_2", "S12"),
                ("s_2_1", "S21"),
                ("s_2_2", "S22"),
            ]
            for ax, (nm, lab) in zip(axes.flat, spairs):
                j = _idx_by_name(meta, nm)
                if j is None:
                    continue
                s = _as_complex(arr, j)
                ax.plot(f_ghz, np.abs(s), label=lab)
                _style_axes(ax, f_ghz, lab + " magnitude", "|S|", y_mode="linear_tight")
                ax.legend()
            fig.suptitle("S-parameter magnitudes |S|")
            fig.tight_layout()
            pdf.savefig(fig)
            plt.close(fig)

            fig, axes = plt.subplots(2, 2, figsize=(10, 8), sharex=True)
            for ax, (nm, lab) in zip(axes.flat, spairs):
                j = _idx_by_name(meta, nm)
                if j is None:
                    continue
                s = _as_complex(arr, j)
                ph = np.unwrap(np.angle(s))
                ax.plot(f_ghz, np.degrees(ph))
                _style_axes(ax, f_ghz, lab + " phase", "Phase (deg)", y_mode="phase")
            fig.suptitle("S-parameter phase (unwrapped)")
            fig.tight_layout()
            pdf.savefig(fig)
            plt.close(fig)

            fig, ax = plt.subplots(figsize=(10, 6))
            for nm, lab in (("nf", "NF"), ("nfmin", "NFmin")):
                j = _idx_by_name(meta, nm)
                if j is not None:
                    ax.plot(f_ghz, arr[:, j, 0], label=lab)
            ax.legend(loc="upper left")
            _style_axes(
                ax,
                f_ghz,
                "Noise figure",
                "dB",
                y_mode="linear_tight",
            )
            j_rn = _idx_by_name(meta, "rn")
            if j_rn is not None:
                ax2 = ax.twinx()
                ax2.plot(
                    f_ghz,
                    arr[:, j_rn, 0],
                    color="C3",
                    ls="--",
                    alpha=0.8,
                    label="Rn",
                )
                ax2.set_ylabel("Rn (Ω)")
                ax2.legend(loc="upper right")
                _set_linear_y_tight(ax2)
                ax2.grid(True, which="major", ls="-", alpha=0.2)
            fig.tight_layout()
            pdf.savefig(fig)
            plt.close(fig)

            fig, ax = plt.subplots(figsize=(10, 6))
            for nm in ("kf", "mu", "muprime"):
                j = _idx_by_name(meta, nm)
                if j is not None:
                    rval, ival = arr[:, j, 0], arr[:, j, 1]
                    z = np.abs(rval + 1j * ival) if np.max(np.abs(ival)) > 1e-12 else rval
                    ax.plot(f_ghz, np.abs(z), label=nm)
            ax.axhline(1.0, color="k", ls=":", lw=1, alpha=0.6)
            ax.legend()
            _style_axes(
                ax,
                f_ghz,
                "Stability factors (|Kf|, |μ|, |μ′|)",
                "magnitude",
                y_mode="linear_tight",
            )
            fig.tight_layout()
            pdf.savefig(fig)
            plt.close(fig)

            fig, ax1 = plt.subplots(figsize=(10, 6))
            j_g = _idx_by_name(meta, "gmax")
            if j_g is not None:
                g = _as_complex(arr, j_g)
                ax1.plot(f_ghz, np.abs(g), label="|Gmax|")
            j_f = _idx_by_name(meta, "fmax")
            if j_f is not None:
                fv = arr[:, j_f, 0]
                ax1.plot(f_ghz, np.abs(fv), label="|Fmax|")
            ax1.legend(loc="upper left")
            _style_axes(
                ax1,
                f_ghz,
                "Gain / frequency metric",
                "|.|",
                y_mode="linear_tight",
            )
            j_d = _idx_by_name(meta, "delta")
            if j_d is not None:
                ax2 = ax1.twinx()
                d = _as_complex(arr, j_d)
                ax2.plot(
                    f_ghz,
                    np.abs(d),
                    color="C3",
                    ls="--",
                    alpha=0.85,
                    label="|Δ|",
                )
                ax2.set_ylabel("|Δ|")
                ax2.legend(loc="center right")
                _set_linear_y_tight(ax2)
                ax2.grid(True, which="major", ls="-", alpha=0.2)
            fig.tight_layout()
            pdf.savefig(fig)
            plt.close(fig)

            fig, axes = plt.subplots(2, 2, figsize=(10, 8), sharex=True)
            yz = [
                ("y_1_1", "Y11"),
                ("y_1_2", "Y12"),
                ("y_2_1", "Y21"),
                ("y_2_2", "Y22"),
            ]
            for ax, (nm, lab) in zip(axes.flat, yz):
                j = _idx_by_name(meta, nm)
                if j is None:
                    continue
                y = _as_complex(arr, j)
                ax.plot(f_ghz, np.abs(y))
                _style_axes(ax, f_ghz, lab + " |Y|", "|Y|", y_mode="linear_tight")
            fig.suptitle("Y-parameter |Y|")
            fig.tight_layout()
            pdf.savefig(fig)
            plt.close(fig)

            fig, axes = plt.subplots(2, 2, figsize=(10, 8), sharex=True)
            zz = [
                ("z_1_1", "Z11"),
                ("z_1_2", "Z12"),
                ("z_2_1", "Z21"),
                ("z_2_2", "Z22"),
            ]
            for ax, (nm, lab) in zip(axes.flat, zz):
                j = _idx_by_name(meta, nm)
                if j is None:
                    continue
                zv = _as_complex(arr, j)
                ax.plot(f_ghz, np.abs(zv))
                _style_axes(ax, f_ghz, lab + " |Z|", "|Z|", y_mode="linear_tight")
            fig.suptitle("Z-parameter |Z|")
            fig.tight_layout()
            pdf.savefig(fig)
            plt.close(fig)

            fig, ax = plt.subplots(figsize=(10, 6))
            for v in meta["variables"]:
                if v["name"].startswith("i(cy_"):
                    j = v["index"]
                    c = _as_complex(arr, j)
                    ax.plot(f_ghz, np.abs(c), label=v["name"])
            ax.legend(loc="best", fontsize=8)
            _style_axes(ax, f_ghz, "Correlated port currents", "|I|", y_mode="linear_tight")
            fig.tight_layout()
            pdf.savefig(fig)
            plt.close(fig)

            used = {
                "s11_db",
                "s12_db",
                "s21_db",
                "s22_db",
                "s_1_1",
                "s_1_2",
                "s_2_1",
                "s_2_2",
                "y_1_1",
                "y_1_2",
                "y_2_1",
                "y_2_2",
                "z_1_1",
                "z_1_2",
                "z_2_1",
                "z_2_2",
                "nf",
                "nfmin",
                "rn",
                "kf",
                "mu",
                "muprime",
                "gmax",
                "fmax",
                "delta",
            }
            used.update(
                {v["name"] for v in meta["variables"] if v["name"].startswith("i(cy_")}
            )
            remaining = [
                v for v in meta["variables"] if v["name"] not in used and v["index"] != 0
            ]
            if remaining:
                n = len(remaining)
                ncols = 3
                nrows = int(np.ceil(n / ncols))
                fig, axes = plt.subplots(nrows, ncols, figsize=(12, 3 * nrows), sharex=True)
                axes_flat = np.atleast_1d(axes).ravel()
                for k, v in enumerate(remaining):
                    ax = axes_flat[k]
                    j = v["index"]
                    rval = arr[:, j, 0]
                    ival = arr[:, j, 1]
                    if np.max(np.abs(ival)) > 1e-12 * max(np.max(np.abs(rval)), 1.0):
                        ax.plot(f_ghz, np.abs(rval + 1j * ival), label="|.|")
                        _style_axes(
                            ax, f_ghz, v["name"], "|.|", y_mode="linear_tight"
                        )
                    else:
                        ax.plot(f_ghz, rval)
                        _style_axes(
                            ax,
                            f_ghz,
                            v["name"],
                            v.get("type", "value"),
                            y_mode="linear_tight",
                        )
                for ax in axes_flat[n:]:
                    ax.set_visible(False)
                fig.suptitle("Other saved variables (real or |complex|)")
                fig.tight_layout()
                pdf.savefig(fig)
                plt.close(fig)

    if save_png:
        for v in meta["variables"]:
            j = v["index"]
            name = v["name"]
            safe = re.sub(r"[^\w.\-]+", "_", name)
            rval = arr[:, j, 0]
            ival = arr[:, j, 1]
            if np.max(np.abs(ival)) > 1e-15 * max(np.max(np.abs(rval)), 1e-30):
                z = rval + 1j * ival
                fig, (axm, axp) = plt.subplots(
                    2, 1, figsize=(8, 6.5), sharex=True, gridspec_kw={"height_ratios": [1.1, 1]}
                )
                axm.plot(f_ghz, np.abs(z))
                _style_axes(
                    axm,
                    f_ghz,
                    f"{name} ({v.get('type', '')}) — magnitude",
                    "|.|",
                    y_mode="linear_tight",
                    xlabel=False,
                )
                axp.plot(f_ghz, np.angle(z, deg=True))
                _style_axes(
                    axp,
                    f_ghz,
                    f"{name} — phase",
                    "Phase (deg)",
                    y_mode="phase",
                )
                fig.tight_layout()
            else:
                fig, ax = plt.subplots(figsize=(8, 4.5))
                vt = str(v.get("type", "")).lower()
                ax.plot(f_ghz, rval)
                if name.endswith("_db") or vt == "decibel" or name in ("nf", "nfmin"):
                    ylab = "dB"
                else:
                    ylab = v.get("type", "value")
                _style_axes(
                    ax,
                    f_ghz,
                    f"{name} ({v.get('type', '')})",
                    ylab,
                    y_mode="linear_tight",
                )
                fig.tight_layout()
            fig.savefig(base_out / f"{safe}.png", dpi=150)
            plt.close(fig)

    return {
        "pdf_path": pdf_path_out,
        "out_dir": base_out,
        "meta": meta,
        "frequency_hz": f_hz,
        "data": arr,
    }


def plot_all(
    plot_path: str | Path,
    out_dir: str | Path | None = None,
    pdf_name: str = "spice4qucs_plots.pdf",
) -> Path:
    """Backward-compatible alias: returns PDF path only (raises if ``save_pdf`` is False)."""
    r = plot_spice4qucs_matplotlib(
        plot_path, out_dir=out_dir, pdf_name=pdf_name, save_pdf=True, save_png=True
    )
    p = r["pdf_path"]
    if p is None:
        raise RuntimeError("PDF was not generated")
    return p

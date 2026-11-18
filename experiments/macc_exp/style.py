"""Plot style. `paper` reproduces the look of the T-RO figures (serif fonts,
green/red colours); `clean` uses a colour-blind-validated pair."""

from __future__ import annotations

import shutil

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import AutoMinorLocator  # noqa: E402

PALETTES = {
    # colours of the original scripts (cg2o green, competitor red)
    "paper": {"a": "#1eff00", "b": "#fa000095", "host": "#0000ff", "preceding": "#fa00fa",
              "accent": "#0000ff"},
    # categorical slots 1 and 2 of the validated reference palette
    "clean": {"a": "#2a78d6", "b": "#eb6834", "host": "#2a78d6", "preceding": "#e87ba4",
              "accent": "#52514e"},
}

# one colour per linear solver in the sweep chart (fixed order, never cycled)
CATEGORICAL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
GOOD = "#1baf7a"
MUTED = "#8b8a85"

LINE_WIDTH = 1.15


def apply(palette: str = "paper", latex: bool = False, dpi: int = 200) -> dict:
    """Set the global matplotlib style and return the colour dictionary."""
    use_tex = bool(latex and shutil.which("latex") and shutil.which("dvipng"))
    plt.rcParams.update({
        "font.family": "serif",
        "font.serif": ["Times New Roman", "Times", "Liberation Serif", "Nimbus Roman",
                       "STIXGeneral", "DejaVu Serif"],
        "mathtext.fontset": "stix",
        "text.usetex": use_tex,
        "font.size": 8,
        "axes.titlesize": 8,
        "axes.labelsize": 7.5,
        "xtick.labelsize": 7,
        "ytick.labelsize": 7,
        "legend.fontsize": 7,
        "figure.dpi": dpi,
        "savefig.dpi": dpi,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.linewidth": 0.6,
    })
    return PALETTES[palette]


def dense_grid(ax, x_minor: int = 4, y_minor: int = 4) -> None:
    ax.minorticks_on()
    ax.xaxis.set_minor_locator(AutoMinorLocator(x_minor))
    ax.yaxis.set_minor_locator(AutoMinorLocator(y_minor))
    ax.grid(True, which="major", linewidth=0.7, alpha=0.45)
    ax.grid(True, which="minor", linewidth=0.35, alpha=0.2)
    ax.set_axisbelow(True)

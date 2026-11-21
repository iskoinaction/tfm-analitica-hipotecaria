"""Figura comparativa de las series nacionales (original nb 4.2 vs auditada)."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from common import FIG, build_clean, build_original, national_raw

Yo = build_original(); Yc = build_clean(weighted=True, end="2024-10-01")
fig, ax = plt.subplots(1, 5, figsize=(18, 3.2))
for i, c in enumerate(Yo.columns):
    ax[i].plot(Yo.index, Yo[c], color="#c0504d", lw=1.4, label="original nb4.2 (media simple, 2025 arrastrado)")
    ax[i].plot(Yc.index, Yc[c], color="#1f3b70", lw=1.4, ls="--", label="auditada (ponderada pobl., hasta 2024Q4)")
    ax[i].axvspan(np.datetime64("2025-01-01"), np.datetime64("2025-10-01"), color="orange", alpha=.15)
    ax[i].set_title(c, fontsize=9); ax[i].grid(alpha=.2)
ax[0].legend(fontsize=6.5)
fig.tight_layout(); fig.savefig(FIG / "series_nacionales.png", dpi=110)

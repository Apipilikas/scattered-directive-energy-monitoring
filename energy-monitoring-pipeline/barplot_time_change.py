import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path

# Dummy relative execution time change (%) compared with the synchronous VFL baseline.
methods = ["FedBCD", "Overlap-FedBCD", "FedEncrypt"]
environments = ["Local", "FABRIC"]

changes = {
    "Local": [-12.40, -18.75, 235.60],
    "FABRIC": [-45.10, -39.85, 312.45],
}

x = np.arange(len(methods))
width = 0.34
colors = ["#4C78A8", "#F58518"]

# Single-column subfigure size for readable side-by-side placement.
fig, ax = plt.subplots(figsize=(2.45, 2.05), constrained_layout=True)

for i, environment in enumerate(environments):
    offset = (i - 0.5) * width

    bars = ax.bar(
        x + offset,
        changes[environment],
        width,
        label=environment,
        color=colors[i],
        edgecolor="white",
        linewidth=0.8,
    )

    for bar, value in zip(bars, changes[environment]):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            value * 0.18,
            f"{value:+.2f}%",
            ha="center",
            va="center",
            rotation=90,
            fontsize=5.5,
            color="white",
            clip_on=True,
        )

ax.axhline(0, color="#333333", linewidth=1)

ax.set_xticks(x)
ax.set_xticklabels(methods, rotation=20, ha="right", fontsize=6)
ax.set_ylabel("Time change (%)", fontsize=7)
ax.tick_params(axis="y", labelsize=6)

ax.legend(
    title="Execution environment",
    frameon=False,
    fontsize=5.5,
    title_fontsize=6,
    ncols=1,
    loc="upper left",
)

ax.set_yscale("symlog", linthresh=10, linscale=1)
ax.set_ylim(-100, 500)

ax.spines[["top", "right"]].set_visible(False)
ax.grid(axis="y", which="both", linestyle=":", alpha=0.45)
ax.set_axisbelow(True)

output_path = Path(__file__).with_name("relative_time_change_2col.png")
fig.savefig(output_path, dpi=600, bbox_inches="tight")

plt.show()
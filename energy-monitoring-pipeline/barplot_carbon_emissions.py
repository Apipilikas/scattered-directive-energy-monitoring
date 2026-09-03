import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
from matplotlib.patches import Patch
import matplotlib.patheffects as pe

# Dummy totals for FABRIC across three methods.
methods = ["FedBCD", "Overlap-FedBCD", "Fed-Encrypt"]
components = ["LOSA", "AMST", "TOKY"]

carbon_emissions = {
    "FedBCD": [10.2, 6.1, 3.4],
    "Overlap-FedBCD": [13.1, 7.4, 4.8],
    "FedEncrypt": [15.6, 9.2, 5.7],
}

energy_consumption = {
    "FedBCD": [8.9, 5.3, 2.8],
    "Overlap-FedBCD": [10.8, 6.2, 3.9],
    "FedEncrypt": [13.7, 7.8, 4.9],
}

carbon_totals = {method: sum(values) for method, values in carbon_emissions.items()}
energy_totals = {method: sum(values) for method, values in energy_consumption.items()}

x = np.arange(len(methods))
bar_width = 0.32
colors = ["#4C78A8", "#F58518", "#54A24B"]

# Wider figure to fit two stacked bars per method.
fig, ax = plt.subplots(figsize=(5.1, 3.0), constrained_layout=True)
ax_energy = ax.twinx()

x_carbon = x - bar_width / 2
x_energy = x + bar_width / 2

bottom_carbon = np.zeros(len(methods))
bottom_energy = np.zeros(len(methods))

for component_index, location in enumerate(components):
    carbon_values = [carbon_emissions[method][component_index] for method in methods]
    energy_values = [energy_consumption[method][component_index] for method in methods]

    bars_carbon = ax.bar(
        x_carbon,
        carbon_values,
        bar_width,
        bottom=bottom_carbon,
        label=location,
        color=colors[component_index],
        edgecolor="white",
        linewidth=0.8,
    )

    bars_energy = ax_energy.bar(
        x_energy,
        energy_values,
        bar_width,
        bottom=bottom_energy,
        label="_nolegend_",
        color=colors[component_index],
        edgecolor="white",
        linewidth=0.8,
        hatch="///",
    )

    for bar, value, base, method in zip(bars_carbon, carbon_values, bottom_carbon, methods):
        total = carbon_totals[method]
        percentage = (value / total) * 100 if total else 0
        carbon_label = ax.text(
            bar.get_x() + bar.get_width() / 2,
            base + value / 2,
            f"{percentage:.0f}%",
            ha="center",
            va="center",
            fontsize=5.4,
            fontweight="bold",
            color="white",
            rotation=90,
            clip_on=True,
        )
        carbon_label.set_path_effects([pe.withStroke(linewidth=1.25, foreground="black")])

    for bar, value, base, method in zip(bars_energy, energy_values, bottom_energy, methods):
        total = energy_totals[method]
        percentage = (value / total) * 100 if total else 0
        ax_energy.text(
            bar.get_x() + bar.get_width() / 2,
            base + value / 2,
            f"{percentage:.0f}%",
            ha="center",
            va="center",
            fontsize=5.4,
            fontweight="bold",
            color="#111111",
            rotation=90,
            clip_on=True,
            bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.7, "pad": 0.2},
        )

    bottom_carbon = bottom_carbon + np.array(carbon_values)
    bottom_energy = bottom_energy + np.array(energy_values)

for xi_carbon, xi_energy, method in zip(x_carbon, x_energy, methods):
    carbon_total = carbon_totals[method]
    energy_total = energy_totals[method]
    ax.text(
        xi_carbon,
        carbon_total + 0.45,
        f"C: {carbon_total:.1f}",
        ha="center",
        va="bottom",
        fontsize=6,
    )
    ax_energy.text(
        xi_energy,
        energy_total + 0.45,
        f"E: {energy_total:.1f}",
        ha="center",
        va="bottom",
        fontsize=6,
    )

ax.set_xticks(x)
ax.set_xticklabels(methods, rotation=18, ha="right", fontsize=6)
ax.set_ylabel("Carbon emissions (kg CO2e)", fontsize=7)
ax.tick_params(axis="y", labelsize=6)
ax_energy.set_ylabel("Energy consumption (kWh)", fontsize=7)
ax_energy.tick_params(axis="y", labelsize=6)

location_legend = ax.legend(
    title="Location",
    frameon=False,
    fontsize=5.5,
    title_fontsize=6,
    ncols=1,
    loc="upper left",
)
ax.add_artist(location_legend)

metric_handles = [
    Patch(facecolor="#CCCCCC", edgecolor="white", label="Carbon"),
    Patch(facecolor="#CCCCCC", edgecolor="white", hatch="///", label="Energy"),
]
ax.legend(
    handles=metric_handles,
    title="Metric",
    frameon=False,
    fontsize=5.5,
    title_fontsize=6,
    loc="upper right",
)

max_carbon_total = max(carbon_totals.values())
max_energy_total = max(energy_totals.values())
ax.set_ylim(0, max_carbon_total + 4)
ax_energy.set_ylim(0, max_energy_total + 4)
ax.spines[["top"]].set_visible(False)
ax.spines[["right"]].set_visible(False)
ax_energy.spines[["top"]].set_visible(False)
ax_energy.spines[["right"]].set_visible(True)
ax.grid(axis="y", linestyle=":", alpha=0.45)
ax.set_axisbelow(True)

output_path = Path(__file__).with_name("carbon_emissions_fabric_methods_2col.pdf")
fig.savefig(output_path, dpi=600, bbox_inches="tight")

plt.show()
import pandas as pd
import matplotlib.pyplot as plt
import configuration as conf
import json
import argparse
import utils
from scipy.stats import kendalltau
import numpy as np
import seaborn as sns

CORRELATION_CONFIG = {
        "Baseline": "baseline_experiment",
        "Event-driven": "baseline_event_driven",
        "Fed-BCD": "fed_bcd_experiment",
        "Overlap-Fed-BCD": "overlap_fed_bcd_experiment",
        "Fed-Encrypt": "fed_encrypt_experiment"
    }

CORRELATION_COLUMNS = [
    ("total_carbon_emission_difference","Carbon Emission (gCO2e/KWh)", "cab", 1000),
    ("execution_time","Execution Time (s)", "ex", 1)
]

def main():
    plot_sidecar, plot_accuracies, plot_correlation, plot_box, is_local, both_environments = _resolve_args()

    print(f"============= Generate plots =============")
    
    if plot_sidecar:
        _generate_sidecar_plot()

    if plot_correlation:
        _generate_correlation_plot(is_local, both_environments)
        _generate_mean_correlation_plot(is_local, both_environments)
        _generate_correlation_matrix(is_local, both_environments)

    if plot_accuracies:
        _generate_accuracies_plot()

    if plot_box:
        _generate_box_plot(is_local, both_environments)

def _generate_sidecar_plot():
    print("> Generating sidecar plot")
    data = pd.read_csv("output/data_metrics.csv")

    time_seconds = data.index * 30  

    plt.figure(figsize=(10, 6))

    min_time = time_seconds.min()  # This will be 0
    max_time = time_seconds.max()
    cutoff_time = 120  # The 120-second mark

    for column_name in data.columns:
        if column_name.endswith("_energy"):        
            energy_data = data[column_name]
            container_name = column_name.replace("_energy", "")
            
            plt.plot(time_seconds, energy_data, linestyle='-', label=container_name)


    plt.axvline(x=cutoff_time, color='red', linestyle='--', linewidth=2)
    plt.axvspan(min_time, cutoff_time, color='gray', alpha=0.15, label='Idle Period')
    plt.axvspan(cutoff_time, max_time, color='lightgray', alpha=0.15, label='Active Period')

    plt.xlabel('Time (Seconds)') 
    plt.ylabel('Energy (in J)')
    plt.grid(True, linestyle='--', alpha=0.7)
    plt.legend()

    # Display the plot
    file_name = f"{conf.PLOT_OUTPUT_FOLDER}/sidecar_plot.png"
    plt.savefig(file_name)
    plt.close()
    print(f"Plot saved in {file_name}!")

def _resolve_mode_name(is_local, both_environments = False):
    return "both" if both_environments else ("local" if is_local else "fabric")

def _generate_mean_correlation_plot(is_local, both_environments):
    for column_name, column_label, column_prefix, column_scale in CORRELATION_COLUMNS:
        _generate_mean_correlation_plot_by_column(column_name, column_label, column_prefix, column_scale, is_local, both_environments)  

def _generate_mean_correlation_plot_by_column(column_name, column_label, column_prefix, column_scale, is_local, both_environments):
    print(f"> Generating mean correlation plot for column : {column_name}")

    plt.figure(figsize=(6, 5))
    
    if not CORRELATION_CONFIG:
        print("Warning: No JSON files found in the output folder.")
        return

    x = []
    y = []

    def _plot(is_local: bool, include_mode_in_label: bool):
        for name, file_prefix in CORRELATION_CONFIG.items():
            total_metrics_data, _, _ = utils.read_experiments_by_prefix(file_prefix, is_local)
            
            x_val = total_metrics_data[column_name].mean()*column_scale
            y_val = total_metrics_data["total_energy_difference"].mean()
            
            x.append(x_val)
            y.append(y_val)

            if include_mode_in_label:
                name = f"{name}_{_resolve_mode_name(is_local)}"

            plt.scatter(x_val, y_val, label=name, alpha=0.7, s=100)

    _plot(is_local, both_environments)

    if both_environments:
        _plot(not is_local, both_environments)

    if len(x) > 1:        
        slope, intercept = np.polyfit(x, y, 1)
        
        x_line = np.linspace(min(x) * 0.9, max(x) * 1.1, 100)
        y_line = slope * x_line + intercept
        
        plt.plot(x_line, y_line, color='gray', linestyle='--', alpha=0.5, label=f"Linear Fit")

    plt.xlabel(f"Mean {column_label}")
    plt.ylabel("Mean Energy Consumption (J)") 
    
    plt.legend()
    plt.grid(True, linestyle='--', alpha=0.6)
    plt.tight_layout()

    file_name = f"{conf.PLOT_OUTPUT_FOLDER}/en_{column_prefix}_mean_correlation_{_resolve_mode_name(is_local, both_environments)}_plot.pdf"
    plt.savefig(file_name, bbox_inches='tight')
    plt.close()
    print(f"Plot saved in {file_name}!")

def _generate_correlation_plot(is_local, both_environments):
    for column_name, column_label, column_prefix, column_scale in CORRELATION_COLUMNS:
        _generate_correlation_plot_by_column(column_name, column_label, column_prefix, column_scale, is_local, both_environments)   

def _generate_correlation_plot_by_column(column_name, column_label, column_prefix, column_scale, is_local, both_environments):
    print(f"> Generating correlation plot for column: {column_name}")
    plt.figure(figsize=(6, 5))
    
    x = []
    y = []

    def _plot(is_local: bool, include_mode_in_label: bool):
        for name, file_prefix in CORRELATION_CONFIG.items():
            total_metrics_data, _, _ = utils.read_experiments_by_prefix(file_prefix, is_local)
            
            x_val = total_metrics_data[column_name]*column_scale
            y_val = total_metrics_data["total_energy_difference"]
            
            x.extend(x_val.tolist())
            y.extend(y_val.tolist())

            if include_mode_in_label:
                name = f"{name}_{_resolve_mode_name(is_local)}"

            plt.scatter(x_val, y_val, label=name, alpha=0.7, s=30)

    _plot(is_local, both_environments)

    if both_environments:
        _plot(not is_local, both_environments)

    x = np.array(x)
    y = np.array(y)

    if len(x) > 1:
        tau, p_value = kendalltau(x, y)
        
        slope, intercept = np.polyfit(x, y, 1)
        
        x_line = np.linspace(x.min(), x.max(), 100)
        y_line = slope * x_line + intercept
        
        plt.plot(x_line, y_line, color='gray', linestyle='--', alpha=0.5, label=f"Linear Fit (τ={tau:.2f})")

    plt.xlabel(column_label)
    plt.ylabel("Energy Consumption (J)") 
    
    plt.legend()
    plt.grid(True, linestyle='--', alpha=0.6)
    plt.tight_layout()

    label = _resolve_mode_name(is_local, both_environments)

    file_name = f"{conf.PLOT_OUTPUT_FOLDER}/en_{column_prefix}_correlation_{label}_plot.pdf"
    plt.savefig(file_name, bbox_inches='tight')
    plt.close()
    print(f"Plot saved in {file_name}!")

def _generate_correlation_matrix(is_local, both_environments):
    print("> Generating correlation matrix heatmap")
    
    combined_frames = []

    def _read_data(is_local):
        for name, file_prefix in CORRELATION_CONFIG.items():
            total_metrics_data, _, _ = utils.read_experiments_by_prefix(file_prefix, is_local)
            
            df_copy = total_metrics_data.copy()
            df_copy['experiment_type'] = name 
            combined_frames.append(df_copy)

    _read_data(is_local)

    if both_environments:
        _read_data(not is_local)

    if not combined_frames:
        return

    master_df = pd.concat(combined_frames, ignore_index=True)

    columns_to_include = [
        "total_carbon_emission_difference",
        "total_energy_difference",
        "execution_time"
    ]

    rename_columns = {
        "total_carbon_emission_difference": "Carbon Emission (gCO2e/KWh)",
        "total_energy_difference": "Energy Consumption (J)",
        "execution_time": "Execution Time (s)"
    }

    valid_columns = [col for col in columns_to_include if col in master_df.columns]

    filtered_df = master_df[valid_columns].rename(columns=rename_columns)

    corr_matrix = filtered_df.corr(method='kendall')
    corr_matrix = corr_matrix.iloc[::-1]

    plt.figure(figsize=(10, 10))

    # cmap_custom = sns.light_palette("seagreen", as_cmap=True)
    cmap_custom = sns.color_palette("vlag", as_cmap=True)
    
    sns.heatmap(
        corr_matrix, 
        annot=True,
        fmt=".3f",
        cmap=cmap_custom,
        vmin=-1, vmax=1,
        center=0,
        square=True,
        linewidths=0.5,      
        cbar_kws={"shrink": .8}
    )

    plt.tight_layout()

    file_name = f"{conf.PLOT_OUTPUT_FOLDER}/correlation_{_resolve_mode_name(is_local, both_environments)}_matrix.pdf"
    plt.savefig(file_name, bbox_inches='tight')
    plt.close()
    print(f"Correlation matrix saved in {file_name}!")

def _generate_accuracies_plot():
    print("> Generating accuracies plot")
    
    plt.figure(figsize=(10, 6))
    
    json_files = {
        "Baseline": "experiments/fabric/baseline_experiment_260623_1609/experiments.json",
        "Fed-BCD": "experiments/fabric/fed_bcd_experiment_260623_1411/experiments.json",
        "Overlap-Fed-BCD": "experiments/fabric/overlap_fed_bcd_experiment_260625_1502/experiments.json",
        "Fed-Encrypt": "experiments/fabric/fed_encrypt_experiment_260626_2016/experiments.json"
    }
    
    if not json_files:
        print("Warning: No JSON files found in the output folder.")
        return


    for name, file_path in json_files.items():
        try:
            with open(file_path, 'r') as f:
                metrics_data = json.load(f)
            
            run_data = metrics_data["0"]
            accuracies_list = run_data["accuracies"]
            
            if not accuracies_list:
                continue
            
            rounds = [item["train_round"] for item in accuracies_list]
            accuracies = [item["accuracy"] for item in accuracies_list]

            if name == "Fed-Encrypt":
                # There is an issue that accuracies in Fed-encrypt returns the float value not %.
                accuracies = [item["accuracy"] * 100 for item in accuracies_list]
            
            
            plt.plot(rounds, accuracies, marker='o', linestyle='-', alpha=0.8, label=name)
                
        except Exception as e:
            print(f"Error processing accuracy data for {file_path}: {e}")

    plt.xlabel('Train Round')
    plt.ylabel('Accuracy (%)')
    # plt.title('Model accuracy per training round')
    plt.grid(True, linestyle='--', alpha=0.6)
    
    plt.ylim(0, 100)

    plt.gca().xaxis.get_major_locator().set_params(integer=True)
    
    plt.legend(loc='lower right')

    file_name = f"{conf.PLOT_OUTPUT_FOLDER}/accuracies_plot.pdf"
    plt.savefig(file_name, bbox_inches='tight')
    plt.close()
    print(f"Plot saved in {file_name}!")

def _generate_box_plot(is_local, both_environments):
    print("> Generating box plot")

    plt.figure(figsize=(10, 5))

    data = {}

    def _read_data(is_local: bool, include_mode_in_label: bool):
        for name, file_prefix in CORRELATION_CONFIG.items():
            total_metrics_data, _, _ = utils.read_experiments_by_prefix(file_prefix, is_local)

            if include_mode_in_label:
                name = f"{name}_{_resolve_mode_name(is_local)}"

            data[name] = total_metrics_data["total_carbon_emission_difference"]*1000
            # data[name] = total_metrics_data["total_energy_difference"]

    _read_data(is_local, both_environments)

    if both_environments:
        _read_data(not is_local, both_environments)

    labels = sorted(data.keys())
    
    x = [data[label] for label in labels]

    plt.boxplot(x, tick_labels=labels)
    plt.xticks(rotation=20, ha='right')

    plt.ylabel("Carbon Emission (gCO2e/KWh)")
    # plt.ylabel("Energy Consumption (J)")
    plt.xlabel("Mitigation Strategies")
    file_name = f"{conf.PLOT_OUTPUT_FOLDER}/cab_box_{_resolve_mode_name(is_local, both_environments)}_plot.pdf"
    plt.tight_layout()
    plt.savefig(file_name)
    plt.close()
    print(f"Plot saved in {file_name}!")

def _resolve_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("-sid", "--sidecar", action='store_true')
    parser.add_argument("-acc", "--accuracies", action='store_true')
    parser.add_argument("-cor", "--correlation", action='store_true')
    parser.add_argument("-box", "--box-plot", action='store_true')
    utils.add_boolean_argument(parser, conf.F_ARGUMENT)
    utils.add_boolean_argument(parser, conf.BE_ARGUMENT)

    args = parser.parse_args()
    plot_sidecar = args.sidecar
    plot_accuracies = args.accuracies
    plot_correlation = args.correlation
    plot_box = args.box_plot

    return plot_sidecar, plot_accuracies, plot_correlation, plot_box, not args.fabric_mode, args.both_environments


if __name__ == '__main__':
    main()
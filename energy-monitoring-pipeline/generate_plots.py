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

CORRELATION_COLUMN = ("total_carbon_emission_difference","Carbon Emission (gCO2e/KWh)", "cab", 1000)
# CORRELATION_COLUMN = ("execution_time","Execution Time (s)", "ex", 1)

CORRELATION_COLUMN_NAME, CORRELATION_COLUMN_LABEL, CORRELATION_COLUMN_PREFIX, CORRELATION_COLUMN_SCALE = CORRELATION_COLUMN

def main():
    plot_sidecar, plot_accuracies, plot_correlation = _resolve_args()

    print(f"============= Generate plots =============")
    
    if plot_sidecar:
        _generate_sidecar_plot()

    if plot_correlation:
        _generate_correlation_plot()
        _generate_mean_correlation_plot()
        _generate_correlation_matrix()

    if plot_accuracies:
        _generate_accuracies_plot()

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

def _generate_mean_correlation_plot():
    print("> Generating mean correlation plot")
    
    plt.figure(figsize=(6, 5))
    
    if not CORRELATION_CONFIG:
        print("Warning: No JSON files found in the output folder.")
        return

    x = []
    y = []

    for name, file_prefix in CORRELATION_CONFIG.items():
        total_metrics_data, _, _ = utils.read_experiments_by_prefix(file_prefix, False)
        
        x_val = total_metrics_data[CORRELATION_COLUMN_NAME].mean()*CORRELATION_COLUMN_SCALE
        y_val = total_metrics_data["total_energy_difference"].mean()
        
        x.append(x_val)
        y.append(y_val)

        plt.scatter(x_val, y_val, label=name, alpha=0.7, s=100)

    if len(x) > 1:        
        slope, intercept = np.polyfit(x, y, 1)
        
        x_line = np.linspace(min(x) * 0.9, max(x) * 1.1, 100)
        y_line = slope * x_line + intercept
        
        plt.plot(x_line, y_line, color='gray', linestyle='--', alpha=0.5, label=f"Linear Fit")

    plt.xlabel(f"Mean {CORRELATION_COLUMN_LABEL}")
    plt.ylabel("Mean Energy Consumption (J)") 
    
    plt.legend()
    plt.grid(True, linestyle='--', alpha=0.6)
    plt.tight_layout()

    file_name = f"{conf.PLOT_OUTPUT_FOLDER}/en_{CORRELATION_COLUMN_PREFIX}_mean_correlation_plot.pdf"
    plt.savefig(file_name, bbox_inches='tight')
    plt.close()
    print(f"Plot saved in {file_name}!")

def _generate_correlation_plot():
    print("> Generating correlation plot")
    
    plt.figure(figsize=(6, 5))
    
    if not CORRELATION_CONFIG:
        print("Warning: No JSON files found in the output folder.")
        return

    x = []
    y = []

    for name, file_prefix in CORRELATION_CONFIG.items():
        total_metrics_data, _, _ = utils.read_experiments_by_prefix(file_prefix, False)
        
        x_val = total_metrics_data[CORRELATION_COLUMN_NAME]*CORRELATION_COLUMN_SCALE
        y_val = total_metrics_data["total_energy_difference"]
        
        x.extend(x_val.tolist())
        y.extend(y_val.tolist())

        plt.scatter(x_val, y_val, label=name, alpha=0.7, s=30)

    x = np.array(x)
    y = np.array(y)

    if len(x) > 1:
        tau, p_value = kendalltau(x, y)
        
        slope, intercept = np.polyfit(x, y, 1)
        
        x_line = np.linspace(x.min(), x.max(), 100)
        y_line = slope * x_line + intercept
        
        plt.plot(x_line, y_line, color='gray', linestyle='--', alpha=0.5, label=f"Linear Fit (τ={tau:.2f})")

    plt.xlabel(CORRELATION_COLUMN_LABEL)
    plt.ylabel("Energy Consumption (J)") 
    
    plt.legend()
    plt.grid(True, linestyle='--', alpha=0.6)
    plt.tight_layout()

    file_name = f"{conf.PLOT_OUTPUT_FOLDER}/en_{CORRELATION_COLUMN_PREFIX}_correlation_plot.pdf"
    plt.savefig(file_name, bbox_inches='tight')
    plt.close()
    print(f"Plot saved in {file_name}!")

def _generate_correlation_matrix():
    print("> Generating correlation matrix heatmap")
    
    combined_frames = []

    for name, file_prefix in CORRELATION_CONFIG.items():
        total_metrics_data, _, _ = utils.read_experiments_by_prefix(file_prefix, False)
        
        if isinstance(total_metrics_data, pd.DataFrame) and not total_metrics_data.empty:
            df_copy = total_metrics_data.copy()
            df_copy['experiment_type'] = name 
            combined_frames.append(df_copy)

    if not combined_frames:
        return

    master_df = pd.concat(combined_frames, ignore_index=True)

    columns_to_include = [
        "total_carbon_emission_difference",
        "total_energy_difference",
        "execution_time"
    ]

    valid_columns = [col for col in columns_to_include if col in master_df.columns]

    filtered_df = master_df[valid_columns]

    corr_matrix = filtered_df.corr(method='kendall')
    corr_matrix = corr_matrix.iloc[::-1]

    plt.figure(figsize=(10, 10))

    # cmap_custom = sns.light_palette("seagreen", as_cmap=True)
    cmap_custom = sns.color_palette("vlag", as_cmap=True)
    
    sns.heatmap(
        corr_matrix, 
        annot=True,
        fmt=".2f",
        cmap=cmap_custom,
        vmin=-1, vmax=1,
        center=0,
        square=True,
        linewidths=0.5,      
        cbar_kws={"shrink": .8}
    )

    plt.tight_layout()

    file_name = f"{conf.PLOT_OUTPUT_FOLDER}/correlation_matrix.pdf"
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

def _resolve_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("-sid", "--sidecar", action='store_true')
    parser.add_argument("-acc", "--accuracies", action='store_true')
    parser.add_argument("-cor", "--correlation", action='store_true')

    args = parser.parse_args()
    plot_sidecar = args.sidecar
    plot_accuracies = args.accuracies
    plot_correlation = args.correlation

    return plot_sidecar, plot_accuracies, plot_correlation


if __name__ == '__main__':
    main()
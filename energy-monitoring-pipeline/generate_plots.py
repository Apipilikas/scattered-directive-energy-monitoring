import pandas as pd
import matplotlib.pyplot as plt
import configuration as conf
import json
import argparse

def main():
    plot_accuracies = _resolve_args()

    print(f"============= Generate plots =============")
    
    if plot_accuracies:
        _generate_accuracies_plot()
    else:
        _generate_sidecar_plot()

def _generate_sidecar_plot():
    print("> Generating sidecar plot")
    data = pd.read_csv("output/data_metrics.csv")

    time_seconds = data.index * 30  

    # Initialize the plot
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
    plt.title('Model accuracy per training round')
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
    parser.add_argument("-acc", "--accuracies", action='store_true')

    args = parser.parse_args()
    plot_accuracies = args.accuracies

    return plot_accuracies


if __name__ == '__main__':
    main()
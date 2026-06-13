import pandas as pd
import matplotlib.pyplot as plt
import configuration as conf

def main():
    print(f"============= Generate plots =============")
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

if __name__ == '__main__':
    main()
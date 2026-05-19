import argparse
import json
import configuration as conf
import pandas as pd
import statistics

def main():
    print(f"============= Average experiments =============")
    _calculate_statistics()

def _calculate_statistics():
    experiments_data = _read_experiments_file()

    values = {}
    experiment_files = []

    properties_to_calculate = [
        "total_idle_energy",
        "total_active_energy",
        "total_energy_difference"
    ]

    for run, data in experiments_data.items():
        for property_name in properties_to_calculate:
            values.setdefault(property_name, []).append(data[property_name])

        experiment_files.append(data["metrics_path"])

    output = {}

    for property_name in properties_to_calculate:
        mean_property_name = f"{property_name}_mean"
        std_property_name = f"{property_name}_std"

        output[mean_property_name] = statistics.mean(values[property_name])
        output[std_property_name] = statistics.stdev(values[property_name])

    metrics_mean_path, metrics_std_path = _calculate_metrics_statistics(experiment_files)

    output["metrics_mean_path"] = metrics_mean_path
    output["metrics_std_path"] = metrics_std_path

    with open(conf.AVERAGE_EXPERIMENTS_OUTPUT_PATH, 'w') as f:
        json.dump(output, f, indent=2)
    
    print(f"Saved final average experiments file to [{conf.AVERAGE_EXPERIMENTS_OUTPUT_PATH}]!")

def _calculate_metrics_statistics(experiment_files):
    metrics = _read_experiment_metrics(experiment_files)
    metrics = metrics.filter(like='_energy')

    metrics_mean = metrics.groupby(metrics.index).mean(numeric_only=True)
    metrics_std = metrics.groupby(metrics.index).std(numeric_only=True)

    metrics_mean_path = f"{conf.DATA_OUTPUT_FOLDER}/average_metrics_mean.csv"
    metrics_std_path = f"{conf.DATA_OUTPUT_FOLDER}/average_metrics_std.csv"

    metrics_mean.to_csv(metrics_mean_path, index=False)
    print(f"Saved metrics means file to [{metrics_mean_path}]!")
    metrics_std.to_csv(metrics_std_path, index=False)
    print(f"Saved metrics std file to [{metrics_mean_path}]!")

    return metrics_mean_path, metrics_std_path

def _align_experiments(dfs: list[pd.DataFrame]):
    min_length = min(len(df) for df in dfs)
    return [df.head(min_length) for df in dfs]

def _read_experiment_metrics(experiment_files: list[str]):
    dfs = [pd.read_csv(file) for file in experiment_files]
    dfs = _align_experiments(dfs)
    return pd.concat(dfs)

def _read_experiments_file():
    with open(conf.EXPERIMENTS_OUTPUT_PATH, 'r') as file:
        return json.load(file)

if __name__ == '__main__':
    main()
import pandas as pd
from sklearn.cluster import DBSCAN
import argparse
import utils
import os
import shutil
import configuration as conf

def execute_DBSCAN_AD_algorithm(df: pd.DataFrame):
    # Detect anomalies using DBSCAN
    column_to_use = 'total_energy_difference'
    X = df[[column_to_use]].values

    dbscan = DBSCAN(eps=30, min_samples=3)
    labels = dbscan.fit_predict(X)

    # Anomalies are labeled as -1
    anomalies = df[labels == -1]

    # Print anomalies
    print(f"Anomalies detected ({len(anomalies)} anomalies):")
    
    # Iterate directly through the filtered column strings
    for index, anomaly in anomalies.iterrows():
        # print(anomaly)
        dir = anomaly["dir"]
        run = anomaly["run"]
        print(f"File: {dir} | Run: {run}")

def check_runs_results(exp_dirs, anomaly_folders):
    # Check runs_results.csv for status codes not equal to 200
    for exp_dir_path, exp_rep_dir in exp_dirs:
        file_path = os.path.join(exp_dir_path, exp_rep_dir, 'runs_results.csv')
        if os.path.isfile(file_path):
            runs_df = pd.read_csv(file_path)
            anomalies = runs_df[(runs_df['appr_status_code'] != 200) | (runs_df['data_status_code'] != 200)]
            if not anomalies.empty:
                print(f"Anomalies in {file_path}:")
                print(anomalies)
                anomaly_folders.add(os.path.join(exp_dir_path, exp_rep_dir))
        else:
            print(f"File not found: {file_path}")

def remove_anomaly_folders(anomaly_folders):
    # Remove experiment folders found to be anomalies
    for folder in anomaly_folders:
        if os.path.exists(folder):
            shutil.rmtree(folder)
            print(f"Removed folder: {folder}")
        else:
            print(f"Folder not found: {folder}")

def _resolve_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("-ep", "--experiment-path")
    parser.add_argument("-pr", "--prefix")
    utils.add_boolean_argument(parser, conf.F_ARGUMENT)

    args = parser.parse_args()
    is_local = not args.fabric_mode
    prefix_arg = args.prefix

    if prefix_arg is None:
        output_path = utils.resolve_experiment_path(args.experiment_path, is_local)
        total_metrics_data, metrics_data, aggregated_metrics = utils.read_experiments_file(output_path)
        return _inject_dir_to_df(total_metrics_data, output_path)
    
    total_metrics_dfs = []
    filtered_dirs = utils.get_experiments_directories_by_prefix(prefix_arg, is_local)

    for dir in filtered_dirs:
        exp_path = utils.resolve_experiment_path(dir, is_local=is_local, raise_ex=False)
        total_metrics_data, metrics_data, aggregated_metrics = utils.read_experiments_file(exp_path)
        total_metrics_dfs.append(_inject_dir_to_df(total_metrics_data, exp_path))

    return pd.concat(total_metrics_dfs)

def _inject_dir_to_df(df: pd.DataFrame, dir: str):
    df["Dir"] = dir
    return df

def main():
    total_metrics_data = _resolve_args()
    execute_DBSCAN_AD_algorithm(total_metrics_data)

if __name__ == "__main__":
    main()
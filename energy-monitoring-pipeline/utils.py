import time
import json
import argparse
import configuration as conf
import pandas as pd
import os
from collections import defaultdict

def get_time_range(minutes_before: int) -> tuple[float, float]:

    end_time = time.time()
    start_time = end_time - (minutes_before * 60)

    return start_time, end_time

def _align_experiments(dfs: list[pd.DataFrame]):
    min_length = min(len(df) for df in dfs)
    return [df.head(min_length) for df in dfs]

def is_experiment_run_valid(output: dict):
    return output["request_approval_status_code"] == 202 and output["accuracies"] != {}

def read_experiments_by_prefix(prefix: str, is_local = True) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    filtered_dirs = get_experiments_directories_by_prefix(prefix, is_local)

    if not filtered_dirs:
        print(f"No experiment directories found starting with prefix: '{prefix}'")
        return pd.DataFrame(), pd.DataFrame(), {}

    total_metrics_dfs = []
    metrics_dfs = []

    combined_flat_metrics = defaultdict(list)
    combined_nested_metrics = defaultdict(lambda: defaultdict(list))

    for dir in filtered_dirs:
        exp_path = resolve_experiment_path(dir, is_local, False)
        
        if not exp_path:
            continue

        total_metrics_df, metrics_df, aggregated_metrics = read_experiments_file(exp_path)
        
        total_metrics_dfs.append(total_metrics_df)
        metrics_dfs.append(metrics_df)

        for key, value in aggregated_metrics.items():
            if isinstance(value, dict):
                for component, val_list in value.items():
                    combined_nested_metrics[key][component].extend(val_list)
            else:
                combined_flat_metrics[key].extend(value)

    final_aggregated_metrics = {
        **{k: dict(v) for k, v in combined_nested_metrics.items()}, 
        **dict(combined_flat_metrics)
    }

    final_total_metrics_df = pd.concat(total_metrics_dfs)
    final_metrics_df = pd.concat(metrics_dfs)

    return final_total_metrics_df, final_metrics_df, final_aggregated_metrics

def load_experiments_file(file_path = conf.EXPERIMENT_OUTPUT_FOLDER):
    with open(f"{file_path}/{conf.EXPERIMENTS_OUTPUT_FILE_NAME}", 'r') as file:
        experiments_data = json.load(file)

    return experiments_data

def read_experiments_file(file_path = conf.EXPERIMENT_OUTPUT_FOLDER) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    experiments_data = load_experiments_file(file_path)

    total_metrics_dfs = []
    metrics_dfs = []

    flat_metrics = defaultdict(list)
    nested_metrics = defaultdict(lambda: defaultdict(list))

    ignore_properties = ["accuracies", "total_metrics_path", "metrics_path"]

    for run, data in experiments_data.items():
        if not is_experiment_run_valid(data):
            continue

        df = pd.read_csv(data["total_metrics_path"])
        df["run"] = run
        df["execution_time"] = pd.to_timedelta(data["active_elapsed_time"]).total_seconds()
        total_metrics_dfs.append(df)
        metrics_dfs.append(pd.read_csv(data["metrics_path"]))

        for key, value in data.items():
            if key in ignore_properties:
                continue

            if isinstance(value, dict):
                for component, v in value.items():
                    nested_metrics[key][component].append(float(v))
            else:
                flat_metrics[key].append(value)

    aggregated_metrics = {**{k: dict(v) for k, v in nested_metrics.items()}, **dict(flat_metrics)}

    if len(total_metrics_dfs) == 0:
        return None, None, aggregated_metrics
    
    return pd.concat(total_metrics_dfs), pd.concat(_align_experiments(metrics_dfs)), aggregated_metrics

def resolve_experiment_path(path, is_local = True, raise_ex = True) -> str:
    output_path = f"{conf.EXPERIMENT_OUTPUT_FOLDER}/{get_experiment_mode_folder(is_local)}/{path}"

    if os.path.exists(output_path):
        return output_path
    else:
        if raise_ex:
            raise Exception(f"File path {output_path} does not exist in {conf.EXPERIMENT_OUTPUT_FOLDER} folder.")
        else:
            return None

def get_experiments_directories(is_local = True):
    return os.listdir(f"{conf.EXPERIMENT_OUTPUT_FOLDER}/{get_experiment_mode_folder(is_local)}")

def get_experiments_directories_by_prefix(prefix: str, is_local = True):
    all_dirs = get_experiments_directories(is_local=is_local)
    return [d for d in all_dirs if d.startswith(prefix)]

def get_experiment_mode_folder(is_local = True):
    return "local" if is_local else "fabric"

def interpret_guilford_scale(correlation: float) -> str:
    """
    Interpret a correlation value using the standard Guilford scale.
    Handles both positive and negative correlations symmetrically.

    :param correlation: Correlation coefficient (range: -1.0 to 1.0)
    :return: Interpretation string (e.g., "High positive correlation")
    """
    abs_corr = abs(correlation)

    if abs_corr < 0.2:
        strength = "Slight"
    elif abs_corr < 0.4:
        strength = "Low"
    elif abs_corr < 0.7:
        strength = "Moderate"
    elif abs_corr < 0.9:
        strength = "High"
    else:
        strength = "Very high"

    direction = "positive" if correlation > 0 else "negative" if correlation < 0 else "neutral"
    return f"{strength} {direction} correlation"

def add_boolean_argument(parser: argparse.ArgumentParser, arg_tuple: tuple[str, str, str]):
    arg_flag = arg_tuple[0]
    arg_name = arg_tuple[1]
    help = arg_tuple[2]
    parser.add_argument(
        arg_flag, arg_name, action='store_true', help=help
        )
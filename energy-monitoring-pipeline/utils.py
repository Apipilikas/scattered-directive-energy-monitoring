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

def read_experiments_file(file_path = conf.EXPERIMENT_OUTPUT_FOLDER) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    with open(f"{file_path}/{conf.EXPERIMENTS_OUTPUT_FILE_NAME}", 'r') as file:
        experiments_data = json.load(file)

    total_metrics_dfs = []
    metrics_dfs = []

    flat_metrics = defaultdict(list)
    nested_metrics = defaultdict(lambda: defaultdict(list))

    ignore_properties = ["accuracies", "total_metrics_path", "metrics_path"]

    for run, data in experiments_data.items():
        total_metrics_dfs.append(pd.read_csv(data["total_metrics_path"]))
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

def get_experiment_mode_folder(is_local = True):
    return "local" if is_local else "fabric"

def add_boolean_argument(parser: argparse.ArgumentParser, arg_tuple: tuple[str, str, str]):
    arg_flag = arg_tuple[0]
    arg_name = arg_tuple[1]
    help = arg_tuple[2]
    parser.add_argument(
        arg_flag, arg_name, action='store_true', help=help
        )
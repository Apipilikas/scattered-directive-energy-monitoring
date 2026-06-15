import time
import json
import argparse
import configuration as conf
import pandas as pd
import os

def get_time_range(minutes_before: int) -> tuple[float, float]:

    end_time = time.time()
    start_time = end_time - (minutes_before * 60)

    return start_time, end_time

def _align_experiments(dfs: list[pd.DataFrame]):
    min_length = min(len(df) for df in dfs)
    return [df.head(min_length) for df in dfs]

def read_experiments_file(file_path = conf.EXPERIMENT_OUTPUT_FOLDER) -> tuple[pd.DataFrame, pd.DataFrame]:
    with open(f"{file_path}/{conf.EXPERIMENTS_OUTPUT_FILE_NAME}", 'r') as file:
        experiments_data = json.load(file)

    total_metrics_dfs = []
    metrics_dfs = []

    for run, data in experiments_data.items():
        total_metrics_dfs.append(pd.read_csv(data["total_metrics_path"]))
        metrics_dfs.append(pd.read_csv(data["metrics_path"]))
   
    return pd.concat(total_metrics_dfs), pd.concat(_align_experiments(metrics_dfs))

def resolve_experiment_path(output_prefix, is_local = True, raise_ex = True) -> str:
    output_path = f"{conf.EXPERIMENT_OUTPUT_FOLDER}/{get_experiment_mode_folder(is_local)}/{output_prefix}"

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
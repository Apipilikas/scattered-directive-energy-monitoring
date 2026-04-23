from configuration import COLLECT_MINUTES_BEFORE, PROM_QUERIES, DATA_COLLECT_OUTPUT_PATH
from utils import get_time_range
from prometheus_executor import execute_query_range
import csv
import pandas as pd

def main():
    print("============= Metrics collection started =============")
    start_time, end_time = get_time_range(COLLECT_MINUTES_BEFORE)
    print(f"Start time: {start_time}, End time: {end_time}")

    return _collect_metrics(start_time, end_time)

def _collect_metrics(start_time: float, end_time: float):
    metrics = {}
    
    for name, query in PROM_QUERIES.items():
        metrics[name] = execute_query_range(query, start_time, end_time)
    
    _export_metrics(metrics)

def _export_metrics(metrics: dict):
    dataframes = []

    for query_name, containers in metrics.items():

        for container, metric_values in containers.items():
            column_name = f"{container}_{query_name}"
            df = pd.DataFrame(metric_values, columns=["timestamp", column_name])
            
            # Convert timestamps to actual datetime
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit='s')
            df.set_index("timestamp", inplace=True)
            
            # Convert to float
            df[column_name] = df[column_name].astype(float)

            dataframes.append(df)

    return _save_file_to_csv(dataframes)

def _save_file_to_csv(dataframes: list[pd.DataFrame]):
    if dataframes:
        final_df = pd.concat(dataframes, axis=1, sort=False)
        
        final_df.sort_index(inplace=True)
        final_df.fillna(0.0, inplace=True)

        final_df.to_csv(DATA_COLLECT_OUTPUT_PATH)
        print(f"Saved file to [{DATA_COLLECT_OUTPUT_PATH}]!")
    else:
        print("No data exported!")

if __name__ == '__main__':
    main()
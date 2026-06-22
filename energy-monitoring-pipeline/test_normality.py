import pandas as pd
import configuration as conf
import argparse
from scipy.stats import shapiro
import utils

def test_normality(df: pd.DataFrame):
    # Perform Shapiro-Wilk normality test
    columns_to_test = ['total_energy_difference']
    # columns_to_test = ['total_energy_difference', 'average_exec_time']
    not_normal = {col: 0 for col in columns_to_test}
    normal = {col: 0 for col in columns_to_test}

    # Test normality for each column
    for column in columns_to_test:
        data = df[column].values
        print(f"Data: {data}")
        # Ensure data used is at least 3 values
        if len(data) >= 3:
            stat, p = shapiro(data)
            # Use threshold to determine if the p-value is considered not normal distribution
            if p < 0.01:
                not_normal[column] += 1
                print(f"Not normal distribution for column: {column}")
            else:
                normal[column] += 1
            # Print stastic and p-value
            print(f"Statistic (Shapiro-Wilk test): {stat}, p-value: {p}")
        else:
            print(f"Not enough data points for normality test in column: {column}")

def _resolve_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("-ep", "--experiment-path")
    utils.add_boolean_argument(parser, conf.F_ARGUMENT)

    args = parser.parse_args()
    is_local = not args.fabric_mode

    return utils.resolve_experiment_path(args.experiment_path, is_local)


def main():
    output_path = _resolve_args()

    print(f"============= Test normality =============")

    # Load the data
    total_metrics_data, metrics_data, aggregated_metrics = utils.read_experiments_file(output_path)

    if total_metrics_data is None:
        print("No data loaded. Exiting.")
    else:
        # Perform normality test
        test_normality(total_metrics_data)

if __name__ == "__main__":
    main()
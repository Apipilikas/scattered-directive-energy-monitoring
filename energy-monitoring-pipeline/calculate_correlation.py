import pandas as pd
import os
import argparse
from scipy.stats import kendalltau
import utils
import configuration as conf

def test_kendall_tau(df: pd.DataFrame):
    """
    Perform Kendall Tau correlation test for statistical significance.
    """
    # Extracting data
    columns_to_compare = ['execution_time', 'total_carbon_emission_difference']

    baseline_column_name = 'total_energy_difference'

    energy_data = df[baseline_column_name]

    for column_name in columns_to_compare:
        comparetive_data = df[column_name]
        if len(df) >= 3:
            tau, p_value = kendalltau(energy_data, comparetive_data)

            # Interpret correlation strength using helper function for the scale
            strength = utils.interpret_guilford_scale(tau)

            print(f"\nKendall Tau Correlation for columns '{baseline_column_name}' VS '{column_name}':")
            print(f"    Tau Coefficient: {tau}")
            print(f"    p-value: {p_value} {'(Significant)' if p_value < 0.05 else '(Not Significant)'}")
            print(f"    Strength: {strength}")
        else:
            print(f"\nNot enough data points for Kendall Tau correlation test.")

def _resolve_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("-pr", "--prefix")
    parser.add_argument("-all", "--all", action="store_true")
    parser.add_argument("-m", "--mean", action="store_true")
    utils.add_boolean_argument(parser, conf.F_ARGUMENT)
    utils.add_boolean_argument(parser, conf.BE_ARGUMENT)

    args = parser.parse_args()
    is_local = not args.fabric_mode
    prefix_arg = args.prefix
    all_arg = args.all
    both_environments_arg = args.both_environments
    mean_arg = args.mean

    total_metrics_data = []

    if all_arg:
        prefixes_to_run = conf.PREFIXES
    else:
        prefixes_to_run = [prefix_arg]

    for prefix in prefixes_to_run:
        local_data, _, _ = utils.read_experiments_by_prefix(prefix, is_local)
        
        if mean_arg:
            local_row = local_data[["total_energy_difference", "execution_time", "total_carbon_emission_difference"]].mean().to_frame().T
            total_metrics_data.append(local_row)
        else:
            total_metrics_data.append(local_data)

        if both_environments_arg and all_arg:
            dist_data, _, _ = utils.read_experiments_by_prefix(prefix, not is_local)
            
            if mean_arg:
                dist_row = dist_data[["total_energy_difference", "execution_time", "total_carbon_emission_difference"]].mean().to_frame().T
                total_metrics_data.append(dist_row)
            else:
                total_metrics_data.append(dist_data)
    
    return pd.concat(total_metrics_data)

def main():
    total_metrics_data = _resolve_args()
    test_kendall_tau(total_metrics_data)

if __name__ == "__main__":
    main()
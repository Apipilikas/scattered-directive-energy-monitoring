import pandas as pd
import os
import argparse
from scipy.stats import kendalltau
import utils
import configuration as conf

def test_kendall_tau(df: pd.DataFrame, archetype: str):
    """
    Perform Kendall Tau correlation test for statistical significance.
    """
    # Extracting data
    energy_data = df['total_energy_difference']
    exec_time_data = df['average_exec_time']

    if len(df) >= 3:
        tau, p_value = kendalltau(energy_data, exec_time_data)

        # Interpret correlation strength using helper function for the scale
        strength = utils.interpret_guilford_scale(tau)

        print(f"\nKendall Tau Correlation for {archetype}:")
        print(f"    Tau Coefficient: {tau}")
        print(f"    p-value: {p_value} {'(Significant)' if p_value < 0.05 else '(Not Significant)'}")
        print(f"    Strength: {strength}")
    else:
        print(f"\nNot enough data points for Kendall Tau correlation test.")

def _resolve_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("-bpr", "--baseline-prefix")
    parser.add_argument("-mpr", "--mitigation-prefix")
    utils.add_boolean_argument(parser, conf.F_ARGUMENT)

    args = parser.parse_args()
    is_local = not args.fabric_mode
    baseline_prefix_arg = args.baseline_prefix
    mitigation_prefix_arg = args.mitigation_prefix

    baseline_data = utils.read_experiments_by_prefix(baseline_prefix_arg, is_local)
    mitigation_data = utils.read_experiments_by_prefix(mitigation_prefix_arg, is_local)

    return baseline_data, mitigation_data, mitigation_prefix_arg

def main():
    baseline_data, mitigation_data, mitigation_prefix = _resolve_args()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Kendall Tau correlation test on energy efficiency experiment data")
    parser.add_argument("archetype", type=str, choices=["ComputeToData", "DataThroughTTP", "all"], 
                        help="Archetype to test correlation from.")
    parser.add_argument("--data_type", type=str, choices=["normal", "fabric"], default="normal", 
                        help="Data type to use, i.e., the data folder to use for this analysis. Defaults to 'normal'.")
    args = parser.parse_args()

    # If all is selected, use all archetypes
    archetypes = constants.ARCHETYPES if args.archetype == "all" else [args.archetype]

    # List to hold all DataFrames
    all_dfs = []
    # Load the data for each prefix and archetype
    for archetype in archetypes:
        for prefix in constants.IMPLEMENTATIONS_PREFIXES:
            # Load the data (will load all experiments folders and its data with the prefix)
            df, exp_dirs = utils.load_experiment_results(prefix, archetype, args.data_type)
            # If data is not empty, add it to the list
            if not df.empty:
                # Append the df
                all_dfs.append(df)
            else:
                print(f"No data loaded for prefix: {prefix} and archetype: {archetype}")

    # Combine all DataFrames into one
    if all_dfs:
        combined_df = pd.concat(all_dfs, ignore_index=True)
        # Logging purposes
        # print(f"Combined df: {combined_df}")
        # print(f"Length of df: {len(combined_df)}")
        # Perform Kendall Tau correlation test on the combined DataFrame
        test_kendall_tau(combined_df, args.archetype)
    else:
        print("No data loaded for any prefix or archetype.")
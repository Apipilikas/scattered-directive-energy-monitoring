import pandas as pd
import os
import argparse
from scipy.stats import mannwhitneyu
import utils
import constants

def calculate_rank_biserial(u_stat, n1, n2):
    """
    Compute Rank Biserial Correlation from Mann-Whitney U test results.
    :param u_stat: U-statistic from Mann-Whitney test
    :param n1: Sample size of first group (Baseline)
    :param n2: Sample size of second group (Optimization)
    :return: Rank Biserial Correlation coefficient
    """
    return 1 - (2 * u_stat) / (n1 * n2)

def test_statistical_significance(df_baseline: pd.DataFrame, df_opt: pd.DataFrame, archetype: str, optimization: str):
    """
    Perform Mann-Whitney U test for statistical significance and compute Rank Biserial Correlation as effect size.
    """
    columns_to_test = ['total_energy_difference', 'average_exec_time']

    # Logging purposes
    # print(f"Using baseline df of {archetype}: {df_baseline}")
    # print(f"Using {optimization} df of {archetype}: {df_opt}")

    # Perform calculations for each column
    for column in columns_to_test:
        # Ensure both groups have enough data points
        if len(df_baseline) >= 3 and len(df_opt) >= 3:
            # Calculate values using Mann Whitney U test for statistical significance
            # Use optimization as the first one, as we want to know the difference it has on the baseline
            # Use two-sided MWU test
            u_stat, p_value = mannwhitneyu(df_opt[column], df_baseline[column], alternative='two-sided')

            # Compute Rank Biserial Correlation for effect size
            rbc = calculate_rank_biserial(u_stat, len(df_baseline), len(df_opt))
            # Interpret correlation strength using helper function for the scale
            strength = utils.interpret_guilford_scale(rbc)

            # Print results for this optimization
            print(f"\nComparison: {optimization} vs. baseline and {archetype} for {column}")
            print(f"    Mann-Whitney U Statistic: {u_stat}")
            print(f"    p-value: {p_value} {'(Significant)' if p_value < 0.05 else '(Not Significant)'}")
            print(f"    Rank Biserial Correlation (Effect Size): {rbc}")
            print(f"    Strength: {strength}")
        else:
            print(f"\nNot enough data for Mann-Whitney U test for {optimization} and {archetype} on {column}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run statistical significance test on energy efficiency experiment data")
    parser.add_argument("archetype", type=str, choices=["ComputeToData", "DataThroughTTP", "all"], 
                        help="Archetype to test statistical significance from.")
    parser.add_argument("--data_type", type=str, choices=["normal", "fabric"], default="normal", 
                        help="Data type to use, i.e., the data folder to use for this analysis. Defaults to 'normal'.")
    args = parser.parse_args()

    # If all is selected, use all archetypes
    archetypes = constants.ARCHETYPES if args.archetype == "all" else [args.archetype]
    
    # Load baseline data separately for each archetype
    baseline_data_dict = {}
    for archetype in archetypes:
        # Load the data (will load all experiments folders and its data with the prefix)
        df, exp_dirs = utils.load_experiment_results("baseline", archetype, args.data_type)
        if not df.empty:
            # Add the baseline df for this archetype
            baseline_data_dict[archetype] = df
        else:
            print(f"No data loaded for prefix: baseline and archetype: {archetype}")

    # Load the data for each prefix and archetype (do archetype as the parent loop 
    # to ensure implementations are shown next to each other)
    for archetype in archetypes:
        # Loop over optimizations only (excluding baseline)
        for prefix in constants.OPTIMIZATIONS_PREFIXES:
            # Load the data (will load all experiments folders and its data with the prefix)
            df, exp_dirs = utils.load_experiment_results(prefix, archetype, args.data_type)
            # If data is not empty, perform statistical significance test
            if not df.empty:
                print(f"\n***************************************************************************")
                print(f"Implementation: {prefix}\nArchetype: {archetype}")
                # Calculate statistics using the baseline df of the corresponding archetype
                test_statistical_significance(baseline_data_dict[archetype], df, archetype, prefix)
                print(f"\n***************************************************************************")
            else:
                print(f"No data loaded for prefix: {prefix} and archetype: {archetype}")
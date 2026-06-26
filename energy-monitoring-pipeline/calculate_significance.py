import pandas as pd
import os
import argparse
from scipy.stats import mannwhitneyu
import utils
import configuration as conf

def calculate_rank_biserial(u_stat, n1, n2):
    """
    Compute Rank Biserial Correlation from Mann-Whitney U test results.
    :param u_stat: U-statistic from Mann-Whitney test
    :param n1: Sample size of first group (Baseline)
    :param n2: Sample size of second group (Optimization)
    :return: Rank Biserial Correlation coefficient
    """
    return 1 - (2 * u_stat) / (n1 * n2)

def test_statistical_significance(df_baseline: pd.DataFrame, df_opt: pd.DataFrame, optimization: str):
    """
    Perform Mann-Whitney U test for statistical significance and compute Rank Biserial Correlation as effect size.
    """
    columns_to_test = ['total_energy_difference', 'total_carbon_emission_difference']

    for column in columns_to_test:
        if len(df_baseline) >= 3 and len(df_opt) >= 3:
            u_stat, p_value = mannwhitneyu(df_opt[column], df_baseline[column], alternative='two-sided')

            rbc = calculate_rank_biserial(u_stat, len(df_baseline), len(df_opt))
            strength = utils.interpret_guilford_scale(rbc)

            print(f"\nComparison: {optimization} vs. baseline for {column}")
            print(f"    Mann-Whitney U Statistic: {u_stat}")
            print(f"    p-value: {p_value} {'(Significant)' if p_value < 0.05 else '(Not Significant)'}")
            print(f"    Rank Biserial Correlation (Effect Size): {rbc}")
            print(f"    Strength: {strength}")
        else:
            print(f"\nNot enough data for Mann-Whitney U test for {optimization} on {column}")

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
    test_statistical_significance(baseline_data[0], mitigation_data[0], mitigation_prefix)

if __name__ == "__main__":
    main()
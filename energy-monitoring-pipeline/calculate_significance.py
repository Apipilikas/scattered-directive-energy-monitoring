import pandas as pd
import argparse
from scipy.stats import mannwhitneyu
import utils
import configuration as conf

METRICS_SCALES = {
    'total_energy_difference': 1,
    'total_carbon_emission_difference': 1000,
    'execution_time': 1
}

METRICS_LABELS = {
    'total_energy_difference': r"Energy",
    'total_carbon_emission_difference': r"\makecell{Carbon \\ Emission}",
    'execution_time': r"\makecell{Execution \\ Time}"
}

METRICS = {
    'total_energy_difference': "J",
    'total_carbon_emission_difference': "g CO2e/kWh",
    'execution_time': "s"
}

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
    columns_to_test = ['total_energy_difference', 'total_carbon_emission_difference', 'execution_time']

    output = {}

    for column in columns_to_test:
        if len(df_baseline) >= 3 and len(df_opt) >= 3:
            u_stat, p_value = mannwhitneyu(df_opt[column], df_baseline[column], alternative='two-sided')

            rbc = calculate_rank_biserial(u_stat, len(df_baseline), len(df_opt))
            strength = utils.interpret_guilford_scale(rbc)

            baseline_mean = df_baseline[column].mean()
            opt_mean = df_opt[column].mean()

            mean_difference = opt_mean - baseline_mean
            mean_difference_perc = (mean_difference)/baseline_mean*100

            print(f"\nComparison: {optimization} vs. baseline for {column}")
            print(f"    Mann-Whitney U Statistic: {u_stat}")
            print(f"    Mean difference: {mean_difference}")
            print(f"    Mean difference (%): {mean_difference_perc}")
            print(f"    p-value: {p_value} {'(Significant)' if p_value < 0.05 else '(Not Significant)'}")
            print(f"    Rank Biserial Correlation (Effect Size): {rbc}")
            print(f"    Strength: {strength}\n")

            strength_words = strength.replace(r'\\', ' ').split()[:-1]
            strength_latex = r" \\ ".join([word.capitalize() for word in strength_words])

            output[column] = {
                "mean_difference": _to_latex_scientific(mean_difference * METRICS_SCALES[column]),
                "mean_difference_perc": f"{mean_difference_perc:.3f}",
                "p_value": _to_latex_scientific(p_value),
                "significance": p_value < 0.05,
                "rbc": _to_latex_scientific(rbc),
                "strength": strength_latex
            }
        else:
            print(f"\nNot enough data for Mann-Whitney U test for {optimization} on {column}")

    _print_latex_table(output)

    return output

def _print_latex_table(results: dict):
    print("> Printing LaTeX table: \n")
    print(r"\begin{table}[!htbp]")
    print(r"    \centering")
    print(r"    \makebox[\textwidth][c]{")
    print(r"    \begin{tabular}{ccccccc}")
    print(r"        \toprule")
    print(r"        \textbf{Metric} & \textbf{\makecell{Mean \\ Difference}} & \textbf{\makecell{Mean \\ Difference (\%)}} & \textbf{\makecell{MWU \\ (p-value)}} & \textbf{Significant} & \textbf{RBC} & \textbf{Strength} \\")
    print(r"        \midrule")
    
    first = True

    for name, result in results.items():
        sig_str = 'Yes' if result['significance'] else 'No'
        if not first: 
            print(r"        \addlinespace")

        first = False
        print(rf"        \textbf{{{METRICS_LABELS[name]}}} & ${result['mean_difference']}$${METRICS[name]}$ & {result['mean_difference_perc']}\% & ${result['p_value']}$ & {sig_str} & {result['rbc']} & \makecell{{{result['strength']}}} \\")
    
    print(r"        \bottomrule")
    print(r"    \end{tabular}")
    print(r"    }")
    print(r"    \caption{CAPTION}")
    print(r"    \label{tab:LABEL}")
    print(r"\end{table}")

def _to_latex_scientific(value, decimals=3):
    if pd.isna(value) or value == 0:
        return "0"
    
    abs_val = abs(value)
    if 0.001 <= abs_val < 1000:
        return f"{value:.{decimals}f}"
    
    sci_str = f"{value:.{decimals}e}"
    mantissa, exponent = sci_str.split('e')
    
    exponent = int(exponent)
    
    if exponent == 0:
        return f"{mantissa}"
        
    return rf"{mantissa} \times 10^{{{exponent}}}"

def _print_grouped_latex_table(data: list):
    print("\n> Printing LaTeX grouped table: \n")
    print(r"\begin{table}[!htbp]")
    print(r"    \centering")
    print(r"    \makebox[\textwidth][c]{")
    print(r"    \begin{tabular}{c|ccccccc}")
    print(r"        \toprule")
    print(r"        & \textbf{Metric} & \textbf{\makecell{Mean \\ Difference}} & \textbf{\makecell{Mean \\ Difference (\%)}} & \textbf{\makecell{MWU \\ (p-value)}} & \textbf{Significant} & \textbf{RBC} & \textbf{Strength} \\")
    print(r"        \midrule")

    i = 0
    
    for results in data:
        num_data_rows = len(results)
        
        multirow_span = num_data_rows + (num_data_rows - 1)
        
        j = 0

        for name, result in results.items():
            sig_str = 'Yes' if result['significance'] else 'No'
            if j == 0:
                env = result["environment"]
                env_column = rf"\multirow{{{multirow_span}}}{{*}}{{\rotatebox[origin=c]{{90}}{{\textbf{{{env}}}}}}} &"
            else:
                env_column = "&"

            print(rf"        {env_column}")
            print(rf"        \textbf{{{METRICS_LABELS[name]}}} & ${result['mean_difference']}$${METRICS[name]}$ & {result['mean_difference_perc']}\% & ${result['p_value']}$ & {sig_str} & {result['rbc']} & \makecell{{{result['strength']}}} \\")

            if j < num_data_rows - 1:
                print(r"        \addlinespace")

            j += 1

        if i < len(data) - 1:
            print(r"        \midrule")

        i += 1
        

    print(r"        \bottomrule")
    print(r"    \end{tabular}")
    print(r"    }")
    print(r"    \caption{CAPTION}")
    print(r"    \label{tab:TABLE}")
    print(r"\end{table}")

def _resolve_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("-bpr", "--baseline-prefix")
    parser.add_argument("-mpr", "--mitigation-prefix")
    parser.add_argument("-all", "--all", action='store_true')
    parser.add_argument("-bth", "--both", action='store_true')
    utils.add_boolean_argument(parser, conf.F_ARGUMENT)

    args = parser.parse_args()
    is_local = not args.fabric_mode
    baseline_prefix_arg = args.baseline_prefix
    mitigation_prefix_arg = args.mitigation_prefix
    all_arg = args.all
    both_arg = args.both

    return baseline_prefix_arg, mitigation_prefix_arg, is_local, all_arg, both_arg

def _read_experiments(baseline_prefix, mitigation_prefix, is_local, all):
    baseline_data, _, _ = utils.read_experiments_by_prefix(baseline_prefix, is_local)
    mitigation_data, _, _ = utils.read_experiments_by_prefix(mitigation_prefix, is_local)

    if all:
        b_data, _, _ =  utils.read_experiments_by_prefix(baseline_prefix, not is_local)
        m_data, _, _ =  utils.read_experiments_by_prefix(mitigation_prefix, not is_local)
        baseline_data = pd.concat([baseline_data, b_data])
        mitigation_data = pd.concat([mitigation_data, m_data])


    return baseline_data, mitigation_data

def _resolve_group_label(is_local):
    return "Local" if is_local else "FABRIC"

def main():
    baseline_prefix, mitigation_prefix, is_local, all, both = _resolve_args()

    environments = [is_local]

    results = []

    if both:
        environments.append(not is_local)


    for env in environments:
        baseline_data, mitigation_data = _read_experiments(baseline_prefix, mitigation_prefix, env, all)
        result = test_statistical_significance(baseline_data, mitigation_data, mitigation_prefix)
        for i, data in result.items():
            data["environment"] = _resolve_group_label(env)
        results.append(result)

    if both:
        _print_grouped_latex_table(results)
        

if __name__ == "__main__":
    main()
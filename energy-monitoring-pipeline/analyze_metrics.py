from sklearn import ensemble as skl
import argparse
import pandas as pd
import configuration as conf
from utils import add_boolean_argument
from pyrca.analyzers.rcd import RCD
import csv

def main():
    run_ad, run_rca = _resolve_args()
    
    execute_analysis(run_ad, run_rca)
    
    return

def execute_analysis(run_ad: bool, run_rca: bool):
    if run_ad or run_rca:
        print("============= Metrics analysis started =============")

    if run_ad:
        print("Anomaly detection started...")
        _detect_anomalies()
    
    if run_rca:
        print("Root cause analysis started...")
        _analyze_root_causes()

def _resolve_args():
    run_ad = False
    run_rca = False

    parser = argparse.ArgumentParser()
    
    add_boolean_argument(parser, conf.AD_ARGUMENT)
    add_boolean_argument(parser, conf.RCA_ARGUMENT)

    args = parser.parse_args()
    ad_arg = args.anomaly_detection
    rca_arg = args.root_cause_analysis

    if not (ad_arg or rca_arg):
        run_ad = True
        run_rca = True
    else:
        run_ad = ad_arg
        run_rca = rca_arg

    return run_ad, run_rca

def _convert_cpu_usage_to_percentage(df: pd.DataFrame):
    cpu_columns = [col for col in df.columns if '_cpu' in col]
    df[cpu_columns] = df[cpu_columns] * 100
    return df

# Anomaly detection (AD)
def _detect_anomalies():
    df = pd.read_csv(conf.DATA_COLLECT_OUTPUT_PATH)

    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df.set_index("timestamp", inplace=True)

    df = _convert_cpu_usage_to_percentage(df)

    for column_name in df.columns:
        # Skip timestamp column
        if column_name == "timestamp":
            continue
        else:
            df_column = df[[column_name]]

            model = skl.IsolationForest()

            anomaly_column_name = f"{column_name}_anomaly"
            df[anomaly_column_name] = model.fit_predict(df_column)

            anomaly_score_column_name = f"{column_name}_anomaly_score"
            df[anomaly_score_column_name] = model.decision_function(df_column)

    df.to_csv(conf.DATA_DA_OUTPUT_PATH)
    print(f"Saved file to [{conf.DATA_DA_OUTPUT_PATH}]!")

# Root cause analysis (RCA)
def _analyze_root_causes():
    model = RCD(config=RCD.config_class(
        start_alpha=0.05,
        k= conf.RCD_K,
        bins=5,
        gamma=5,
        localized=True
    ))

    train_df = pd.read_csv(conf.TRAINING_DATA_PATH)
    if "timestamp" in train_df.columns:
        train_df.drop(columns = conf.COLUMN_TO_DROP, inplace=True)
    train_df = train_df.filter(like='_energy')
    
    test_df = pd.read_csv(conf.DATA_COLLECT_OUTPUT_PATH)
    if "timestamp" in test_df.columns:
        test_df.drop(columns = conf.COLUMN_TO_DROP, inplace=True)
    test_df = test_df.filter(like='_energy')
    
    results = model.find_root_causes(train_df, test_df)
    print_results(results.to_dict())

def print_results(results):   
    # Extracting node names
    nodes_list = [node[0] for node in results['root_cause_nodes']]

    with open(conf.DATA_RCA_OUTPUT_PATH, mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(['Root Cause'])
        writer.writerows([[node] for node in nodes_list])
        print(f"Saved file to [{conf.DATA_RCA_OUTPUT_PATH}]!")

if __name__ == '__main__':
    main()
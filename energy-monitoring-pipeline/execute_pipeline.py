from collect_metrics import main as collect_metrics
from analyze_metrics import execute_analysis
import argparse
from configuration import AD_ARGUMENT, RCA_ARGUMENT, CM_ARGUMENT
from utils import add_boolean_argument

def main():
    run_cm, run_ad, run_rca = _resolve_args()

    if run_cm:
        collect_metrics()
    
    execute_analysis(run_ad, run_rca)

    return

def _resolve_args():
    run_cm = False
    run_ad = False
    run_rca = False

    parser = argparse.ArgumentParser()
    
    add_boolean_argument(parser, CM_ARGUMENT)
    add_boolean_argument(parser, AD_ARGUMENT)
    add_boolean_argument(parser, RCA_ARGUMENT)

    args = parser.parse_args()
    cm_arg = args.collect_metrics
    ad_arg = args.anomaly_detection
    rca_arg = args.root_cause_analysis

    if not (cm_arg or ad_arg or rca_arg):
        run_cm = True
        run_ad = True
        run_rca = True
    else:
        run_cm = cm_arg
        run_ad = ad_arg
        run_rca = rca_arg

    return run_cm, run_ad, run_rca

if __name__ == '__main__':
    main()
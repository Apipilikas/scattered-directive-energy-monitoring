import utils
import argparse
import configuration as conf

def main():
    prefix, is_local = _resolve_args()

    print(f"============= Test valid results =============")
    _test_validity(prefix, is_local)

def _test_validity(prefix, is_local = True):
    dirs = utils.get_experiments_directories_by_prefix(prefix, is_local)

    total_experiments = 0
    total_valid_experiments = 0
    invalid_experiments = []
    running_experiments = []

    for dir in dirs:
        exp_path = utils.resolve_experiment_path(dir, is_local=is_local, raise_ex=False)
        try:
            experiments_data = utils.load_experiments_file(exp_path)
        except FileNotFoundError:
            running_experiments.append(f"Dir: {dir}")


        for run, data in experiments_data.items():
            total_experiments += 1
            if not utils.is_experiment_run_valid(data):
                reason = ""

                if data["request_approval_status_code"] != 202:
                    reason += "Non 202 Status code"

                if data["accuracies"] == {}:
                    reason += ", " if reason != "" else ""
                    reason += "Accuracies are empty"

                invalid_experiments.append(f"Dir: {dir} | Run: {run} | Reason: {reason}")
            else:
                total_valid_experiments += 1
    
    print(f"Valid experiments: [{total_valid_experiments} / {total_experiments}]")

    if len(running_experiments) > 0:
        print("> Running experiments:")
        [print(f"    - {ex}") for ex in running_experiments]

    print("> Invalid directories:")
    [print(f"    - {ex}") for ex in invalid_experiments]


def _resolve_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("-pr", "--prefix")
    utils.add_boolean_argument(parser, conf.F_ARGUMENT)

    args = parser.parse_args()

    return args.prefix, not args.fabric_mode

if __name__ == '__main__':
    main()
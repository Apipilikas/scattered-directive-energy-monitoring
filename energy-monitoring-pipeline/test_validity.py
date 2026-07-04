import utils
import argparse
import configuration as conf

def main():
    prefix, is_local, all = _resolve_args()

    print(f"============= Test valid results =============")

    if all:
        for normal_prefix in conf.PREFIXES:
            print(f"\n> Validity for prefix: {normal_prefix}")
            _test_validity(normal_prefix, is_local)

            pa_prefix = f"pa_{normal_prefix}"
            print(f"\n> Validity for policy aware prefix: {pa_prefix}")
            _test_validity(pa_prefix, is_local)

    else:
        _test_validity(prefix, is_local)

def _test_validity(prefix, is_local = True):
    dirs = utils.get_experiments_directories_by_prefix(prefix, is_local)

    total_experiments = 0
    total_valid_experiments = 0
    invalid_non_202_experiments = 0
    invalid_empty_accuracies_exeperiments = 0
    invalid_experiments = []
    running_experiments = []

    for dir in dirs:
        exp_path = utils.resolve_experiment_path(dir, is_local=is_local, raise_ex=False)
        try:
            experiments_data = utils.load_experiments_file(exp_path)
            
            for run, data in experiments_data.items():
                total_experiments += 1
                if not utils.is_experiment_run_valid(data):
                    reason = ""

                    if data["request_approval_status_code"] != 202:
                        reason += "Non 202 Status code"
                        invalid_non_202_experiments += 1

                    if data["accuracies"] == {}:
                        if reason == "":
                            reason += "Accuracies are empty"
                            invalid_empty_accuracies_exeperiments += 1

                    invalid_experiments.append(f"Dir: {dir} | Run: {run} | Reason: {reason}")
                else:
                    total_valid_experiments += 1
        except FileNotFoundError:
            running_experiments.append(f"Dir: {dir}")


    
    print(f"Valid experiments: [{total_valid_experiments} / {total_experiments}]")

    if len(running_experiments) > 0:
        print("> Running experiments:")
        [print(f"    - {ex}") for ex in running_experiments]

    if len(invalid_experiments) > 0:
        print(f"> Invalid non-202 experiments: {invalid_non_202_experiments}")
        print(f"> Invalid premature termination experiments: {invalid_empty_accuracies_exeperiments}")
        print("> Invalid directories:")
        [print(f"    - {ex}") for ex in invalid_experiments]


def _resolve_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("-pr", "--prefix")
    parser.add_argument("-all", "--all", action='store_true')
    utils.add_boolean_argument(parser, conf.F_ARGUMENT)

    args = parser.parse_args()

    return args.prefix, not args.fabric_mode, args.all

if __name__ == '__main__':
    main()
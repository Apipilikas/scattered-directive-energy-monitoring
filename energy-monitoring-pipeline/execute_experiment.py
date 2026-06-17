import datetime
import time
import configuration as conf
from prometheus_executor import execute_query
import requests
import json
from collect_metrics import collect_metrics, save_metrics_to_csv
import argparse
import csv
import os
import utils

# URLs
API_BASE_URL = "http://localhost:8080/api/v1"
REQUEST_APPROVAL_URL = f"{API_BASE_URL}/requestApproval"
GET_TRAINING_STATUS_URL = f"{API_BASE_URL}/getTrainingStatus"

# Request bodies
REQUEST_APPROVAL_DATA_PROVIDERS = ["server", "clientone", "clienttwo", "clientthree"]
REQUEST_APPROVAL_BODY = {
    "type": "vflTrainModelRequest",
    "user": {
      "id": "1234",
      "userName": "evangelos.pipilikas@student.uva.nl"
    },
    "dataProviders": REQUEST_APPROVAL_DATA_PROVIDERS,
    "data_request": {
      "type": "vflTrainModelRequest",
      "data": {
        "learning_rate": 0.1,
        "cycles": 180,
        "policy_removal": -1,
        "policy_reintroduction": -1,
        "training_backtrack": 0
    },
    "requestMetadata": {}
    }
}
REQUEST_APPROVAL_HEADER = {
    "Content-Type": "application/json",
    "Host": "api-gateway.api-gateway.svc.cluster.local"
}

PROM_CONTAINERS = "{container_name=~\"kernel_processes|system_processes|" + "|".join(conf.get_agents())  + "|policy.*|orchestrator|sidecar|rabbitmq|api-gateway\"}"
PROM_ENERGY_QUERY_TOTAL = f"sum(kepler_container_joules_total{PROM_CONTAINERS}) by ({conf.KEPLER_LABEL})"
PROM_ENERGY_QUERY_RANGE = f"sum(increase(kepler_container_joules_total{PROM_CONTAINERS}[{conf.PROM_IDLE_DURATION}])) by ({conf.KEPLER_LABEL})"

def _get_duration(is_active = False):
    return conf.PROM_ACTIVE_DURATION if is_active else conf.PROM_IDLE_DURATION

def _get_energy_query_range(is_active = False):
    containers_filter = PROM_CONTAINERS

    if run_custom:
        containers_filter = "{container_name=\"" + custom_container + "\"}"

    return f"sum(increase(kepler_container_joules_total{containers_filter}[{_get_duration(is_active)}])) by ({conf.KEPLER_LABEL})"

run_baseline = False
run_custom = False
custom_container = ""
output_path = ""

def main():
    iterations = _resolve_args()
    
    baseline_str = "(baseline)" if run_baseline else ""
    custom_container_str = f"({custom_container})" if run_custom else ""
    print(f"============= Execute experiment {baseline_str} {custom_container_str} =============")
    
    iterations_no = int(iterations) if not iterations is None else conf.EXPERIMENT_RUNS_NO 
    execute_experiment(iterations_no)
    _delete_experiment_files(iterations_no)

def _request_approval():
    response = requests.post(
        REQUEST_APPROVAL_URL, json=REQUEST_APPROVAL_BODY, headers=REQUEST_APPROVAL_HEADER
        )
    
    response_content = response.json()

    id = ""
    status_code = response.status_code
    execution_time = response.elapsed.total_seconds()

    if "request_id" in response_content:
        id = response_content["request_id"]
    elif "active_request_id" in response_content:
        id = response_content["active_request_id"]
    else:
        raise Exception("Response is not recognizable.")

    return id, status_code, execution_time

def _get_training_status(jobId : str):
    response = requests.get(
        GET_TRAINING_STATUS_URL, params={"id": jobId}, headers=REQUEST_APPROVAL_HEADER
    )

    return response.json()

def _get_energy_comsumption(is_active = False):
    query = _get_energy_query_range(is_active) 
    return execute_query(query)

def _calculate_total_energy(metrics: dict):
    return sum(float(value) for value in metrics.values())

def _format_datetime(seconds) -> str:
    return str(datetime.timedelta(seconds=seconds))

def execute_experiment(runs_no: int):
    runs = {}

    for r in range(runs_no):
        print(f"\n> Starting new experiment run [{r + 1}/{runs_no}]")
        try:
            runs[r] = execute_experiment_run(r)
        except Exception as e:
            print(f"Error has been occurred while executing experiment with number: {r}.\n {e}")

    with open(f"{output_path}/{conf.EXPERIMENTS_OUTPUT_FILE_NAME}", 'w') as f:
        json.dump(runs, f, indent=2)

def execute_experiment_run(run_no: int):
    # Phase 1: Idle period
    # Wait idle period
    print("\n> Idle period")
    experiment_start_time = time.time()
    
    print("Waiting for idle period ...")
    time.sleep(conf.IDLE_PERIOD)
    
    idle_energy = _get_energy_comsumption()
    total_idle_energy = _calculate_total_energy(idle_energy)

    accuracies = {}
    status_code = 0
    execution_time = 0

    # Phase 2: Active period
    # Record the start time of the active period
    print("\n> Active period")
    active_start_time = time.time()
    if run_baseline:
        time.sleep(conf.ACTIVE_PERIOD)
    else:
        try:
            request_id, status_code, execution_time = _request_approval()

            if status_code != 202:
                print("Request approval status code was not expected!")
            else:
                while True:
                    time.sleep(5)
                    response = _get_training_status(request_id)
                    is_training_done = response["status"] == "done"

                    if is_training_done:
                        accuracies = response["results"]
                        break
        except Exception as e:
            print(f"Error occurred while fetching data.\n {e}")
    
    experiment_end_time = time.time()
    experiment_elapsed_time = experiment_end_time - experiment_start_time
    active_elapsed_time = time.time() - active_start_time

    remaining_time = conf.ACTIVE_PERIOD - active_elapsed_time

    if remaining_time > 0:
        # To Change
        print("Waiting for remaining active period...")
        time.sleep(remaining_time)

    active_energy = _get_energy_comsumption()
    total_active_energy = _calculate_total_energy(active_energy)

    experiment_elapsed_datetime = _format_datetime(experiment_elapsed_time)
    active_elapsed_datetime = _format_datetime(active_elapsed_time)

    print("\n> Summary")
    print(f"Experiment elapsed time: {experiment_elapsed_time} s ({experiment_elapsed_datetime})")
    print(f"Active period elapsed time: {active_elapsed_time} s ({active_elapsed_datetime})")

    if run_custom:
        dfs = collect_metrics(experiment_start_time, experiment_end_time, {f"{custom_container}_energy" : _get_energy_query_range(True)})
    else:
        dfs = collect_metrics(experiment_start_time, experiment_end_time)

    output_metrics_path = f"{output_path}/experiment_{run_no}_metrics.csv"
    save_metrics_to_csv(dfs, output_metrics_path)

    output_total_metrics_path = f"{output_path}/experiment_{run_no}_total_metrics.csv"
    with open(output_total_metrics_path, mode="w", newline="") as file:
        fieldnames = ["total_idle_energy", "total_active_energy", "total_energy_difference"]
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        # Calculate total idle, active and difference energy consumption
        total_energy_difference = total_active_energy - total_idle_energy
        
        # Add energy data
        writer.writerow({
            "total_idle_energy": total_idle_energy,
            "total_active_energy": total_active_energy,
            "total_energy_difference": total_energy_difference
        })

    output = {
        "idle_energy": idle_energy,
        "active_energy": active_energy,
        "request_approval_status_code": status_code,
        "request_approval_execution_time": execution_time,
        "experiment_elapsed_time": experiment_elapsed_datetime,
        "active_elapsed_time": active_elapsed_datetime,
        "accuracies": accuracies,
        "total_metrics_path": output_total_metrics_path,
        "metrics_path": output_metrics_path
    }

    with open(f"{output_path}/experiment_{run_no}.json", 'w') as f:
        json.dump(output, f, indent=2)

    return output

def _delete_experiment_files(runs_no: int):
    # Delete temp files
    for r in range(runs_no):
        file_name = f"{output_path}/experiment_{r}.json"

        if os.path.exists(file_name):
            os.remove(file_name)

def _resolve_output_path(arg, is_local = True):
    timestamp = datetime.datetime.now().strftime("%y%m%d_%H%M")
    output_prefix = f"{arg}_" if arg is not None else ""
    folder_name = f"{output_prefix}experiment_{timestamp}"

    experiment_mode_folder = utils.get_experiment_mode_folder(is_local)

    output_path = f"{conf.EXPERIMENT_OUTPUT_FOLDER}/{experiment_mode_folder}/{folder_name}"
    os.makedirs(output_path, exist_ok=True)

    return output_path


def _resolve_args():
    global run_baseline
    global run_custom
    global custom_container
    global output_path

    parser = argparse.ArgumentParser()
    parser.add_argument("-b", "--baseline", action='store_true')
    parser.add_argument("-op", "--output-prefix")
    parser.add_argument("-c", "--custom")
    parser.add_argument("-i", "--iterations")
    utils.add_boolean_argument(parser, conf.F_ARGUMENT)
    
    args = parser.parse_args()
    
    run_baseline = args.baseline
    run_custom = args.custom is not None
    output_path = _resolve_output_path(args.output_prefix, not args.fabric_mode)

    if run_custom:
        custom_container = str(args.custom)

    return args.iterations

if __name__ == '__main__':
    main()
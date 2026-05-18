import datetime
import time
import configuration as conf
from prometheus_executor import execute_query
import requests
import json
from collect_metrics import collect_metrics, save_metrics_to_csv
import argparse

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
PROM_SIDECAR_CONTAINER = "{container_name=\"sidecar\"}"
PROM_ENERGY_QUERY_TOTAL = f"sum(kepler_container_joules_total{PROM_CONTAINERS}) by ({conf.KEPLER_LABEL})"
PROM_ENERGY_QUERY_RANGE = f"sum(increase(kepler_container_joules_total{PROM_CONTAINERS}[{conf.PROM_DURATION}])) by ({conf.KEPLER_LABEL})"
PROM_SIDECAR_ENERGY_QUERY_RANGE = f"sum(increase(kepler_container_joules_total{PROM_SIDECAR_CONTAINER}[2m])) by (pod_name)"

run_baseline = False
run_sidecar = False

def main():
    iterations = _resolve_args()
    
    baseline_str = "(baseline)" if run_baseline else ""
    sidecar_str = "(sidecar)" if run_sidecar else ""
    print(f"============= Execute experiment {baseline_str} {sidecar_str} =============")
    
    iterations_no = int(iterations) if not iterations is None else conf.EXPERIMENT_RUNS_NO 
    execute_experiment(iterations_no)

def _request_approval():
    response = requests.post(
        REQUEST_APPROVAL_URL, json=REQUEST_APPROVAL_BODY, headers=REQUEST_APPROVAL_HEADER
        )
    
    response_content = response.json()

    id = ""

    if "request_id" in response_content:
        id = response_content["request_id"]
    elif "active_request_id" in response_content:
        id = response_content["active_request_id"]
    else:
        raise Exception("Response is not recognizable.")

    return id

def _get_training_status(jobId : str):
    response = requests.get(
        GET_TRAINING_STATUS_URL, params={"id": jobId}, headers=REQUEST_APPROVAL_HEADER
    )

    return response.json()

def _get_energy_comsumption():
    query = PROM_SIDECAR_ENERGY_QUERY_RANGE if run_sidecar else PROM_ENERGY_QUERY_RANGE
    return execute_query(query)

def _calculate_total_energy(metrics: dict):
    return sum(float(value) for value in metrics.values())

def _format_datetime(seconds) -> str:
    return str(datetime.timedelta(seconds=seconds))

def execute_experiment(runs_no: int):
    runs = {}

    for r in range(runs_no):
        print(f"\n> Starting new experiment run {r}/{runs_no}")
        runs[r] = execute_experiment_run(r)

    with open('output/experiments.json', 'w') as f:
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

    # Phase 2: Active period
    # Record the start time of the active period
    print("\n> Active period")
    active_start_time = time.time()
    if run_baseline:
        time.sleep(conf.ACTIVE_PERIOD)
    else:
        request_id = _request_approval()

        while True:
            time.sleep(5)
            response = _get_training_status(request_id)
            is_training_done = response["status"] == "done"

            if is_training_done:
                accuracies = response["results"]
                break
    
    active_energy = _get_energy_comsumption()
    total_active_energy = _calculate_total_energy(active_energy)

    total_energy_difference = total_active_energy - total_idle_energy
    
    experiment_end_time = time.time()
    experiment_elapsed_time = experiment_end_time - experiment_start_time
    active_elapsed_time = time.time() - active_start_time

    remaining_time = conf.ACTIVE_PERIOD - active_elapsed_time

    if remaining_time > 0:
        # To Change
        time.sleep(remaining_time)

    print("\n> Summary")
    print(f"Experiment elapsed time: {experiment_elapsed_time} s ({_format_datetime(experiment_elapsed_time)})")
    print(f"Active period elapsed time: {active_elapsed_time} s ({_format_datetime(active_elapsed_time)})")

    if run_sidecar:
        dfs = collect_metrics(experiment_start_time, experiment_end_time, {"sidecar_energy" : PROM_SIDECAR_ENERGY_QUERY_RANGE})
    else:
        dfs = collect_metrics(experiment_start_time, experiment_end_time)

    save_metrics_to_csv(dfs, f"output/experiment_{run_no}_metrics.csv")

    output = {
        "idle_energy": idle_energy,
        "total_idle_energy": total_idle_energy,
        "active_energy": active_energy,
        "total_active_energy": total_active_energy,
        "total_energy_difference": total_energy_difference,
        "accuracies": accuracies,
        "metrics_path": "output/experiment_metrics.csv"
    }

    with open(f"output/experiment_{run_no}.json", 'w') as f:
        json.dump(output, f, indent=2)

    return output

def _resolve_args():
    global run_baseline
    global run_sidecar

    parser = argparse.ArgumentParser()
    parser.add_argument("-b", "--baseline", action='store_true')
    parser.add_argument("-s", "--sidecar", action='store_true')
    parser.add_argument("-i", "--iterations")
    
    args = parser.parse_args()
    
    run_baseline = args.baseline
    run_sidecar = args.sidecar

    return args.iterations

if __name__ == '__main__':
    main()
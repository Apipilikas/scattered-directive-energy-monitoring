import time
from configuration import *
from prometheus_executor import execute_query
import requests
import json
from collect_metrics import collect_metrics, save_metrics_to_csv

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

PROM_CONTAINERS = "{container_name=~\"kernel_processes|system_processes|" + "|".join(get_agents())  + "|policy.*|orchestrator|sidecar|rabbitmq|api-gateway\"}"
PROM_ENERGY_QUERY_TOTAL = f"sum(kepler_container_joules_total{PROM_CONTAINERS}) by ({KEPLER_LABEL})"
PROM_ENERGY_QUERY_RANGE = f"sum(increase(kepler_container_joules_total{PROM_CONTAINERS}[{PROM_DURATION}])) by ({KEPLER_LABEL})"

def main():
    print("============= Execute experiment =============")
    execute_experiment()

def _request_approval():
    response = requests.post(
        REQUEST_APPROVAL_URL, json=REQUEST_APPROVAL_BODY, headers=REQUEST_APPROVAL_HEADER
        )
    
    status_code = response.status_code
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
    return execute_query(PROM_ENERGY_QUERY_RANGE)

# def _save_results(results: dict):
#     file_name = ""
#     fieldnames = ["idle_energy_total", "active_energy_total", "total_energy_difference", "average_exec_time"]
#     writer = csv.DictWriter(file, fieldnames=fieldnames)
#     writer.writeheader()
#     for result_no, result_data in results.items():
#         total_idle_energy = sum(float(value) for value in result_data["idle_energy"].values())
#         total_active_energy = sum(float(value) for value in result_data["active_energy"].values())
#         total_difference = total_active_energy - total_idle_energy


def execute_experiment():
    runs = {}

    for r in range(1):
        runs[r] = execute_experiment_run()

def execute_experiment_run():
    # Phase 1: Idle period
    # Wait idle period
    print("> Idle period")
    print("Waiting for idle period ...")
    experiment_start_time = time.time()
    time.sleep(IDLE_PERIOD)
    idle_energy = _get_energy_comsumption()
    print(f"Idle Energy: {idle_energy} (in J)")

    # Phase 2: Active period
    # Record the start time of the active period
    print("> Active period")
    active_start_time = time.time()
    request_id = _request_approval()

    accuracies = {}

    while True:
        time.sleep(5)
        response = _get_training_status(request_id)
        is_training_done = response["status"] == "done"

        if is_training_done:
            accuracies = response["results"]
            break
    
    active_energy = _get_energy_comsumption()
    experiment_end_time = time.time()
    experiment_elapsed_time = experiment_end_time - experiment_start_time
    active_elapsed_time = time.time() - active_start_time

    print("\n> Summary")
    print(f"Experiment elapsed time: {experiment_elapsed_time}")
    print(f"Active period elapsed time: {active_elapsed_time}")

    dfs = collect_metrics(experiment_start_time, experiment_end_time)
    save_metrics_to_csv(dfs, "output/experiment_metrics.csv")

    output = {
        "idle_energy": idle_energy,
        "active_energy": active_energy,
        "accuracies": accuracies,
        "metrics_path": "output/experiment_metrics.csv"
    }

    with open('output/experiment.json', 'w') as f:
        json.dump(output, f, indent=2)

    return output

if __name__ == '__main__':
    main()
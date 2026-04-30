import time
from configuration import *
from prometheus_executor import execute_query
import requests
import csv

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
    return

def _request_approval():
    response = requests.post(
        REQUEST_APPROVAL_URL, json=REQUEST_APPROVAL_BODY, headers=REQUEST_APPROVAL_HEADER
        )
    
    status_code = response.status_code

    if status_code == "202":
        return response.json()["request_id"]
    else:
        raise Exception("Not accepted")

def _get_training_status(jobId : str):
    response = requests.get(
        GET_TRAINING_STATUS_URL, params={"jobId": jobId}, headers=REQUEST_APPROVAL_HEADER
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

    for r in range(10):
        runs[r] = execute_experiment_run()

def execute_experiment_run():
    # Phase 1: Idle period
    # Wait idle period
    print("Waiting for idle period...")
    time.sleep(IDLE_PERIOD)
    idle_energy = _get_energy_comsumption()
    print(f"Idle Energy: {idle_energy} (in J)")

    # Phase 2: Active period
    # Record the start time of the active period
    start_time = time.time()
    request_id = _request_approval()

    accuracies = {}

    while True:
        response = _get_training_status(request_id)
        is_training_done = response["status"] == "done"

        if is_training_done:
            accuracies = response["results"]
            break
    
    elapsed_time = time.time() - start_time
    active_energy = _get_energy_comsumption()

    return {
        "idle_energy": idle_energy,
        "active_energy": active_energy,
        "accuracies": accuracies
    }


if __name__ == '__main__':
    main()
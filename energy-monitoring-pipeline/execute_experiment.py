import datetime
import time
import configuration as conf
from prometheus_executor import execute_query
import requests
import json
from collect_metrics import collect_metrics, save_metrics_to_csv
import argparse
import csv
import subprocess
import os
import utils
import faulthandler

faulthandler.enable()

# URLs
API_BASE_URL = "http://localhost:8080/api/v1"
REQUEST_APPROVAL_URL = f"{API_BASE_URL}/requestApproval"
GET_TRAINING_STATUS_URL = f"{API_BASE_URL}/getTrainingStatus"

# Request bodies
REQUEST_APPROVAL_DATA_PROVIDERS = ["clientone", "clienttwo", "clientthree", "server"]
REQUEST_APPROVAL_DATA_BODY = {
    "learning_rate": 0.1,
    "cycles": 180,
    "policy_removal": -1,
    "policy_reintroduction": -1,
    "training_backtrack": 0,
    "communication_frequency": 15,
    "sample_batch_size": 256
}
REQUEST_APPROVAL_POLICY_AWARE_DATA_BODY = {
    "learning_rate": 0.1,
    "cycles": 180,
    "policy_removal": 40,
    "policy_reintroduction": 80,
    "training_backtrack": 0,
    "communication_frequency": 15,
    "sample_batch_size": 256
}
REQUEST_APPROVAL_HEADER = {
    "Content-Type": "application/json",
    "Host": "api-gateway.api-gateway.svc.cluster.local"
}

# For fabric
PROM_CONTAINERS_FABRIC = "{container_name=~\"system_processes|" + "|".join(conf.get_agents())  + "|policy.*|orchestrator|sidecar|rabbitmq|api-gateway\"}"
# For local
PROM_CONTAINERS_LOCAL = "{container_name=~\"kernel_processes|system_processes|" + "|".join(conf.get_agents())  + "|policy.*|orchestrator|sidecar|rabbitmq|api-gateway\"}"

is_local = False
execute_policy_aware = False
run_baseline = False
run_custom = False
custom_container = ""
output_path = ""
relative_path = ""

def _get_duration(is_active = False):
    return conf.PROM_ACTIVE_DURATION if is_active else conf.PROM_IDLE_DURATION

def _get_energy_query_range(is_active = False, seconds = -1):
    containers_filter = PROM_CONTAINERS_LOCAL if is_local else PROM_CONTAINERS_FABRIC

    duration = f"{seconds}s"

    if seconds == -1:
        duration = _get_duration(is_active)

    if run_custom:
        containers_filter = "{container_name=\"" + custom_container + "\"}"

    return f"sum(increase(kepler_container_joules_total{containers_filter}[{duration}])) by ({conf.KEPLER_LABEL})"

def _get_carbon_emission_query_range():
    containers_filter = PROM_CONTAINERS_LOCAL if is_local else PROM_CONTAINERS_FABRIC

    if run_custom:
        containers_filter = "{container_name=\"" + custom_container + "\"}"

    return f"""(sum(increase(kepler_container_joules_total{containers_filter}[1h]) * ({conf.KEPLER_WATT_PER_SECOND_TO_KWH})) by ({conf.KEPLER_LABEL})) 
                * 
                (
                sum(count_over_time(kepler_container_joules_total{containers_filter}[24h])) by ({conf.KEPLER_LABEL}) 
                / 
                sum(count_over_time(kepler_container_joules_total{containers_filter}[1h])) by ({conf.KEPLER_LABEL})
                )"""

def main():
    iterations = _resolve_args()
    
    baseline_str = "(baseline)" if run_baseline else ""
    custom_container_str = f"({custom_container})" if run_custom else ""
    policy_aware_str = "(Policy aware)" if execute_policy_aware else ""
    print(f"============= Execute experiment {baseline_str} {custom_container_str} {policy_aware_str} =============")
    
    iterations_no = int(iterations) if not iterations is None else conf.EXPERIMENT_RUNS_NO 
    execute_experiment(iterations_no)

def _get_request_approval_body():
    data_body = REQUEST_APPROVAL_POLICY_AWARE_DATA_BODY if execute_policy_aware else REQUEST_APPROVAL_DATA_BODY

    return {
        "type": "vflTrainModelRequest",
        "user": {
        "id": "GUID",
        "userName": "evangelos.pipilikas@student.uva.nl"
        },
        "dataProviders": REQUEST_APPROVAL_DATA_PROVIDERS,
        "data_request": {
        "type": "vflTrainModelRequest",
        "data": data_body,
        "requestMetadata": {}
        }
    }

def _request_approval():
    response = requests.post(
        REQUEST_APPROVAL_URL, json=_get_request_approval_body(), headers=REQUEST_APPROVAL_HEADER
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

def _get_carbon_emission():
    query = _get_carbon_emission_query_range()
    metrics = execute_query(query)

    for container_name, energy_value in metrics.items():
        site = None if is_local else conf.get_site_from_container(container_name)
        
        coefficient = conf.CARBON_COEFFICIENTS.get(site, conf.KEPLER_CARBON_COEFFICIENT)
        
        metrics[container_name] = float(energy_value) * coefficient

    return metrics

def _get_energy_comsumption(is_active = False, seconds = -1):
    query = _get_energy_query_range(is_active, seconds) 
    return execute_query(query)

def _sum_metrics(metrics: dict):
    return sum(float(value) for value in metrics.values())

def _format_datetime(seconds) -> str:
    return str(datetime.timedelta(seconds=seconds))

def execute_experiment(runs_no: int):
    runs = {}

    try:
        for r in range(runs_no):
            print(f"\n> Starting new experiment run [{r + 1}/{runs_no}]")
            run_output = execute_experiment_run(r)
            runs[r] = run_output

            if not utils.is_experiment_run_valid(run_output):
                print(f"Experiment {r} is not valid.")
                break
            

    except KeyboardInterrupt:
        print("\nExperiment manually interrupted by user!")
    except Exception as e:
        print(f">!< Fatal error occurred while executing experiment.\n {e}")

    finally:
        if runs:
            with open(f"{output_path}/{conf.EXPERIMENTS_OUTPUT_FILE_NAME}", 'w') as f:
                json.dump(runs, f, indent=2)
            _delete_experiment_files(runs_no)

def execute_experiment_run(run_no: int):
    # Phase 1: Idle period
    # Wait idle period
    print("\n> Idle period")
    experiment_start_time = time.time()
    
    print("Waiting for idle period ...")
    time.sleep(conf.IDLE_PERIOD)
    
    idle_energy = _get_energy_comsumption()
    total_idle_energy = _sum_metrics(idle_energy)

    idle_carbon_emission = _get_carbon_emission()
    total_idle_carbon_emission = _sum_metrics(idle_carbon_emission)

    accuracies = {}
    status_code = 0
    execution_time = 0

    # Phase 2: Active period
    # Record the start time of the active period
    print("\n> Active period")
    active_start_time = time.time()

    wait = True
    training_status = ""

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
                    training_status = response["status"]

                    is_training_done = training_status == "done"
                    is_training_failed = training_status == "failed"

                    if is_training_done:
                        accuracies = response["results"]
                        break

                    if is_training_failed:
                        accuracies = response["results"]
                        print("Training pipeline returned [failed] status instead of [done]!")
                        break
        except Exception as e:
            wait = False
            print(f">!< Error occurred while fetching data.\n {e}")
            _retrieve_logs()
    
    experiment_end_time = time.time()
    experiment_elapsed_time = experiment_end_time - experiment_start_time
    active_elapsed_time = time.time() - active_start_time

    experiment_elapsed_datetime = _format_datetime(experiment_elapsed_time)
    active_elapsed_datetime = _format_datetime(active_elapsed_time)

    clear_active_energy = _get_energy_comsumption(seconds=int(active_elapsed_time))
    total_clear_active_energy = _sum_metrics(clear_active_energy)

    clear_active_carbon_emission = _get_carbon_emission()
    total_clear_active_carbon_emission = _sum_metrics(clear_active_carbon_emission)

    remaining_time = conf.ACTIVE_PERIOD - active_elapsed_time

    if wait and remaining_time > 0:
        print(f"Active period elapsed time: {active_elapsed_time} s ({active_elapsed_datetime})")
        print("Waiting for remaining active period...")
        time.sleep(remaining_time)

    active_energy = _get_energy_comsumption()
    total_active_energy = _sum_metrics(active_energy)

    active_carbon_emission = _get_carbon_emission()
    total_active_carbon_emission = _sum_metrics(active_carbon_emission)

    print("\n> Summary")
    print(f"Experiment elapsed time: {experiment_elapsed_time} s ({experiment_elapsed_datetime})")
    print(f"Active period elapsed time: {active_elapsed_time} s ({active_elapsed_datetime})")

    if run_custom:
        dfs = collect_metrics(experiment_start_time, experiment_end_time, {f"{custom_container}_energy" : _get_energy_query_range(True)})
    else:
        dfs = collect_metrics(experiment_start_time, experiment_end_time)

    metrics_file_name = f"experiment_{run_no}_metrics.csv"
    output_metrics_path = f"{output_path}/{metrics_file_name}"
    relative_metrics_path = f"{relative_path}/{metrics_file_name}"
    save_metrics_to_csv(dfs, output_metrics_path)

    total_metrics_name = f"experiment_{run_no}_total_metrics.csv"
    output_total_metrics_path = f"{output_path}/{total_metrics_name}"
    relative_total_metrics_path = f"{relative_path}/{total_metrics_name}"
    with open(output_total_metrics_path, mode="w", newline="") as file:
        fieldnames = ["total_idle_energy", "total_active_energy", "total_energy_difference", "total_clear_active_energy", "total_clear_active_carbon_emission",
                      "total_idle_carbon_emission", "total_active_carbon_emission", "total_carbon_emission_difference"]
        
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()

        total_energy_difference = total_active_energy - total_idle_energy
        total_carbon_emission_difference = total_active_carbon_emission - total_idle_carbon_emission
        
        writer.writerow({
            "total_idle_energy": total_idle_energy,
            "total_active_energy": total_active_energy,
            "total_energy_difference": total_energy_difference,
            "total_clear_active_energy": total_clear_active_energy,
            "total_idle_carbon_emission": total_idle_carbon_emission,
            "total_active_carbon_emission": total_active_carbon_emission,
            "total_clear_active_carbon_emission": total_clear_active_carbon_emission,
            "total_carbon_emission_difference": total_carbon_emission_difference
        })

    output = {
        "training_status": training_status,
        "request_approval_status_code": status_code,
        "request_approval_execution_time": execution_time,
        "experiment_elapsed_time": experiment_elapsed_datetime,
        "active_elapsed_time": active_elapsed_datetime,
        "idle_energy": idle_energy,
        "active_energy": active_energy,
        "clear_active_energy": clear_active_energy,
        "idle_carbon_emission": idle_carbon_emission,
        "active_carbon_emission": active_carbon_emission,
        "clear_active_carbon_emission": clear_active_carbon_emission,
        "accuracies": accuracies,
        "total_metrics_path": relative_total_metrics_path,
        "metrics_path": relative_metrics_path
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

def _retrieve_logs():
    print("\nExperiment failure detected. Triggering retrieve_logs.sh for targets...")
    
    targets = [
        ("api-gateway", "api-gateway", "api-gateway"),
    ]

    for agent in conf.get_agents():
        container_name = "vfl-train" if agent != "server" else "vfl-train-model"
        targets.append((agent, "evangelos-pipilikas", container_name))
    
    script_path = os.path.join(os.path.dirname(__file__), "..", "scripts", "retrieve_logs.sh")
    
    for namespace, pod_prefix, container_name in targets:
        cmd = ["bash", script_path, namespace, pod_prefix, container_name]
        
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)
            print(f"> Successfully retrieved logs for {pod_prefix}")
        except subprocess.CalledProcessError as e:
            print(f">!< Failed to retrieve logs for {pod_prefix}. Script exited with code {e.returncode}")
        except FileNotFoundError:
            print(f">!< Could not find the bash script at: {script_path}")

def _resolve_output_path(arg, is_local = True):
    timestamp = datetime.datetime.now().strftime("%y%m%d_%H%M")
    output_prefix = f"{arg}_" if arg is not None else ""
    folder_name = f"{output_prefix}experiment_{timestamp}"

    current_dir = os.path.dirname(os.path.abspath(__file__))
    experiment_mode_folder = utils.get_experiment_mode_folder(is_local)

    relative_path = f"{conf.EXPERIMENT_OUTPUT_FOLDER}/{experiment_mode_folder}/{folder_name}"

    output_path = os.path.join(
        current_dir, 
        conf.EXPERIMENT_OUTPUT_FOLDER, 
        experiment_mode_folder, 
        folder_name
    )

    os.makedirs(output_path, exist_ok=True)

    return output_path, relative_path


def _resolve_args():
    global run_baseline
    global run_custom
    global custom_container
    global output_path
    global relative_path
    global execute_policy_aware
    global is_local

    parser = argparse.ArgumentParser()
    parser.add_argument("-b", "--baseline", action='store_true')
    parser.add_argument("-pa", "--policy-aware", action='store_true')
    parser.add_argument("-op", "--output-prefix")
    parser.add_argument("-c", "--custom")
    parser.add_argument("-i", "--iterations")
    utils.add_boolean_argument(parser, conf.F_ARGUMENT)
    
    args = parser.parse_args()
    
    run_baseline = args.baseline
    execute_policy_aware = args.policy_aware
    run_custom = args.custom is not None
    is_local = not args.fabric_mode

    output_path, relative_path = _resolve_output_path(args.output_prefix, is_local)

    if run_custom:
        custom_container = str(args.custom)

    return args.iterations

if __name__ == '__main__':
    main()
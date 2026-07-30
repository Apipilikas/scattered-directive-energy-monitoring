import json
import os

# General
COLLECT_MINUTES_BEFORE = 15
COLUMN_TO_DROP = "timestamp"
PREFIXES = ["baseline_experiment", 
            "baseline_event_driven_experiment", 
            "fed_bcd_experiment", 
            "overlap_fed_bcd_experiment", 
            "fed_encrypt_experiment"
            ]

# Paths / Files
DATA_OUTPUT_FOLDER = "output"
DATA_COLLECT_OUTPUT_PATH = f"{DATA_OUTPUT_FOLDER}/data_metrics.csv"
DATA_DA_OUTPUT_PATH = f"{DATA_OUTPUT_FOLDER}/da_data_metrics.csv"
DATA_RCA_OUTPUT_PATH = f"{DATA_OUTPUT_FOLDER}/rca_results.csv"

# Traces constants
TRACE_OUTPUT_PATH = f"{DATA_OUTPUT_FOLDER}/traces"
TRACE_FILENAME = "traces.json"
TRACE_SERVICES = ["clientone", "clienttwo", "clientthree", "server"]

# Experiment constants
_IDLE_PERIOD_MINS = 3
_ACTIVE_PERIOD_MINS = 3
EXPERIMENT_RUNS_NO = 10
IDLE_PERIOD = _IDLE_PERIOD_MINS * 60
ACTIVE_PERIOD = _ACTIVE_PERIOD_MINS * 60
EXPERIMENT_OUTPUT_FOLDER = "experiments"
EXPERIMENTS_OUTPUT_FILE_NAME = "experiments.json"
AVERAGE_EXPERIMENTS_FILE_NAME = "average_experiments.json"

# Plots constants
PLOT_OUTPUT_FOLDER = "plots"

# Kepler constants
KEPLER_WATT_PER_SECOND_TO_KWH = 1/3600000
KEPLER_COAL = 0.4
KEPLER_CARBON_COEFFICIENT = 0.2264

# Prometheus constants
PROM_IDLE_DURATION = f"{_IDLE_PERIOD_MINS}m"
PROM_ACTIVE_DURATION = f"{_ACTIVE_PERIOD_MINS}m"
PROM_URL = "http://localhost:9090"
PROM_QUERY_RANGE_STEPS = "15s"
CADVISOR_LABEL = "container_label_io_kubernetes_container_name"
KEPLER_LABEL = "container_name"
PROM_QUERIES = {
    "energy" : f"sum(increase(kepler_container_joules_total[{PROM_ACTIVE_DURATION}])) by ({KEPLER_LABEL})",
    "cpu_usage" : f"sum(rate(container_cpu_usage_seconds_total[{PROM_ACTIVE_DURATION}])) by ({CADVISOR_LABEL})",
    "memory_usage" : f"sum(rate(container_memory_usage_bytes[{PROM_ACTIVE_DURATION}])) by ({CADVISOR_LABEL})",
    "memory_rss_usage" : f"sum(rate(container_memory_rss[{PROM_ACTIVE_DURATION}])) by ({CADVISOR_LABEL})",
    "memory_cache_usage" : f"sum(rate(container_memory_cache[{PROM_ACTIVE_DURATION}])) by ({CADVISOR_LABEL})",
    # https://github.com/google/cadvisor/issues/2881 | There is a bug regarding disk. It always shows 0 value in 
    # both local and fabric environments.
    # "disk" : f"sum(rate(container_fs_reads_bytes_total[{DURATION}])) by ({CADVISOR_LABEL})",
    "carbon_coal": f"(sum(increase((kepler_container_joules_total[24h:1m]))) by ({KEPLER_LABEL}) * {KEPLER_WATT_PER_SECOND_TO_KWH}) * {KEPLER_COAL}",
    "carbon_emission": f"""(sum(increase(kepler_container_joules_total[1h]) * ({KEPLER_WATT_PER_SECOND_TO_KWH})) by ({KEPLER_LABEL})) 
                            * 
                            (
                            sum(count_over_time(kepler_container_joules_total[24h])) by ({KEPLER_LABEL}) 
                            / 
                            sum(count_over_time(kepler_container_joules_total[1h])) by ({KEPLER_LABEL})
                            ) * {KEPLER_CARBON_COEFFICIENT}"""
}

# Arguments
AD_ARGUMENT = '-ad', '--anomaly-detection', 'Run only anomaly detection algorithm'
RCA_ARGUMENT = '-rca', '--root-cause-analysis', 'Run only root cause analysis algorithm'
CM_ARGUMENT = '-cm', '--collect-metrics', 'Run only anomaly detection algorithm'
BE_ARGUMENT = '-be', '--both-environments', 'Execute experiment including both environments'
F_ARGUMENT = '-f', '--fabric-mode', 'Execute experiment on FABRIC'

# AD and RCA parameters
TRAINING_DATA_PATH = f"{DATA_OUTPUT_FOLDER}/baseline_data_metrics.csv"
RCD_K = 5

# Containers
CONTAINERS = [
    "kernel_processes",
    "system_processes",
    "api-gateway",
    "policy-enforcer",
    "orchestrator",
    "sidecar",
    "policy",
    "rabbitmq"
]

# Helpers
def get_agents():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    agreements_file = os.path.abspath(
        os.path.join(current_dir, "..", "configuration", "etcd_launch_files", "agreements.json")
    )

    agents = extract_property_from_json(agreements_file, "name")

    return agents

def extract_property_from_json(file_path: str, property_name: str):
    lst = []
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            data = json.load(file)
            
            if isinstance(data, list):
                for item in data:
                    if property_name in item:
                        lst.append(item[property_name])

            
        return lst

    except FileNotFoundError:
        print(f"Error: The file '{file_path}' was not found.")
    except json.JSONDecodeError:
        print(f"Error: '{file_path}' is not a valid JSON file.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

def get_containers():
    return CONTAINERS + get_agents()
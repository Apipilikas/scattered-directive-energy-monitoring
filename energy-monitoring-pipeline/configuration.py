from utils import extract_property_from_json

# General
COLLECT_MINUTES_BEFORE = 15
COLUMN_TO_DROP = "timestamp"

# Paths / Files
DATA_OUTPUT_FOLDER = "output"
DATA_COLLECT_OUTPUT_PATH = f"{DATA_OUTPUT_FOLDER}/data_metrics.csv"
DATA_ANALYZED_OUTPUT_PATH = f"{DATA_OUTPUT_FOLDER}/analyzed_data_metrics.csv"

# Prometheus
DURATION = "2m"
PROM_URL = "http://localhost:9090"
PROM_QUERY_RANGE_STEPS = "15s"
PROM_QUERIES = {
    "energy" : f"sum(increase(kepler_container_joules_total[{DURATION}])) by (container_name)",
    "cpu_usage" : f"sum(rate(container_cpu_usage_seconds_total[{DURATION}])) by (container_label_io_kubernetes_container_name)",
    # "cpu_usage" : f"rate(container_cpu_usage_seconds_total[{DURATION}])",
    "memory_usage" : f"sum(rate(container_memory_usage_bytes[{DURATION}])) by (container_label_io_kubernetes_container_name)",
    "memory_rss_usage" : f"sum(rate(container_memory_rss[{DURATION}])) by (container_label_io_kubernetes_container_name)",
    "memory_cache_usage" : f"sum(rate(container_memory_cache[{DURATION}])) by (container_label_io_kubernetes_container_name)",
    "disk" : f"sum(rate(container_fs_reads_bytes_total[{DURATION}])) by (container_label_io_kubernetes_container_name)"
}

# Arguments
AD_ARGUMENT = '-ad', '--anomaly-detection', 'Run only anomaly detection algorithm'
RCA_ARGUMENT = '-rca', '--root-cause-analysis', 'Run only root cause analysis algorithm'
CM_ARGUMENT = '-cm', '--collect-metrics', 'Run only anomaly detection algorithm'

# AD and RCA parameters
TRAINING_DATA_PATH = f"{DATA_OUTPUT_FOLDER}/baseline_data_metrics.csv"
RCD_K = 5

# Namespaces
NAMESPACES = [
    "api-gateway",
    "policy-enforcer",
    "orchestrator",
    "sidecar",
    "policy",
    "rabbitmq"
]

def get_namespaces():
    etcd_launch_files_path = "../configuration/etcd_launch_files"
    agents = extract_property_from_json(f"{etcd_launch_files_path}/agreements.json", "name")

    return NAMESPACES + agents
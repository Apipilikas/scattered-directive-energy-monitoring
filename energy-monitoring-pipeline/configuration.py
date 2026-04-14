from utils import extract_property_from_json

# General
DATA_COLLECT_OUTPUT_FILE = "data_metrics.csv"
COLLECT_MINUTES_BEFORE = 15

# Prometheus
PROM_URL = "http://localhost:9090"
PROM_QUERY_RANGE_STEPS = "15s"
PROM_QUERIES = {
    # "energy" : "",
    "cpu_usage" : "rate(container_cpu_usage_seconds_total[2m])",
    # "memory_usage" : "",
    # "memory_rss_usage" : "",
    # "memory_cache_usage" : "",
    # "disk" : ""
}

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
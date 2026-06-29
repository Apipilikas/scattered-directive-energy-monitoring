import sys
import json
import subprocess
from datetime import datetime
import configuration as conf

def get_matching_pods(namespace, prefix):
    print(f"\n> Searching namespace '{namespace}' for pods starting with '{prefix}'...")
    cmd = ["kubectl", "get", "pods", "-n", namespace, "-o", "jsonpath={.items[*].metadata.name}"]
    
    output = subprocess.check_output(cmd, text=True).strip()
    if not output:
        print(">!< No pod found!")
        return []
        
    all_pods = output.split()
    return [pod for pod in all_pods if pod.startswith(prefix)]

def _parse_time(iso_str):
    if not iso_str: return None
    return datetime.fromisoformat(iso_str.replace("Z", "+00:00"))

def collect_pod_metrics(pod_name, namespace="default"):
    cmd = ["kubectl", "get", "pod", pod_name, "-n", namespace, "-o", "json"]
    try:
        raw_data = subprocess.check_output(cmd, stderr=subprocess.DEVNULL)
        data = json.loads(raw_data)
    except subprocess.CalledProcessError:
        print(f">!< Error: Pod '{pod_name}' no longer exists in namespace '{namespace}'.")
        return

    # 1. Capture the API Birth Certificate
    birth_time = _parse_time(data["metadata"]["creationTimestamp"])
    
    # 2. Extract the static milestone receipts
    milestones = {}
    for condition in data.get("status", {}).get("conditions", []):
        milestones[condition["type"]] = _parse_time(condition["lastTransitionTime"])

    # 3. Calculate exact durations
    init_duration = 0.0
    boot_duration = 0.0
    total_lifespan = (datetime.now(birth_time.tzinfo) - birth_time).total_seconds()

    if "Initialized" in milestones:
        init_duration = (milestones["Initialized"] - birth_time).total_seconds()
        
    if "Ready" in milestones:
        boot_duration = (milestones["Ready"] - birth_time).total_seconds()

    # Print clean thesis stats
    print(f"\n>  Pod name: {pod_name}")
    print(f"    - Initialized: {init_duration:.2f} s")
    print(f"    - Running:  {boot_duration:.2f} s")
    print(f"    - Total:  {total_lifespan / 60:.2f} minutes ({total_lifespan:.1f}s)")

def main():
    for namespace in conf.get_agents():
        targeted_pods = get_matching_pods(namespace, "evangelos-pipilikas")
        for pod in targeted_pods:
            collect_pod_metrics(pod, namespace)

if __name__ == "__main__":
    main()
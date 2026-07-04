import sys
import json
import subprocess
from datetime import datetime
import configuration as conf

METRICS = ["Ready", "ContainersReady", "PodScheduled", "PodReadyToStartContainers", "Initialized"]

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

    birth_time = _parse_time(data["metadata"]["creationTimestamp"])
    
    milestones = {}
    for condition in data.get("status", {}).get("conditions", []):
        milestones[condition["type"]] = _parse_time(condition["lastTransitionTime"])

    total_lifespan = (datetime.now(birth_time.tzinfo) - birth_time).total_seconds()

    output = {}

    print(f"\n>  Pod name: {pod_name}")

    for metric in METRICS:
        duration = _get_condition(milestones, birth_time, metric)
        output[metric] = duration
        print(f"    - {metric}:  {_to_minutes(duration):.3f} minutes ({duration:.3f}s)")

    print(f"    - Total:  {_to_minutes(total_lifespan):.3f} minutes ({total_lifespan:.3f}s)")

    return output

def _get_condition(milestones: dict, birth_time, condition_name: str):
    duration = 0.0

    if condition_name in milestones:
        duration = (milestones[condition_name] - birth_time).total_seconds()

    return duration

def _to_minutes(lifespan: float):
    return lifespan / 60

def _calculate_pod_metrics_mean(results):
    print("\n>  Calculating means across the pods")
    for metric in METRICS:
        total_duration = sum(res.get(metric, 0) for res in results)
        mean_duration = total_duration / len(METRICS)
        
        print(f"    - Mean {metric}:  {_to_minutes(mean_duration):.3f} minutes ({mean_duration:.3f}s)")

def main():
    results = []

    for namespace in conf.get_agents():
        targeted_pods = get_matching_pods(namespace, "evangelos-pipilikas")
        for pod in targeted_pods:
            results.append(collect_pod_metrics(pod, namespace))

    _calculate_pod_metrics_mean(results)

if __name__ == "__main__":
    main()
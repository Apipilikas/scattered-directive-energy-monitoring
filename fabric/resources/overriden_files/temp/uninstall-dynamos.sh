#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
source "${SCRIPT_DIR}/../dynamos.conf"

echo "Uninstalling DYNAMOS namespaces..."
helm uninstall nginx namespaces core orchestrator agents thirdparties api-gateway surf --ignore-not-found

echo "Uninstalling monitoring namespaces..."
helm uninstall prometheus grafana kepler -n monitoring

echo "Uninstalling nginx..."
helm uninstall nginx --ignore-not-found
helm uninstall nginx -n ingress

#Config
config_path="${DYNAMOS_ROOT}/configuration"
etcd_launch_files="${config_path}/etcd_launch_files"

agents=$(grep '"name":' ${etcd_launch_files}/agreements.json | awk -F'"' '{print $4}' | paste -sd "," -)

{
# Parse the agents and thirdparties from the CLI arguments
IFS=',' read -r -a agents_array <<< "$agents"

echo "Clearing old jobs..."
for agent in "${agents_array[@]}"
do
    echo "Clearing pods for agent: ['$agent']"
    kubectl delete jobs --all -n "$agent"
done
}

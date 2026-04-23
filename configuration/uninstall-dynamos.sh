#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
source "${SCRIPT_DIR}/../dynamos.conf"

echo -e "=============== Started uninstalling DYNAMOS ===============\n"

echo -e "Uninstalling DYNAMOS namespaces...\n"
helm uninstall nginx namespaces core orchestrator agents thirdparties api-gateway surf --ignore-not-found

echo -e "Uninstalling monitoring namespaces...\n"
helm uninstall prometheus kepler -n monitoring --ignore-not-found

echo -e "Uninstalling nginx...\n"
helm uninstall nginx --ignore-not-found
helm uninstall nginx -n ingress

#Config
config_path="${DYNAMOS_ROOT}/configuration"
etcd_launch_files="${config_path}/etcd_launch_files"

agents=$(grep '"name":' ${etcd_launch_files}/agreements.json | awk -F'"' '{print $4}' | paste -sd "," -)

{
# Parse the agents and thirdparties from the CLI arguments
IFS=',' read -r -a agents_array <<< "$agents"

echo -e "Clearing old jobs...\n"
for agent in "${agents_array[@]}"
do
    echo "- Clearing pods for agent: ['$agent']"
    kubectl delete jobs --all -n "$agent"
done
}

echo "=============== Finished uninstalling DYNAMOS ==============="
#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
source "${SCRIPT_DIR}/../dynamos.conf"

echo -e "\n=============== Started restarting DYNAMOS ===============\n"

echo -e "Restarting api-gateway ...\n"
kubectl rollout restart deployment api-gateway -n api-gateway

echo -e "\nRestarting core ...\n"
kubectl rollout restart deployment -n core

echo -e "\nRestarting orchestrator ...\n"
kubectl rollout restart deployment orchestrator -n orchestrator
kubectl rollout restart deployment policy-enforcer -n orchestrator

#Config
config_path="${DYNAMOS_ROOT}/configuration"
etcd_launch_files="${config_path}/etcd_launch_files"

agents=$(grep '"name":' ${etcd_launch_files}/agreements.json | awk -F'"' '{print $4}' | paste -sd "," -)

{
# Parse the agents and thirdparties from the CLI arguments
IFS=',' read -r -a agents_array <<< "$agents"

echo -e "\nRestarting agents ...\n"
for agent in "${agents_array[@]}"
do
    echo "- Restarting agent: ['$agent']"
    kubectl rollout restart deployment "$agent" -n "$agent"
done
}

echo -e "\n=============== Finished restarting DYNAMOS ===============\n"
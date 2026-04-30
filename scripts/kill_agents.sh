#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
source "${SCRIPT_DIR}/../dynamos.conf"

echo -e "\n=============== Started killing lingering agents ===============\n"

#Config
config_path="${DYNAMOS_ROOT}/configuration"
etcd_launch_files="${config_path}/etcd_launch_files"

agents=$(grep '"name":' ${etcd_launch_files}/agreements.json | awk -F'"' '{print $4}' | paste -sd "," -)

{
# Parse the agents and thirdparties from the CLI arguments
IFS=',' read -r -a agents_array <<< "$agents"

echo -e "\nClearing old jobs...\n"
for agent in "${agents_array[@]}"
do
    echo "- Clearing pods for agent: ['$agent']"
    kubectl delete jobs --all -n "$agent"
done
}

echo -e "\n=============== Finished killing lingering agents ===============\n"
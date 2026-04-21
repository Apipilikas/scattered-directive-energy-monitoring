#!/bin/bash

set -e

# Importing dynamos config
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
source "${SCRIPT_DIR}/../dynamos.conf"

if [ "$1" == "local" ]; then
    echo "Environment set to 'LOCAL'."
    CHARTS_PATH="${CHARTS_LOCAL_PATH}"
elif [ "$1" == "fabric" ]; then
    echo "Environment set to 'FABRIC'."
    CHARTS_PATH="${CHARTS_FABRIC_PATH}"
else
    echo "ERROR: You must specify an environment argument: 'local' or 'fabric'."
    exit 1
fi

echo "=============== Started setting up DYNAMOS ==============="

# Change this to the path of the DYNAMOS repository on your disk
echo "Setting up paths..."

# Charts
core_chart="${CHARTS_PATH}/core"
namespace_chart="${CHARTS_PATH}/namespaces"
orchestrator_chart="${CHARTS_PATH}/orchestrator"
agents_chart="${CHARTS_PATH}/agents"
ttp_chart="${CHARTS_PATH}/thirdparty"
api_gw_chart="${CHARTS_PATH}/api-gateway"

# Config
k8s_service_files="${CONFIG_PATH}/k8s_service_files"
etcd_launch_files="${CONFIG_PATH}/etcd_launch_files"

# Add agents
agents=$(grep '"name":' ${etcd_launch_files}/agreements.json | awk -F'"' '{print $4}' | paste -sd "," -)
echo "Agents discovered: $agents"

configure_dynamos="${DYNAMOS_ROOT}/fabric/node_scripts/configure_dynamos.sh "
chmod +x ${configure_dynamos}
${configure_dynamos} $agents

rabbit_definitions_file="${k8s_service_files}/definitions.json"
example_definitions_file="${k8s_service_files}/definitions_example.json"

cp "$example_definitions_file" "$rabbit_definitions_file"
echo "definitions_example.json copied over definitions.json to ensure a clean file"

echo "Generating RabbitMQ password..."
# Create a password for a rabbit user
rabbit_pw=$(openssl rand -hex 16)

# Use the RabbitCtl to make a special hash of that password:
hashed_pw=$($SUDO docker run --rm rabbitmq:3-management rabbitmqctl hash_password $rabbit_pw)
actual_hash=$(echo "$hashed_pw" | cut -d $'\n' -f2)

echo "Replacing tokens..."
cp ${k8s_service_files}/definitions_example.json ${rabbit_definitions_file}


# The Rabbit Hashed password needs to be in definitions.json file, that is the configuration for RabbitMQ
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS sed
    sed -i '' "s|%PASSWORD%|${actual_hash}|g" ${rabbit_definitions_file}
else
    # GNU sed
    sed -i "s|%PASSWORD%|${actual_hash}|g" ${rabbit_definitions_file}
fi

echo "Installing namespaces..."
helm upgrade -i -f ${namespace_chart}/values.yaml namespaces ${namespace_chart} --set secret.password=${rabbit_pw}

echo "Preparing PVC"

{
    cd ${DYNAMOS_ROOT}/configuration
    ./fill-rabbit-pvc.sh "$1"
}

echo "Preparing energy monitoring installation..."

{
    cd ${DYNAMOS_ROOT}/configuration
    ./dynamos-monitoring-configuration.sh "$1"
}

echo "Installing NGINX..."
helm install -f ${core_chart}/ingress-values.yaml nginx oci://ghcr.io/nginxinc/charts/nginx-ingress -n ingress --version 0.18.0

echo "Installing DYNAMOS core..."
helm upgrade -i -f ${core_chart}/values.yaml core ${core_chart} --set hostPath=${HOME}

sleep 3

echo "Installing orchestrator layer..."
helm upgrade -i -f ${orchestrator_chart}/values.yaml orchestrator ${orchestrator_chart} --set dockerArtifactAccount=${DOCKERHUB_ACCOUNT}

if [ "$1" == "local" ]; then
    echo "Transferring local etcd_launch_files..."
    {
        cd ${DYNAMOS_ROOT}/configuration
        ./fill-etcd-pvc.sh
    }
fi



sleep 1

echo "Installing agents layer..."
helm upgrade -i -f ${agents_chart}/values.yaml agents ${agents_chart} --set dockerArtifactAccount=${DOCKERHUB_ACCOUNT}

sleep 1

echo "Installing thirdparty layer..."
helm upgrade -i -f ${ttp_chart}/values.yaml surf ${ttp_chart} --set dockerArtifactAccount=${DOCKERHUB_ACCOUNT}

sleep 1

echo "Installing api gateway..."
helm upgrade -i -f ${api_gw_chart}/values.yaml api-gateway ${api_gw_chart} --set dockerArtifactAccount=${DOCKERHUB_ACCOUNT}

echo "=============== Finished setting up DYNAMOS ==============="

exit 0
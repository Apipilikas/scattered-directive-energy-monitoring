#!/bin/bash

# Importing dynamos config
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
source "${SCRIPT_DIR}/../dynamos.conf"

# Paths
monitoring_chart="${CHARTS_PATH}/monitoring"

echo "Installing Prometheus..."
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update
helm upgrade -i -f ${monitoring_chart}/prometheus-values.yaml prometheus prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  --create-namespace

echo "Installing Kepler..."
helm repo add kepler https://sustainable-computing-io.github.io/kepler-helm-chart
helm repo update
helm upgrade -i kepler kepler/kepler \
    --namespace monitoring \
    --version 0.5.12 \
    --set serviceMonitor.enabled=true \
    --set serviceMonitor.labels.release=prometheus \
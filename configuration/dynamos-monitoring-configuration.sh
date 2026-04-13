#!/bin/bash

# Importing dynamos config
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
source "${SCRIPT_DIR}/../dynamos.conf"

# Paths
monitoring_chart="${CHARTS_PATH}/monitoring"

echo "Installing Prometheus..."
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update
helm upgrade -i -f ${monitoring_chart}/prometheus-values.yaml prometheus prometheus-community/prometheus

echo "Installing Grafana..."
helm repo add grafana-community https://grafana-community.github.io/helm-charts
helm repo update
helm upgrade -i -f ${monitoring_chart}/grafana-values.yaml grafana  grafana-community/grafana

echo "Installing Kepler..." 
helm repo add kepler https://sustainable-computing-io.github.io/kepler-helm-chart
helm repo update
helm upgrade -i -f ${monitoring_chart}/kepler-values.yaml kepler kepler/kepler \
  --version 0.6.1 
#!/bin/bash

# Importing dynamos config
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
source "${SCRIPT_DIR}/../dynamos.conf"

# Paths
monitoring_chart="${CHARTS_PATH}/monitoring"

echo "Installing Prometheus..."
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update
helm upgrade -i -f ${monitoring_chart}/prometheus-values.yaml prometheus prometheus-community/prometheus \
  --namespace monitoring \
  --create-namespace

echo "Installing Grafana..."
helm repo add grafana-community https://grafana-community.github.io/helm-charts
helm repo update
helm upgrade -i -f ${monitoring_chart}/grafana-values.yaml grafana  grafana-community/grafana \
  --namespace monitoring

# >!< Cannot run in local environment >!<
# echo "Installing Kepler..."
# helm install kepler oci://quay.io/sustainable_computing_io/charts/kepler \
#   --namespace monitoring \
#   --version 0.11.4 
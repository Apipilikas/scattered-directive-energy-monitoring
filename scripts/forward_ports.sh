#!/bin/bash

echo -e "\n=============== Started port forwarding ===============\n"

kubectl port-forward svc/prometheus-kube-prometheus-prometheus 9090:9090 -n monitoring &
kubectl port-forward svc/api-gateway 8080:8080 -n api-gateway &
kubectl port-forward svc/orchestrator 8090:8080 -n orchestrator &
kubectl port-forward svc/prometheus-grafana 3000:80 -n monitoring &
kubectl port-forward service/jaeger 16686:16686 -n linkerd-jaeger &

echo -e "\nAll ports forwarded! Press Ctrl+C to exit.\n"
wait
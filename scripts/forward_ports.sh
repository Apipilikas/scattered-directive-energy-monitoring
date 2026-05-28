#!/bin/bash

wait_for_service() {
  local svc=$1
  local ns=$2
  
  echo "Waiting for service $svc in namespace $ns to be ready..."
  
  while true; do
    ENDPOINTS=$(kubectl get endpoints "$svc" -n "$ns" -o jsonpath='{.subsets[*].addresses[*].ip}' 2>/dev/null)
    
    if [[ -n "$ENDPOINTS" ]]; then
      echo "> Service $svc is ready!"
      break
    fi
    
    sleep 2
  done
}

echo -e "\n=============== Waiting for pods to be ready ===============\n"

wait_for_service "prometheus-kube-prometheus-prometheus" "monitoring"
wait_for_service "api-gateway" "api-gateway"
wait_for_service "orchestrator" "orchestrator"
wait_for_service "prometheus-grafana" "monitoring"

echo -e "\n=============== Started port forwarding ===============\n"

kubectl port-forward svc/prometheus-kube-prometheus-prometheus 9090:9090 -n monitoring &
kubectl port-forward svc/api-gateway 8080:8080 -n api-gateway &
sleep 1
kubectl port-forward svc/orchestrator 8090:8080 -n orchestrator &
kubectl port-forward svc/prometheus-grafana 3000:80 -n monitoring &
kubectl port-forward service/jaeger 16686:16686 -n linkerd-jaeger &

sleep 5
echo -e "\nAll ports forwarded! Press Ctrl+C to exit.\n"
wait
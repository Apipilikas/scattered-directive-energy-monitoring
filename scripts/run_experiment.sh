#!/bin/bash

set -e

# --- CONFIGURATION ---
MAX_RETRIES=3
TOTAL_RUNS=4
COOLDOWN_SECONDS=100 #seconds
K8S_SETTLE_TIME=200 #seconds

ENV="${1:-}"
TOTAL_RUNS="${2:-4}"
if [[ "$ENV" != "local" && "$ENV" != "fabric" ]]; then
    echo ">!< ERROR: First argument must be 'local' or 'fabric'"
    exit 1
fi
echo -e "=============== Started experiment execution ==============="

shift $(( $# >= 2 ? 2 : $# ))
PYTHON_ARGS="$@"

PIDS=()

stop_port_forwards() {
    if [ ${#PIDS[@]} -gt 0 ]; then
        echo -e "\n[-] Tearing down port-forwards..."
        kill "${PIDS[@]}" 2>/dev/null || true
        wait "${PIDS[@]}" 2>/dev/null || true
        PIDS=()
    fi
}

trap 'stop_port_forwards; exit 130' INT TERM

start_port_forwards() {
    echo -e "[-] Establishing Port Forwards..."
    kubectl port-forward svc/prometheus-kube-prometheus-prometheus 9090:9090 -n monitoring & PIDS+=($!)
    kubectl port-forward svc/api-gateway 8080:8080 -n api-gateway & PIDS+=($!)
    kubectl port-forward svc/orchestrator 8090:8080 -n orchestrator & PIDS+=($!)
    kubectl port-forward svc/prometheus-grafana 3000:80 -n monitoring & PIDS+=($!)
    kubectl port-forward service/jaeger 16686:16686 -n linkerd-jaeger & PIDS+=($!)
}

setup_dynamos_with_retry() {
    local attempt=1
    while [ $attempt -le $MAX_RETRIES ]; do
        echo -e "\n[Step 1/5] Running DYNAMOS Configuration (Attempt $attempt of $MAX_RETRIES)..."
        
        set +e
        ./configuration/dynamos-configuration.sh "$ENV"
        local exit_code=$?
        set -e

        if [ $exit_code -eq 0 ]; then
            return 0
        fi

        echo -e "\n>!< ERROR: DYNAMOS configuration failed with exit code $exit_code!"

        if [ $attempt -eq $CONFIG_MAX_RETRIES ]; then
            echo ">!< ERROR: Exhausted all $CONFIG_MAX_RETRIES attempts to configure DYNAMOS. Aborting suite."
            exit $exit_code
        fi

        echo "Scrubbing broken installation state before retrying in 15 seconds..."
        
        set +e
        ./uninstall-dynamos.sh > /dev/null 2>&1 # Wipe the half-baked charts
        set -e
        
        sleep 15
        ((attempt++))
    done
}

for (( i=1; i<=TOTAL_RUNS; i++ )); do
    echo -e "=============== STARTING SUITE RUN [ $i / $TOTAL_RUNS ] ==============="
    
    echo "[Step 1/5] Running Dynamos Configuration..."
    setup_dynamos_with_retry

    echo -e "\n[Step 2/5] Waiting ${K8S_SETTLE_TIME}s for Kubernetes pods to stabilize..."
    sleep "$K8S_SETTLE_TIME"

    echo "[Step 3/5] Binding local ports..."
    start_port_forwards
    sleep 4 # Give sockets 4 seconds to establish handshake

    echo -e "\n[Step 4/5] Triggering execute_experiment.py $PYTHON_ARGS ..."
    
    set +e 
    python -u energy-monitoring-pipeline/execute_experiment.py $PYTHON_ARGS
    PY_EXIT_CODE=$?
    set -e

    if [ $PY_EXIT_CODE -ne 0 ]; then
        echo -e "\n>!< WARNING: Python script exited with error code $PY_EXIT_CODE on run $i!"
    fi

    stop_port_forwards

    echo -e "\n[Step 5/5] Uninstalling DYNAMOS..."
    ./configuration/uninstall-dynamos.sh

    if [ "$i" -lt "$TOTAL_RUNS" ]; then
        echo -e "\nRun $i finished. Resting cluster for $COOLDOWN_SECONDS seconds..."
        sleep "$COOLDOWN_SECONDS"
    fi

done

echo -e "=============== Finshed experiment execution ==============="
exit 0
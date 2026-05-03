#!/bin/bash

if [ "$1" == "local" ]; then
    TEMP_POD_FILE="temp-pod-local.yaml"
elif [ "$1" == "fabric" ]; then
    TEMP_POD_FILE="temp-pod.yaml"
else
    echo ">!< ERROR: Environment is not specified: 'local' or 'fabric'. >!<"
    exit 1
fi

MAX_RETRIES=3
RETRY_COUNT=0
PODS_READY=false
WAIT_TIMEOUT="60s"

# Create the temporary pod with retrying as sometimes it gets stuck and I have to exit script and re-run it.
while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    echo -e "\nApplying ${TEMP_POD_FILE} (Attempt $((RETRY_COUNT+1))/${MAX_RETRIES})..."
    kubectl apply -f "${TEMP_POD_FILE}"

    # Wait for the pod to be in the 'Running' state
    echo -e "\nWaiting for temp-pod to be Running...\n"
    
    if kubectl wait --for=condition=Ready pod/temp-pod --timeout=${WAIT_TIMEOUT} -n core && \
       kubectl wait --for=condition=Ready pod/temp-pod-orch --timeout=${WAIT_TIMEOUT} -n orchestrator; then
        PODS_READY=true
        break
    else
        echo -e "\n>!< Timeout reached. Pods might be stuck in Pending. Retrying ... >!<"
        sleep 5
        RETRY_COUNT=$((RETRY_COUNT+1))
    fi
done

# Exit if we exhausted all retries and pods are still not ready
if [ "$PODS_READY" = false ]; then
    echo -e "\n>!< ERROR: Failed to get pods into a Ready state after ${MAX_RETRIES} attempts. >!<"
    exit 1
fi

# Copy local files to the PVC
kubectl cp ./k8s_service_files/definitions.json temp-pod:/mnt/ -n core
kubectl cp ./k8s_service_files/rabbitmq.conf temp-pod:/mnt/ -n core

# Create a tarball of the files
tar -czvf etcd_files.tar.gz -C ./etcd_launch_files/ .

# Copy the tarball to the pod
kubectl cp etcd_files.tar.gz temp-pod-orch:/mnt -n orchestrator

# Untar the files inside the pod (optional, if you want to unpack the files inside the pod)
kubectl exec -n orchestrator temp-pod-orch -- tar -xzvf /mnt/etcd_files.tar.gz -C /mnt

# Delete the temporary pod
kubectl delete -f temp-pod.yaml --wait=false

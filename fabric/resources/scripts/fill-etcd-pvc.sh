#!/bin/bash

echo "Starting etcd file transfer..."

# Create the temporary pod
kubectl apply -f temp-etcd-pod.yaml

# Wait for the pod to be in the 'Running' state
echo "Waiting for temp-etcd-pod to be Running..."
kubectl wait --for=condition=Ready pod/temp-etcd-pod --timeout=60s -n orchestrator

# Zip files
echo "Compressing local etcd files..."
tar -czvf etcd_files.tar.gz -C ./etcd_launch_files/ .

# Copy the zip into the running pod's /etcd folder
echo "Transferring files into cluster..."
kubectl cp etcd_files.tar.gz temp-etcd-pod:/etcd -n orchestrator

# Unzip the files clean up
kubectl exec -n orchestrator temp-etcd-pod -- sh -c "tar -xzvf /etcd/etcd_files.tar.gz -C /etcd && rm /etcd/etcd_files.tar.gz"

# Delete the temporary pod
echo "Cleaning up temporary pod..."
kubectl delete pod temp-etcd-pod -n orchestrator

# Clean up the local zip file (it is not needed)
rm etcd_files.tar.gz

echo "Files have been successfully transfered!"
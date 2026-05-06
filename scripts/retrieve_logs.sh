#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
source "${SCRIPT_DIR}/../dynamos.conf"

echo -e "\n=============== Started retrieving logs ===============\n"

echo -e "\nNamespace: $1"
echo -e "Pod start search: $2"
if [ -z "$3" ]; then
    echo ""
else
    echo -e "Container: $3\n"
fi

#Config
config_path="${DYNAMOS_ROOT}/configuration"
etcd_launch_files="${config_path}/etcd_launch_files"

POD=$(kubectl get pods -n $1 | grep "^$2" | sed "s/^\($2[a-zA-Z0-9-]\+\).*/\1/")
echo -e "Pod name: $POD\n"

if [ -z "$3" ]; then
    LOGS=$(kubectl logs $POD -n $1 --timestamps | sed "s/\t/ /")
else
    LOGS=$(kubectl logs $POD -c $3 -n $1 --timestamps | sed "s/\t/ /")
fi

mkdir -p $SCRIPT_DIR/logs
if [ -z "$3" ]; then
    FILE_NAME=$1-$2-logs.txt
else
    FILE_NAME=$1-$2-$3-logs.txt
fi

echo -e "\nSaving file $FILE_NAME ...\n"
echo "$LOGS" > "$SCRIPT_DIR/logs/$FILE_NAME"

echo -e "\n=============== Finished retrieving logs ===============\n"
#!/bin/bash

set -e

# Importing dynamos config
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
source "${SCRIPT_DIR}/../dynamos.conf"

CONFIG_FILE="experiments_configuration.json"
EXPERIMENTS_PATH="${DYNAMOS_ROOT}/scripts/${CONFIG_FILE}"

if [[ "$1" != "local" && "$1" != "fabric" ]]; then
    echo ">!< ERROR: First argument must be 'local' or 'fabric'"
    exit 1
fi

if [ ! -f "$EXPERIMENTS_PATH" ]; then
    echo ">!< ERROR: Cannot find $EXPERIMENTS_PATH"
    exit 1
fi

echo -e "============================================================="
echo -e "=============== Started experiments execution ==============="
echo -e "============================================================="

python -c '
import sys, json

with open(sys.argv[1]) as f:
    for run in json.load(f):
        
        exp   = run["name"]
        reps  = run["repetitions"]
        iters = run["iterations"]
        policy_aware = "true" if run["policy_aware"] else "false"

        print(f"{exp} {reps} {iters} {policy_aware}")
' "$EXPERIMENTS_PATH" | tr -d '\r' | while read -r EXP_NAME REPS ITERS PA; do

    echo -e "=============== Starting experiment ==============="
    echo -e " Name: $EXP_NAME | Repetitions: $REPS"
    echo -e " Iterations: $ITERS | Policy-aware: $PA"
    echo -e "===================================================\n"

    PY_FLAGS="-i $ITERS -op $EXP_NAME"

    if [ "$1" == "fabric" ]; then
        PY_FLAGS="$PY_FLAGS -f"
    fi

    if [ "$PA" == "true" ]; then
        PY_FLAGS="$PY_FLAGS -pa"
    fi

    echo $PY_FLAGS

    ./scripts/run_experiment.sh "$1" "$REPS" $PY_FLAGS

    echo -e "=============== Finished experiment ==============="

    sleep 5

done

echo -e "\n=============================================================="
echo -e "=============== Finished experiments execution ==============="
echo -e "=============================================================="
exit 0
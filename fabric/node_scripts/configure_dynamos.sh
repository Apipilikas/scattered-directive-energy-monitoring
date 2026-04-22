#!/bin/bash

{
# Parse the agents and thirdparties from the CLI arguments
IFS=',' read -r -a agents <<< "$1"
IFS=',' read -r -a thirdparties <<< "$2"

echo "this is $3"

# cd scattered-directive-energy-monitoring

echo "Adding agents..."
for agent in "${agents[@]}"
do
    echo "- agent '$agent'"
    ./scripts/add_agent.sh $agent $3
done

echo ""
echo "Adding third parties..."
for thirdparty in "${thirdparties[@]}"
do
    echo "- third party '$thirdparty'"
    ./scripts/add_thirdparty.sh $thirdparty $3
done
}
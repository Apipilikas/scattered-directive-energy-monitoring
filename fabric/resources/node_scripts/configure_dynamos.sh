#!/bin/bash

{
# Parse the agents and thirdparties from the CLI arguments
IFS=',' read -r -a agents <<< "$1"
IFS=',' read -r -a thirdparties <<< "$2"

cd scattered-directive-energy-monitoring

echo "Adding agents..."
for agent in "${agents[@]}"
do
    echo "- agent '$agent'"
    sed -i 's/\r$//' add_agent.sh
    chmod +x add_agent.sh
    ./add_agent.sh $agent > /dev/null
done

echo ""
echo "Adding third parties..."
for thirdparty in "${thirdparties[@]}"
do
    echo "- third party '$thirdparty'"
    sed -i 's/\r$//' add_thirdparty.sh
    chmod +x add_thirdparty.sh
    ./add_thirdparty.sh $thirdparty > /dev/null
done
}
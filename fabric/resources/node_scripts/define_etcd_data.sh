#!/bin/bash

{
BRANCH_NAME=fed-encrypt-dynamic
# BRANCH_NAME=baseline


echo "Cleaning scattered-directive-energy-monitoring folder..."
sudo rm -rf ~/scattered-directive-energy-monitoring

echo "Cloning  branch $BRANCH_NAME"
git clone -b $BRANCH_NAME https://github.com/Apipilikas/scattered-directive-energy-monitoring.git

sudo mkdir -p /mnt/etcd-data
sudo cp ~/scattered-directive-energy-monitoring/configuration/etcd_launch_files/*.json /mnt/etcd-data
sudo chmod -R 777 /mnt/etcd-data
}

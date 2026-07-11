#!/bin/bash
set -e 

# Helper to create a local bin folder for our Windows executables
mkdir -p $HOME/bin
function addPathExport () {
  echo -e "export PATH=$1" >> $HOME/.bashrc
}
# Ensure our local bin is in the path for this session
export PATH=$HOME/bin:$PATH
addPathExport "\$PATH:$HOME/bin"

echo "=============== Started installing JAEGER Tracing (Local) ==============="

echo "> 1. Clearing namespaces..."

kubectl delete ns jaeger-system linkerd-jaeger linkerd --ignore-not-found || true
kubectl delete clusterrole linkerd-linkerd-identity linkerd-linkerd-destination linkerd-policy linkerd-heartbeat linkerd-linkerd-proxy-injector --ignore-not-found || true
kubectl delete clusterrolebinding linkerd-linkerd-identity linkerd-linkerd-destination linkerd-destination-policy linkerd-heartbeat linkerd-linkerd-proxy-injector --ignore-not-found || true
kubectl delete validatingwebhookconfiguration linkerd-sp-validator-webhook-config linkerd-policy-validator-webhook-config --ignore-not-found || true
kubectl delete mutatingwebhookconfiguration linkerd-proxy-injector-webhook-config --ignore-not-found || true

echo "> 2. Installing Helm charts..."

HELM_VERSION="v3.14.0"
curl -fsSL "https://get.helm.sh/helm-${HELM_VERSION}-windows-amd64.zip" -o helm.zip
unzip -q helm.zip
mv windows-amd64/helm.exe $HOME/bin/helm.exe
rm -rf windows-amd64 helm.zip
echo "Helm installed locally!"

echo "> 3. Installing legacy linkerd CLI..."

curl --proto '=https' --tlsv1.2 -sSfL https://run.linkerd.io/install | LINKERD2_VERSION=stable-2.14.10 sh
export PATH=$HOME/.linkerd2/bin:$PATH
addPathExport "\$PATH:$HOME/.linkerd2/bin"

echo "> 4. Installing gateway api..."

kubectl apply -f https://github.com/kubernetes-sigs/gateway-api/releases/download/v0.8.0/standard-install.yaml

echo "> 5. Installing linkerd control plane..."

linkerd check --pre
linkerd install --crds | kubectl apply -f -
linkerd install --set proxyInit.runAsRoot=true | kubectl apply -f -
linkerd check

echo "> 6. Installing legacy jaeger extension..."

helm repo add linkerd https://helm.linkerd.io/stable
helm repo update

helm install linkerd-jaeger linkerd/linkerd-jaeger \
  --namespace linkerd-jaeger \
  --create-namespace \
  --wait

echo "=============== Finished installing JAGER ==============="
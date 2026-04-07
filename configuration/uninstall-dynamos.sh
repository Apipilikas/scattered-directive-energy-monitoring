echo "Uninstalling namespaces..."
helm uninstall nginx namespaces core orchestrator agents thirdparties api-gateway prometheus --ignore-not-found

echo "Uninstalling nginx..."
helm uninstall nginx --ignore-not-found
helm uninstall nginx -n ingress
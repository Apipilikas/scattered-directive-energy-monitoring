## Install the Control Plane
```
PS C:\Users\apipi> linkerd check

kubernetes-api

--------------

√ can initialize the client

√ can query the Kubernetes API



kubernetes-version

------------------

√ is running the minimum Kubernetes API version



linkerd-existence

-----------------

× 'linkerd-config' config map exists

    configmaps "linkerd-config" not found

    see https://linkerd.io/2/checks/#l5d-existence-linkerd-config for hints



Status check results are ×
```

```
linkerd install --crds > crds.yaml
kubectl apply -f crds.yaml

linkerd install > linkerd.yaml
kubectl apply -f linkerd.yaml

linkerd check

```

# Prometheus

## Error while initializing prometheus
```
M1    node-exporter  ●  quay.io/prometheus/node-exporter:v1.11.0  false  CrashLoopBackOff        77

to try resolving symlinks in path "/var/log/pods/default_prometheus-prometheus-node-exporter-lc9jf_d ││ 82ddaae-cf2b-491d-a602-e45553a8a52e/node-exporter/77.log": lstat /var/log/pods/default_prometheus-pr ││ ometheus-node-exporter-lc9jf_d82ddaae-cf2b-491d-a602-e45553a8a52e/node-exporter/77.log: no such file ││  or directorystream closed: EOF for default/prometheus-prometheus-node-exporter-lc9jf (node-exporter ││ )

kubectl logs -l app.kubernetes.io/name=prometheus-node-exporter -n default --previous | tail -n 15

failed to try resolving symlinks in path "/var/log/pods/default_prometheus-prometheus-node-exporter-lc9jf_d82ddaae-cf2b-491d-a602-e45553a8a52e/node-exporter/77.log": lstat /var/log/pods/default_prometheus-prometheus-node-exporter-lc9jf_d82ddaae-cf2b-491d-a602-e45553a8a52e/node-exporter/77.log: no such file or directorya
```

I had to add the following in charts/monitoring/prometheus-values.yaml:
```yaml
prometheus-node-exporter:
  hostRootFsMount:
    enabled: false
``` 

# Grafana
## Deployment issue
First of all, we provided the following helm chart installation:
```
helm repo add grafana-community https://grafana-community.github.io/helm-charts
helm repo update
helm upgrade -i -f "${monitoring_chart}/grafana-values.yaml" grafana  grafana-community/grafana
```

When we deployed it, we got the following error:
```
404 Not Found

nginx/1.25.1
```

To fix this, we had to either port-forwarding or setting up the NGINX Front Gate. For the latter option, we had to configure the grafana helm charts as:
```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: grafana-manual-ingress
  namespace: default
  annotations:
    nginx.ingress.kubernetes.io/service-upstream: "true"
spec:
  ingressClassName: nginx
  rules:
  - host: grafana.local
    http:
      paths:
      - pathType: Prefix
        path: "/"
        backend:
          service:
            name: grafana
            port:
              number: 80
```
Add the following to C:\Windows\System32\drivers\etc\hosts:
```
127.0.0.1 grafana.local
```

## Dashboards displayed: No data
There was a disconnect in the pipeline with Prometheus. The fix was to add the following in grafana-values.yaml:
```yaml
datasources:
  datasources.yaml:
    apiVersion: 1
    datasources:
    - name: prometheus
      type: prometheus
      access: proxy
      orgId: 1
      url: http://prometheus-server.default.svc.cluster.local:80
      isDefault: true
      jsonData:
        timeInterval: "5s"
      editable: true
```
## f
```
502 Bad Gateway
nginx/1.25.1
```



# Kepler
## Installation failed
```
 time=2026-04-09T15:26:41.815Z level=ERROR source=cmd/kepler/main.go:58 msg="failed to initialize ser ││ vices" error="failed to initialize service rapl: failed to read rapl zones: unable to read class/pow ││ ercap: open /host/sys/class/powercap: no such file or directory" 
```

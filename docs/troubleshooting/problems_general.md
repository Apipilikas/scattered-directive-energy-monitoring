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
```
time=2026-04-13T13:35:49.112Z level=DEBUG source=cmd/kepler/main.go:129 msg="Creating all services"     time=2026-04-13T13:35:49.113Z level=INFO source=cmd/kepler/main.go:356 msg="GPU feature disabled"       time=2026-04-13T13:35:49.113Z level=INFO source=cmd/kepler/main.go:248 msg="using kubelet pod informer" pollInterval=15s                                                                                        time=2026-04-13T13:35:49.113Z level=DEBUG source=cmd/kepler/main.go:267 msg="Creating Prometheus exporter"                                                                                                      time=2026-04-13T13:35:49.113Z level=INFO source=internal/service/initializer.go:31 msg="Initializing service" service=kubeletPodInformer                                                                        W0413 13:35:49.113851    3474 client_config.go:659] Neither --kubeconfig nor --master was specified.  Using the inClusterConfig.  This might not work.                                                          time=2026-04-13T13:35:49.124Z level=DEBUG source=k8s/pod/kubelet.go:160 msg="discovered kubelet endpoint" service=kubeletPodInformer host=192.168.65.3 port=10250                                               time=2026-04-13T13:35:49.149Z level=DEBUG source=k8s/pod/kubelet.go:245 msg="refreshed pod cache from kubelet" service=kubeletPodInformer podCount=16 containerCount=30                                         time=2026-04-13T13:35:49.149Z level=INFO source=k8s/pod/kubelet.go:113 msg="kubelet pod informer initialized" service=kubeletPodInformer nodeName=docker-desktop kubeletHost=192.168.65.3 kubeletPort=10250 pollInterval=15s                                                                                            time=2026-04-13T13:35:49.149Z level=INFO source=internal/service/initializer.go:31 msg="Initializing service" service=resource-informer                                                                         time=2026-04-13T13:35:49.150Z level=INFO source=internal/resource/informer.go:162 msg="Resource informer initialized successfully" service=resource-informer                                                    time=2026-04-13T13:35:49.150Z level=INFO source=internal/service/initializer.go:31 msg="Initializing service" service=rapl                                                                                      time=2026-04-13T13:35:49.150Z level=INFO source=internal/service/initializer.go:43 msg="Shutting down initialized services"                                                                                     time=2026-04-13T13:35:49.150Z level=DEBUG source=internal/service/initializer.go:47 msg="skipping service shutdown" service=kubeletPodInformer reason="service does not implement Shutdowner"                   time=2026-04-13T13:35:49.150Z level=DEBUG source=internal/service/initializer.go:47 msg="skipping service shutdown" service=resource-informer reason="service does not implement Shutdowner"                    time=2026-04-13T13:35:49.150Z level=ERROR source=cmd/kepler/main.go:58 msg="failed to initialize services" error="failed to initialize service rapl: failed to read rapl zones: unable to read class/powercap: open /host/sys/class/powercap: no such file or directory"
```

powercap (Intel RAPL) for managing CPU power limits is generally not supported in WSL because the required /sys/class/powercap or /sys/devices/virtual/powercap directories are not exposed by the WSL kernel. Consequently, tools relying on these files (e.g., powercap-set, PowerJoular) fail to access RAPL energy data.

https://github.com/sustainable-computing-io/kepler/issues/2262
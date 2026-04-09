## temp-pod Running problem
```
Setting up paths...

definitions_example.json copied over definitions.json to ensure a clean file

Generating RabbitMQ password...

Replacing tokens...

Installing namespaces...

Release "namespaces" has been upgraded. Happy Helming!

NAME: namespaces

LAST DEPLOYED: Thu Apr  2 18:08:20 2026

NAMESPACE: default

STATUS: deployed

REVISION: 2

DESCRIPTION: Upgrade complete

TEST SUITE: None

Preparing PVC

pod/temp-pod created

pod/temp-pod-orch created

Waiting for temp-pod to be Running...
```

```
# temp-pod.yaml
apiVersion: v1
kind: Pod
metadata:
  name: temp-pod
  namespace: core
  annotations:
    "linkerd.io/inject": "disabled"
spec:
  nodeSelector:
    kubernetes.io/hostname: dynamos
  nodeName: dynamos
  containers:
  - name: temp-container
    image: busybox
    command: [ "sh", "-c", "--" ]
    args: [ "while true; do sleep 5; done;" ]
    volumeMounts:
    - name: pvc-to-fill
      mountPath: /mnt
  volumes:
  - name: pvc-to-fill
    persistentVolumeClaim:
      claimName: rabbit-pvc

---

apiVersion: v1
kind: Pod
metadata:
  name: temp-pod-orch
  namespace: orchestrator
  annotations:
    "linkerd.io/inject": "disabled"
spec:
  nodeSelector:
    kubernetes.io/hostname: dynamos
  nodeName: dynamos
  containers:
  - name: temp-container
    image: busybox
    command: [ "sh", "-c", "--" ]
    args: [ "while true; do sleep 5; done;" ]
    volumeMounts:
    - name: pvc-to-fill
      mountPath: /mnt
  volumes:
  - name: pvc-to-fill
    persistentVolumeClaim:
      claimName: etcd-pvc
```

I have to remove 
```
  nodeSelector:
    kubernetes.io/hostname: dynamos
  nodeName: dynamos
```
Sometimes, the first time it doesn't manage to get Running and stucks to Pending. In this case, we run the uninstall-dynamos script and then re-run the dynamos-configuration.

## Edit the Windows hostfile
We need to map our local machine to the Kubernetes cluster so the test URL works. I had to add this to C:\Windows\System32\drivers\etc\.

```
127.0.0.1 api-gateway.api-gateway.svc.cluster.local
```

## Other issue
```
  /var/run/secrets/kubernetes.io/serviceaccount from kube-api-access-kmmtt (ro)
Conditions:
  Type           Status
  PodScheduled   False
Volumes:
  pvc-to-fill:
    Type:       PersistentVolumeClaim (a reference to a PersistentVolumeClaim in the same namespace)
    ClaimName:  rabbit-pvc
    ReadOnly:   false
  kube-api-access-kmmtt:
    Type:                    Projected (a volume that contains injected data from multiple sources)
    TokenExpirationSeconds:  3607
    ConfigMapName:           kube-root-ca.crt
    Optional:                false
    DownwardAPI:             true
QoS Class:                   BestEffort
Node-Selectors:              <none>
Tolerations:                 node.kubernetes.io/not-ready:NoExecute op=Exists for 300s
                             node.kubernetes.io/unreachable:NoExecute op=Exists for 300s
Events:
  Type     Reason            Age                 From               Message
  ----     ------            ----                ----               -------
  Warning  FailedScheduling  13s (x18 over 43m)  default-scheduler  0/1 nodes are available: pod has unbound immediate PersistentVolumeClaims. not found
  Warning  FailedScheduling  13s (x4 over 13s)   default-scheduler  0/1 nodes are available: 1 node(s) didn't match PersistentVolume's node affinity. no new claims to deallocate, preemption: 0/1 nodes are available: 1 Preemption is not helpful for scheduling.
```

```
apipi@LAPTOP-CJQE9G38 MINGW64 ~/Documents/UNI/master/MP/scattered-directive-energy-monitoring (main)
$ grep -rn "dynamos" charts/ configuration/
charts/agents/templates/workerX.yaml:33:#           value: dynamos1
charts/api-gateway/values.yaml:5:dockerArtifactAccount: "dynamos1"
charts/api-gateway/values.yaml:6:node: dynamos
charts/core/prometheus-values.yaml:17:      kubernetes.io/hostname: dynamos
charts/core/prometheus-values.yaml:57:    kubernetes.io/hostname: dynamos
charts/core/prometheus-values.yaml:77:      kubernetes.io/hostname: dynamos
charts/core/prometheus-values.yaml:82:    kubernetes.io/hostname: dynamos
charts/core/templates/etcd.yaml:20:  # Use the dynamos-core node for this
charts/core/templates/rabbitmq-services.yaml:41:  # Use the dynamos-core node for this
charts/core/templates/rabbitmq-services.yaml:63:  # Use the dynamos-core node for this
charts/core/values.yaml:27:node: dynamos
charts/namespaces/templates/etcd-pvc.yaml:16:  # Use the dynamos-core node for this
charts/namespaces/values.yaml:4:node: dynamos
charts/orchestrator/templates/policyEnforcer.yaml:21:        image: dynamos1/policy-enforcer:{{ .Values.branchNameTag }}
charts/orchestrator/values.yaml:7:node: dynamos
configuration/temp-pod.yaml:11:    kubernetes.io/hostname: dynamos
configuration/temp-pod.yaml:12:  nodeName: dynamos
configuration/temp-pod.yaml:37:    kubernetes.io/hostname: dynamos
configuration/temp-pod.yaml:38:  nodeName: dynamos
```

```
Namespace: api-gateway
etcdDns: etcd-headless.core.svc.cluster.local
tracingEndpoint: collector.linkerd-jaeger:55678
branchNameTag: "latest"
dockerArtifactAccount: "dynamos1"
node: dynamos
```

Remove node: dynamos

## Agreements and etcd

```
panic: runtime error: invalid memory address or nil pointer dereference                              ││ [signal SIGSEGV: segmentation violation code=0x1 addr=0x28 pc=0xab63d5]                              ││                                                                                                      ││ goroutine 116 [running]:                                                                             ││ main.handleIncomingMessages({0xd80670, 0x134ebc0}, 0xc00041e960)                                     ││     /app/cmd/api-gateway/consume.go:31 +0x455                                                        ││ github.com/Jorrit05/DYNAMOS/pkg/lib.startConsuming({0x0?, 0x0?}, {0xd87ff8, 0xc0004115a0}, {0xc00020 ││     /app/pkg/lib/consume.go:53 +0x408                                                                ││ github.com/Jorrit05/DYNAMOS/pkg/lib.StartConsumingWithRetry({0xc70a21, 0xb}, {0xd87ff8, 0xc0004115a0 ││     /app/pkg/lib/consume.go:17 +0x1d4                                                                ││ main.main.func1()                                                                                    ││     /app/cmd/api-gateway/main.go:64 +0xba                                                            ││ created by main.main in goroutine 1                                                                  ││     /app/cmd/api-gateway/main.go:63 +0x3a7                                                           ││ total 22484                                                                                          ││ drwxr-xr-x    1 root     root          4096 Oct 15 14:01 .                                           ││ drwxr-xr-x    1 root     root          4096 Apr  4 18:46 ..                                          ││ -rwxr-xr-x    1 root     root      23013279 Oct 15 14:01 api-gateway                                 ││ stream closed: EOF for api-gateway/api-gateway-85799dbdb4-dpj96 (api-gateway) 
```

The agreements didn't transfer correctly to the pod.

TODO: It would be nice to resolve the issue above and provide better error explanation.
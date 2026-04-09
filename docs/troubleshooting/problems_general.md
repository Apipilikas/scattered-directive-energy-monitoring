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
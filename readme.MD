<div align="right">
  <a href="https://github.com/Apipilikas/scattered-directive-energy-monitoring/tree/main">
    <strong>🔙 Return to <code>main</code> branch</strong>
  </a>
</div>

<div align="center">

# Scattered Directive Energy Monitoring
### Branch: `fed-bcd`

*This branch contains the Fed-BCD implementation.*

</div>

---

## Overview

Here we provide a brief overview of the Fed-BCD implementation. More details can be found in thesis document.

### FedBCD Architecture
FedBCD targets feature-partitioned FL scenarios, where multiple parties collaborate to train a shared model without exposing their raw data. The vanilla stochastic gradient descent algorithm requires constant communication of intermediate results at the end of every iteration, creating communication congestion, especially when the number of participants is very large. To resolve this, FedBCD proposes that each party performs Q consecutive local gradient updates before synchronizing their results with the party K.

### Api-gateway Modifications
First of all, two new parameters were introduced on the `data_request` payload of `requestApproval` request: `communication_frequency` and `sample_batch_size`. The api-gateway acts as the main orchestrator of the VFL pipeline, serving as a proxy between the clients and the server to ensure no direct peer-to-peer communication. 

The FedBCD execution pipeline consists of the following steps:

1. **Mini-batch sampling :** The api-gateway sends a `vflSampleBatchRequest` request to the server to randomly select a mini-batch sample for the current iteration. The server returns only an array of the sampled indexes, eliminating possible raw data exposure.
2. **Local forward pass :** The api-gateway sends a `vflTrainRequest` request to each client in parallel based on the provided indexes to calculate their local intermediate embeddings.
3. **Loss function derivatives :** The api-gateway collects the received embeddings into a unified strictly ordered list based on a predetermined client list order and transmits the data via a `vflAggregateRequest` request to the server to compute the global loss. 
4. **Local gradient descent :** The api-gateway sends a `vflGradientDescentRequest` request containing the respective gradients to each client. Each client performs Q local backward propagation based on the `staled` gradients.
5. **Local update :** Finally, the api-gateway, in parallel with clients, dispatches a `vflLocalUpdateRequest` to the server to perform Q-1 forward passes based on the intermediate `staled` client embeddings.

### Training Services Modifications
In Scattered Directive, VFL training process is abstracted into two distinct training services: `vfl-train` and `vfl-train-model`.

In `vfl-train`, a dedicated function was implemented to extract the data based on the batch sample indexes. Additionally, local gradient descent is executed Q consecutive times within an iteration loop. 

In `vfl-train-model`, two additional functions were implemented. The first is responsible for the generation of the mini-batch. Furthermore, a local update routine was implemented to simply perform loss function over Q-1 times.
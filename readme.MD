<div align="right">
  <a href="https://github.com/Apipilikas/scattered-directive-energy-monitoring/tree/main">
    <strong>🔙 Return to <code>main</code> branch</strong>
  </a>
</div>

<div align="center">

# Scattered Directive Energy Monitoring
### Branch: `semi-overlap-fed-bcd`

*This branch contains the Overlap-Fed-BCD implementation.*

</div>

---

## The Overlap-FedAvg Framework
The Overlap-FedAvg methodology relies on minimizing clients idle time by breaking the traditional computation-communication sequence. To achieve this, each client and the server initialize two main processes: (1) a local model training process denoted as $P_{pro}$ and (2) communicating process denoted as $P_{comm}$. In short, in vanilla FedAvg, global weights $w_{t+1}$ are updated using current weights $w_{t}$ whereas in Overlap-FedAvg the gradients are updated at the older state $w_{t-1}$, leading to a phenomenon known as gradient staleness.

## Api-gateway Modifications
To achieve this asynchronous setup in api-gateway, Go `Channel` were leveraged to create an event-driven chain. Four main channels were created:

* **`sampleChan` :** Receives a new `TrainingRoundData` instance as soon as batch indexes are fetched from the server.
* **`embeddingsChan` :** Receives an updated `TrainingRoundData`, enhanced with the embeddings as soon as they are gathered from all the clients.
* **`gradientsChan` :** Receives an updated `TrainingRoundData`, enhanced with the gradients as soon as they are computed and returned from the server.
* **`vflCompleteChan` :** Signals the main pipeline that the VFL training has finished.

It is worth noticing that this architecture enables multiple training cycles to exist simultaneously at different stages of the VFL pipeline. However, each channel's buffer capacity is restricted to one to prevent any uncontrolled, out-of-order execution such as applying gradients from future iterations without handling previous ones.

## Training Services Modifications
The first step in this transition involves shifting from a synchronous service architecture to an asynchronous one. To achieve this, multi-threading was integrated into the training services, allowing each individual request to be handled independently. 

However, because both `vfl-train` and `vfl-train-model` services utilize `PyTorch` to train their local and global models respectively, the simultaneous execution of both forward and backward propagation is unsupported and creates runtime errors. Thus, different techniques were utilized, such as thread locks, to queue incoming requests until the completion of active training.

## References

- **Y. Liu et al.**, "FedBCD: A Communication-Efficient Collaborative Learning Framework for Distributed Features," in IEEE Transactions on Signal Processing, vol. 70, pp. 4277-4290, 2022, doi: 10.1109/TSP.2022.3198176. keywords: {Stochastic processes;Data models;Collaborative work;Signal processing algorithms;Distributed databases;Security;Data privacy;Federated learning;data privacy;federated stochastic block coordinate descent;cross-silo federated learning;distributed features}
[![DOI:10.1109/TSP.2022.3198176](https://zenodo.org/badge/DOI/10.1109/TSP.2022.3198176.svg)](https://doi.org/10.1109/TSP.2022.3198176)

- **Y. Zhou, Q. Ye and J. Lv**, "Communication-Efficient Federated Learning With Compensated Overlap-FedAvg," in IEEE Transactions on Parallel and Distributed Systems, vol. 33, no. 1, pp. 192-205, 1 Jan. 2022, doi: 10.1109/TPDS.2021.3090331.
keywords: {Collaborative work;Data models;Training;Servers;Computational modeling;Convergence;Deep learning;Distributed computing;federated learning;overlap;efficient communication},
[![DOI:10.1109/TPDS.2021.3090331](https://zenodo.org/badge/DOI/10.1109/TPDS.2021.3090331.svg)](10.1109/TPDS.2021.3090331)
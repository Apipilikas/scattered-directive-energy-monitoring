<div align="right">
  <a href="https://github.com/Apipilikas/scattered-directive-energy-monitoring/tree/main">
    <strong>🔙 Return to <code>main</code> branch</strong>
  </a>
</div>

<div align="center">

# Scattered Directive Energy Monitoring
### Branch: `baseline`

*This branch contains the basic configuration to deploy the pipeline, execute unsupervised experiments, analyze data, and generate plots.*

</div>

---

## Deployment 
To deploy Scattered Directive, run the following command:
```
./configuration/configure-dynamos.sh <mode>
```

where `<mode>` can be either local to deploy Scattered Directive locally or fabric for the FABRIC configuration.

## Experiments

All the executed experiments can be found in [`energy-monitoring-pipeline/experiments`](https://github.com/Apipilikas/scattered-directive-energy-monitoring/tree/baseline/energy-monitoring-pipeline/experiments) directory. To keep workspace organized, results are seperated into two distinct folders:
* [`local`](https://github.com/Apipilikas/scattered-directive-energy-monitoring/tree/baseline/energy-monitoring-pipeline/experiments/local) : contains results from local environment
* [`fabric`](https://github.com/Apipilikas/scattered-directive-energy-monitoring/tree/baseline/energy-monitoring-pipeline/experiments/fabric) : contains results from FABRIC environment

## Data Analysis

To support Data Analysis, a pipeline has been implemented that integrates both Anomaly Detection (AD) algorithm and Root Cause Analysis (RCA). You can run these steps manually or use the condensed pipeline script:

### Option A : Manual execution

* **Retrieve data** : Run the `collect_metrics.py` script to collect the metrics. Data are stored in a csv in `energy-monitoring-pipeline/output` directory.
* **Analyze data** : Run the `analyze_metrics.py -ad -rca` script to detect the anomalies and the underlying root causes. Relevant flag parameters `-ad` and `-rca` can be passed to perform anomaly detection and root cause analysis respectively. For the latter, a proper baseline dataset should be provided under the `baseline_data_metrics.csv` name.

### Option B : Automated pipeline execution

The entire metrics collection and data analysis can be run by using the following command:

```
execute_pipeline.py -cm -ad- rca
```

Relevant flag parameters `-cm`, `-ad` and `-rca` indicate collect metrics, anomaly detection and root cause analysis routine.

## Retrieve Logs

Logs can be retrieved by running the following command:

```
./scripts/retrieve_logs.sh <namespace> <pod-search> <container>
```

The parameters that should be provided are the following:
*   `namespace` : The Kubernetes namespace where the pod is located.
*   `pod-search` : The starting string/prefix of the pod's name.
*   `container` : The specific container name within the pod.

## Execute Experiments Pipeline

To execute experiments unsupervised, run the following command:

```
./scripts/execute_experiments.sh <mode>
```

where `<mode>` can be either local to deploy Scattered Directive locally or fabric for the FABRIC configuration. 

To configure the experiments, modify the `experiments_configuration.json` file. You can configure the experiment name, number of iterations, repetitions, and whether policy-aware changes are applied.

> [!WARNING] We strongly recommend keeping the iterations count to 10 or fewer when running in the local environment, as the Scattered Directive can become highly unstable locally.

An example of the file is the following:

```json
[
    {
        "name": "baseline",
        "iterations": 10,
        "repetitions": 2,
        "policy_aware": false
    },
    {
        "name": "pa_baseline",
        "iterations": 10,
        "repetitions": 2,
        "policy_aware": true
    }
]
```
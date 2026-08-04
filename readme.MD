<div align="right">
  <a href="https://github.com/Apipilikas/scattered-directive-energy-monitoring/tree/main">
    <strong>🔙 Return to <code>main</code> branch</strong>
  </a>
</div>

<div align="center">

# Scattered Directive Energy Monitoring
### Branch: `baseline-with-event-driven-verification`

*This branch contains the event-driven policy update verification implementation.*

</div>

---

## Overview

Here we provide a brief overview of the event-driven implementation. More details can be found in thesis document.

## Orchestrator API Modifications
To properly support policy updates, a new `DELETE` operation was introduced. Thus, the orchestrator API supports the following endpoints:

| Method | API endpoint | Description |
| :--- | :--- | :--- |
| **GET** | `/api/v1/policyEnforcer/agreements/` | Get all agreements |
| **GET** | `/api/v1/policyEnforcer/agreements/<data_steward_name>` | Get specific data steward's agreement |
| **POST** | `/api/v1/policyEnforcer` | Add new / update existing agreement(s) |
| **DELETE** | `/api/v1/policyEnforcer/agreements/<data_steward_name>` | Delete agreement *(Newly Added)* |

## System Architecture & Workflows
The architecture was shifted from a poll-driven, hard-coded design to an event-driven pipeline. This operates in two main phases:

### Orchestrator & Policy Enforcer Pipeline
1. **API Request:** A user triggers an add, update, or delete agreement request.
2. **Job Evaluation:** The Orchestrator updates `etcd`, retrieves associated active jobs, and deletes or re-evaluates them based on the new policy.
3. **Validation:** The Orchestrator forwards a `policyUpdate` request to the Policy Enforcer, which verifies the agreements and sends the validated data back.
4. **Propagation:** The Orchestrator updates the active job records and pushes the changes downstream to the API-gateway.

### API-Gateway Pipeline
> [!NOTE] 
> Client storage was changed from an unordered map to an ordered ClientData list to ensure sequential data transmission and prevent accuracy spikes during training as standard go map structures do not preserve order.

1. **Api-gateway notified** : the api-gateway sidecar receives a `policyUpdate` incoming message from the orchestrator.
2. **Retrieval of providers' available data** : The api-gateway fetches all the providers' available data stored in the `etcd`.
3. **Extraction of valid data providers** : The api-gateway extracts the valid data providers information from the incoming `policyUpdate` request.
4. **Update current clients list** : The clients list is updated to reflect the newly available clients. Additionally, in our configuration, the `server` is excluded as it functions seperately from the clients as the aggregator.

## Future Work

Proper JSON payload can be supported to provide a list of policy updates. For example:

```json
[
    {
        "action" : "policy_removal",
        "cycle" : 2,
        "data" : {
            "agreement_name" : "clientone"
        }
    },
    {
        "action" : "policy_introduction",
        "cycle" : 10,
        "data" : {
            "name": "clientthree"
            ,
            "relations": {
                "evangelos.pipilikas@student.uva.nl": {
                    "ID": "GUID",
                    "requestTypes": [
                        "vflTrainRequest"
                    ],
                    "dataSets": null,
                    "allowedArchetypes": [
                        "computeToData"
                    ],
                    "allowedComputeProviders": [
                        "clientthree"
                    ]
                }
            },
            "computeProviders": [
                "clientthree"
            ],
            "archetypes": [
                "computeToData"
            ]
    }
    }
]
```

Now, policy changes are handled hard-coded. 
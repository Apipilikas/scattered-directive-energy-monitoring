# Scattered Directive Energy Monitoring Pipeline

The "Green policy-aware Vertical Federated Learning in distributed environment" thesis aimed to integrate an energy monitoring pipeline into the Scattered Directive and implement different mitigation strategies to minimize the environmental footprint. 

## Scattered Directive

[Scattered Directive](https://github.com/Javernus/Scattered-Directive) (often abbreviated to S-Drive) is a distributed infrastructure running a digital data
marketplace platform that implements the VFL workflow to facilitate the dynamic enforcement of policies. It basically  runs a VFL framework on top of the [DYNAMOS](https://github.com/Jorrit05/DYNAMOS) policy-aware middleware
to manage data sharing in a governed environment.

## Codebase explanation

The codebase is designed as follows:

| Branch | Description |
| :--- | :--- |
| **baseline** | This branch contains the basic Scattered Directive configuration to deploy it on local or FABRIC environment. Additionally, it serves as the codebase for experiments (has the whole experiment pipeline), root cause analysis, plot generation and data analysis (significance, validity testing, correlation). |
| **local & fabric** | These branches contain the deployment files on the local and FABRIC environments respectively. They were primarily utilized for initial setups. These branches have been merged into the baseline branch, which contains a unified Scattered Directive installation script. |
|**baseline-with-event-driven-verification**|This branch contains the event-driven policy update verification implementation.|
|**fed-bcd**|This branch contains the Fed-BCD implementation.|
|**semi-overlap-fed-bcd**|This branch contains the asynchronous Fed-BCD implementation.|
| **fed-encrypt** | This branch contains an initial version of MS4 in which policy changes triggered the regeneration of SIFE and MIFE keys. This approach proved to be highly computational inefficient for the system, as additional execution cycles would increase both energy consumption and execution time. Later on, the enhanced version `fed-encrypt-dynamic` eliminates this step by utilizing the masking mechanism. |
|**fed-encrypt-dynamic**|This branch contain the Fed-Ecrypt implementation.|
| **overlap-fed-bcd** | This branch explores an experimental alteration of MS3 that attempts to process gradients and embeddings based on which arrives first. This introduced severe gradient staleness. |

Further information can be found on each branch.

## Installation

The entire pipeline is automated. Move to `baseline` branch. Run:

```
./configuration/configure-dynamos.sh <mode>
```

In mode, you can put either `local` to deploy Scattered Directive locally or `fabric` for the FABRIC configuration.

## Setup in FABRIC

To deploy Scattered Directive to FABRIC, follow these steps:

1. Move to the `baseline` branch
2. Upload all the `fabric\notebooks` directory to the jupyter Lab.
3. Run the script `install_dynamos.ipynb` to configure the whole cluster.

More information about auxilary scripts can be found in `baseline` branch.
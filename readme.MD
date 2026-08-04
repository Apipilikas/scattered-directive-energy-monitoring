<div align="right">
  <a href="https://github.com/Apipilikas/scattered-directive-energy-monitoring/tree/main">
    <strong>🔙 Return to <code>main</code> branch</strong>
  </a>
</div>

<div align="center">

# Scattered Directive Energy Monitoring
### Branch: `fabric`

*This branch contains the initial deployment configurations for FABRIC environment. It has been merged into the [`baseline`](https://github.com/Apipilikas/scattered-directive-energy-monitoring/tree/baseline) branch.*

</div>

---

## Configuration Files

The primary structural differences between the `FABRIC` deployment and other environments (such as local) are in the following key directories:

* **[`charts/`](https://github.com/Apipilikas/scattered-directive-energy-monitoring/tree/fabric/charts)** : contains the Helm charts tuned specifically for FABRIC Kubernetes clusters.
* **[`configuration/`](https://github.com/Apipilikas/scattered-directive-energy-monitoring/tree/fabric/configuration)** : holds the environment setup scripts and core configuration required to deploy Scattered Directive in FABRIC testbed.
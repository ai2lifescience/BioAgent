# BacARG deployment

Copy the BacARG directory by itself. Create an environment from `environment.yml`, install the project, prepare the database separately, and configure paths with environment variables or a deployment YAML. Do not edit source code for infrastructure paths.

Run `bacarg doctor --config <deployment-config>` before the first job. Then run a small synthetic or known control with a new output directory and inspect `status.json`, `manifest.json`, logs, raw ABRicate results, and final tables. Database preparation is an administrative operation and is never part of a normal job.

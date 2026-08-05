# BacVF deployment

Copy this directory alone, create an environment from `environment.yml`, install the project, prepare VFDB core separately, and configure paths through environment variables or YAML. Run `bacvf doctor --config <deployment-config>` before the first job.

Validate a small known or synthetic control in a new output directory. Inspect `status.json`, the command manifest, raw ABRicate output, retained Prokka files, final tables, and separate logs. Database creation is an explicit administrative step and is never triggered by a sample run.

# De novo Assembly WDL Pipeline Environment

## Host requirements

The BioAgent host requires:

- Python 3.9 or newer and the repository dependencies.
- A reachable Cromwell Server. The default URL is `http://127.0.0.1:8000`;
  set `CROMWELL_URL` to override it. An address without a scheme, such as
  `192.168.164.39:39000`, is treated as `http://192.168.164.39:39000`.
- A filesystem shared by BioAgent and Cromwell, with identical absolute paths
  for uploaded FASTQ files, databases, and per-run output directories.
- Access to `cncb/assembly-id:v1.0`, or a compatible image supplied with the
  `docker_image` override, from the execution backend configured in Cromwell.
- Read access to the assembly databases declared in `inputs.json` from the
  Cromwell process and its execution backend.
- Up to 32 CPU cores, 64 GB memory, and 500 GB working disk with the defaults.

From the repository root:

```bash
conda create -n bioagent python=3.12 -y
conda activate bioagent
python -m pip install -r requirements.txt
export CROMWELL_URL=http://127.0.0.1:8000
```

The task image must provide the `/app/scripts/run_assembly.sh`,
`run_read_support.sh`, `run_identify.sh`, and `run_evaluate.sh` entrypoints.
Their command-line dependencies are documented in `environment.yml`.

The minimap2 indexes, reference FASTA files, and annotation tables are WDL
`File` inputs. Cromwell localizes them according to its configured backend.
For a Local/shared-filesystem backend, both services must resolve every input
and output path identically. If Cromwell launches Docker tasks, that backend
must also make localized inputs visible inside its task containers.

Verify the host environment and workflow syntax:

```bash
curl "$CROMWELL_URL/engine/v1/status"
```

`miniwdl check` remains available as an optional local syntax check when
BioAgent is invoked with WDL dry-run mode; normal execution uses Cromwell.

After submission, BioAgent polls Cromwell's workflow status API every five
seconds. A temporary `Unrecognized workflow ID` response is retried for up to
300 seconds (`cromwell_visibility_timeout` in `runner.yaml`) to allow for
submission visibility delays or load-balanced Cromwell deployments.

Pipeline behavior, inputs, and outputs are described in `DESCRIPTION.md`.

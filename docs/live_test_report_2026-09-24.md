# BioAgent live test report — 2026-09-24

This report records a live run of the BioAgent web application and agent runtime from this checkout. The test artifacts and screenshots are in [`images/live_tests_2026-09-24/`](images/live_tests_2026-09-24/); each JSON file contains the run status, model, trace, tool evidence, and returned answer.

The live run predates the optional S3-compatible input-staging adapter added
afterward. That adapter has offline coverage in
[`evals/smoke_cromwell_storage.py`](../evals/smoke_cromwell_storage.py).
The [2026-09-25 follow-up](#s3-input-staging-follow-up--2026-09-25) below
records a successful live upload and Cromwell shared-mount read.

## Execution setup

- Web server: `http://127.0.0.1:8000`
- Health check: passed (`{"status":"ok"}`)
- Remote WDL backend: `CROMWELL_URL=http://192.168.164.39:39000`
- OpenRouter credential: supplied as a temporary process environment variable only; it was not written to the repository or this report.
- Default server configuration: `gpt-5.6-sol`, 12 turns.
- Live fallback model used for the successful tool tests: `deepseek/deepseek-v4-flash`, with 8–20 turns where the workflow needed more tool calls.

## Results

| Area | Result | Evidence |
|---|---|---|
| Embedded website assistant | **Passed**. `/assistant-demo` loaded the shadow-DOM iframe; the assistant read the visible workflow, measurements table, figure, Methods route, and exposed the `set_group` action through the website bridge. | [website JSON](images/live_tests_2026-09-24/website_guidance.json) · [screenshot](images/live_tests_2026-09-24/website_guidance.png) |
| Model routing | **Fallback required**. `gpt-5.6-sol`, `openai/gpt-5.6-terra`, and `google/gemini-3.8-flash` returned OpenRouter HTTP 403 region restrictions. DeepSeek V4 Flash and Qwen 3.8 completed successfully. | [Sol JSON](images/live_tests_2026-09-24/direct_sdk.json) · [Terra JSON](images/live_tests_2026-09-24/direct_sdk_terra.json) · [Gemini JSON](images/live_tests_2026-09-24/direct_sdk_gemini.json) · [DeepSeek screenshot](images/live_tests_2026-09-24/direct_sdk_deepseek.png) · [Qwen screenshot](images/live_tests_2026-09-24/direct_sdk_qwen.png) |
| Sequence tools | **Passed**. Statistics, ORF search, and translation ran together on an 18 bp DNA sequence: 50% GC, no complete ORF, translated peptide `MRKPGF`. | [JSON](images/live_tests_2026-09-24/atomic_sequence.json) · [screenshot](images/live_tests_2026-09-24/atomic_sequence.png) |
| PDB structure workflow | **Passed**. PDB 1A3N was downloaded as mmCIF and inspected: deoxy human hemoglobin, 1.8 Å, chains A–D, heme ligand. | [JSON](images/live_tests_2026-09-24/structure_database.json) · [screenshot](images/live_tests_2026-09-24/structure_database.png) |
| AlphaFold multi-turn workflow | **Passed**. BRCA1 P38398 was downloaded from AlphaFold as `outputs/alphafold/AF-P38398-F1.cif`; the next turn used file inspection and wrote `AF-P38398-F1-report.md` beside it. | [download JSON](images/live_tests_2026-09-24/multiturn_structure_first.json) · [handoff JSON](images/live_tests_2026-09-24/multiturn_structure_second_safe.json) · [screenshot](images/live_tests_2026-09-24/multiturn_structure.png) |
| Table analysis | **Passed**. Profiling, grouping, a code edit, and three distribution plots completed for the uploaded measurements CSV. | [JSON](images/live_tests_2026-09-24/table_analysis.json) · [screenshot](images/live_tests_2026-09-24/table_analysis.png) |
| Document research | **Passed**. The uploaded Paper2Agent PDF was read with page-located limitations and discussion evidence. | [JSON](images/live_tests_2026-09-24/document_research.json) · [screenshot](images/live_tests_2026-09-24/document_research.png) |
| Web research and report writing | **Passed**. Web/PubMed search, fetching, evidence indexing/retrieval, synthesis, and Markdown report writing completed for PhiX174 genome organization. | [JSON](images/live_tests_2026-09-24/web_research_report.json) · [screenshot](images/live_tests_2026-09-24/web_research_report.png) |
| Knowledge ingestion and genome visualization | **Passed**. A collection was created and indexed, passages were retrieved, NC_001422 was fetched, sequence statistics/ORFs were calculated, and `genome_render_map` produced the genome-map artifacts consumed by the new viewer. | [JSON](images/live_tests_2026-09-24/knowledge_ingestion.json) · [screenshot](images/live_tests_2026-09-24/knowledge_ingestion.png) |
| Pipeline catalog and discovery | **Passed**. The catalog and example staging path were exercised, including the bacterial annotation and WDL families. | [JSON](images/live_tests_2026-09-24/pipeline_discovery.json) · [screenshot](images/live_tests_2026-09-24/pipeline_discovery.png) |
| `template_shell` pipeline | **Passed end to end**. Approval was requested and granted; the job produced report, metrics, normalized text, subtype assignments, logs, and a ZIP bundle. Three reads were assigned to alpha, beta, and gamma with zero unassigned reads. | [JSON](images/live_tests_2026-09-24/pipeline_template_success.json) · [screenshot](images/live_tests_2026-09-24/pipeline_template_success.png) |
| Bacterial genome annotation pipeline | **Blocked by environment dependencies**. The first plan mixed Prokka and Bakta-only parameters; the corrected Prokka plan found no Prokka binary; the Bakta plan found no configured Bakta database. No outputs were fabricated. | [original plan](images/live_tests_2026-09-24/pipeline_execution.json) · [corrected plan](images/live_tests_2026-09-24/pipeline_run_corrected.json) · [Bakta result](images/live_tests_2026-09-24/pipeline_run_bakta.json) · [screenshot](images/live_tests_2026-09-24/pipeline_run_bakta.png) |
| Remote Cromwell WDL | **Remote submission passed; execution failed at localization**. The real plan used the configured Cromwell URL and was accepted as workflow `5ce660e7-085a-4723-ae2b-80744d8599f6`. Cromwell could not see the agent-local `runs/.../inputs` path, so the job failed before processing reads. | [actual plan](images/live_tests_2026-09-24/wdl_cromwell_plan_actual.json) · [actual run](images/live_tests_2026-09-24/wdl_cromwell_run_actual.json) · [screenshot](images/live_tests_2026-09-24/wdl_cromwell_run_actual.png) |
| Coding support | **Passed**. The uploaded Python job model was inspected, updated with a stable `id`, and tested. | [JSON](images/live_tests_2026-09-24/coding_support.json) · [screenshot](images/live_tests_2026-09-24/coding_support.png) |

## Pipeline and Cromwell findings

The local pipeline protocol is healthy: the internal `template_shell` example completed through staging, planning, approval, run, wait, and result collection. The production-style bacterial annotation path needs either the Prokka executable or a Bakta installation with `BAKTA_DB`/`bakta_db_path` configured.

The remote WDL path also reached the intended server, which confirms that `CROMWELL_URL` was honored. The remaining integration issue is filesystem visibility: the remote Cromwell host needs the staged input at the same path, or the adapter must upload/localize inputs to a path visible to that host before submission.

The new optional S3-compatible adapter addresses input localization by
uploading local files to S3 and rewriting the WDL inputs to the corresponding
shared-mount paths. For the administrator's deployment, those paths should be
under `/data/versitygw/data/s3/cncb-web-server-mic/files/`. Output paths still
need to be shared or downloadable after the workflow completes.

## S3 input staging follow-up — 2026-09-25

The administrator's backend is in `resource/mscan-app`. Its production
configuration specifies S3 at `http://192.168.164.39:7070`, bucket
`cncb-web-server-mic`, prefix `files/`, and mount root
`/data/versitygw/data/s3`. The suggested ports 7001 and 37001 were closed
during this check. Existing backend credentials were used only in the test
process environment; they are omitted from this report and its evidence.

The adapter now uploads local input files before submission and replaces their
WDL input values with `/data/versitygw/data/s3/cncb-web-server-mic/files/...`.
Repeated references to the same file reuse one upload and the same remote path.

- **Storage access passed.** Workflow `d5e723d0-c0a7-40a3-a39e-5548ec5b26a5`
  finished with `Succeeded`. Its WDL `read_string(source)` output exactly
  matched the synthetic file uploaded through the adapter's storage helper.
  This confirms that Cromwell can read the uploaded file using the mounted
  absolute path; it does not test container execution or output-file retrieval.
  The probe object was deleted after verification.
  [Live evidence](images/live_tests_2026-09-24/cromwell_s3_followup_2026-09-25.json).
- **Full template execution remains unverified.** The adapter submitted
  `template_wdl` as `b0a24ec7-ff17-4003-a8ad-4c566ab23d97` using the uploaded
  FASTA path. The client timed out after 300 seconds; the remote call remained
  `Running` / `WaitingForReturnCode`, with no failure details returned by
  Cromwell. An abort was requested to clean up this synthetic test. The server's
  task logs are needed to determine why execution did not finish.
  [Live evidence](images/live_tests_2026-09-24/cromwell_template_followup_2026-09-25.json).
- **Offline checks passed.** Storage staging and adapter integration checks,
  plus all 10 pipeline configuration tests, passed.

The original 2026-09-24 localization failure above remains part of the historical
record. The new probe verifies the proposed input-storage solution. Automatic
download of remote output files is still outside this input-staging adapter;
the current collector requires output paths visible to BioAgent.

## Screenshot index

### Core and biology workflows

![Sequence analysis](images/live_tests_2026-09-24/atomic_sequence.png)
![PDB structure](images/live_tests_2026-09-24/structure_database.png)
![AlphaFold continuation](images/live_tests_2026-09-24/multiturn_structure.png)
![Table analysis](images/live_tests_2026-09-24/table_analysis.png)
![Document research](images/live_tests_2026-09-24/document_research.png)
![Web research report](images/live_tests_2026-09-24/web_research_report.png)
![Knowledge and genome map](images/live_tests_2026-09-24/knowledge_ingestion.png)

### Website and runtime workflows

![Embedded website assistant](images/live_tests_2026-09-24/website_guidance.png)
![Template shell pipeline](images/live_tests_2026-09-24/pipeline_template_success.png)
![Remote Cromwell run](images/live_tests_2026-09-24/wdl_cromwell_run_actual.png)
![Coding support](images/live_tests_2026-09-24/coding_support.png)

### Model and pipeline diagnostics

![DeepSeek fallback](images/live_tests_2026-09-24/direct_sdk_deepseek.png)
![Qwen fallback](images/live_tests_2026-09-24/direct_sdk_qwen.png)
![GPT-5.6 Sol region block](images/live_tests_2026-09-24/direct_sdk_region_block.png)
![GPT-5.6 Terra region block](images/live_tests_2026-09-24/direct_sdk_terra_region_block.png)
![Gemini region block](images/live_tests_2026-09-24/direct_sdk_gemini_region_block.png)
![Pipeline discovery](images/live_tests_2026-09-24/pipeline_discovery.png)
![Pipeline annotation plan](images/live_tests_2026-09-24/pipeline_execution.png)
![Pipeline corrected plan](images/live_tests_2026-09-24/pipeline_run_corrected.png)
![Pipeline dependency result](images/live_tests_2026-09-24/pipeline_run_bakta.png)

## Follow-up needed for a fully green production run

1. Make Prokka available, or configure a Bakta database, for the bacterial annotation container.
2. Start BioAgent with the [verified S3 configuration](../tools/runtime_tools/pipelines/README.md), investigate the template task's `WaitingForReturnCode` state on the remote server, and arrange output paths visible to BioAgent or implement remote output retrieval.
3. Keep the model fallback configurable because the tested premium and standard aliases were region-restricted through the supplied OpenRouter account.

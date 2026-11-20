# BioAgent–MSCAN live interoperability validation — 2026-11-20

Consolidated 2026-11-20T14:58:37.610489+08:00. Initial execution, follow-up branches, account investigation and shutdown history are combined below.

## Scope and final outcome

The combined initial and follow-up validation covers example-data pipeline execution, the BioAgent–MSCAN bridge, file exchange, native import, agent/browser behavior, and the later account-visibility investigation. **26 of 28 catalog families have at least one successful execution.** PHI execution used artificial negative controls only; two pathogen variant-risk workflows remained excluded. These results assess software behavior and data interchange, not scientific accuracy or clinical suitability.

| Coverage | Initial round | Follow-up | Combined interpretation |
|---|---|---|---|
| Pipeline execution | 23 succeeded, 1 timed out, 4 safety exclusions | 11 cases: 9 succeeded, 2 preparation failures | 26/28 distinct families executed successfully; the two failed protein branches belong to families with other successful inputs |
| Individual file pull checks | 208/208 matched | 55/58 matched | **263/266 matched**; three zero-byte attachment pulls failed |
| Independent source comparisons | 180/180 matched | 49/49 matched, including three ZIP recoveries | **229/229 matched**; ZIP recovery does not change failed individual pulls into passes |
| Direct native synchronization | 16/18 completed non-template families imported | 9/9 completed jobs imported; 9/9 repeat synchronizations succeeded | At least one import succeeded for **19/21 non-template executed families**; broad and k-mer detection remain blocked |

Round totals include repeated checks of identical content in different samples. The standalone one-byte boundary control is separate from these file totals. Accepted native imports can contain empty results.

The later browser inspection established an important acceptance gap: test results were delivered to the linked MSCAN account **xiaomimi**, while the user's browser was signed in as **mscan2026**. The test project was therefore absent from that browser account. Real interactive CNCB SSO was skipped at the user's request.

[Initial summary](mscan_interoperability_2026-11-20/evidence/summary.json); [follow-up summary](mscan_remaining_validation_2026-11-20/evidence/summary.json).

**The TCDB annotator web display failed at the recorded browser check.** Execution/import success did not establish that its Parquet-backed table could load. The browser showed xiaomimi and the imported overview counts, while the table request failed in DuckDB because of the backend's inherited proxy setting. [Recorded UI diagnostic](mscan_remaining_validation_2026-11-20/evidence/annotator-ui-diagnostic.json).

## Environment and isolation

[Preflight, commits and worker image](mscan_interoperability_2026-11-20/evidence/preflight.json); [connector capabilities and live search](mscan_interoperability_2026-11-20/evidence/connection.json).

Standard endpoints: BioAgent `localhost:8000`, OAuth `localhost:8090`, MSCAN backend `localhost:8080`, frontend `localhost:8848`. Cromwell and object storage used the configured remote deployment. Jobs were admitted within the existing two-job account quota. The initial observation limit was 20 minutes per pipeline. The assembly retry allowed 45 minutes and finished within about 20 minutes including exchange checks. Additional follow-up branches used 15-minute budgets. Timeouts are distinct from terminal workflow failures.

The standard MSCAN backend already had `scheduled.cromwellPoll.enabled=false` when discovered. The bridge transfer poller and explicit result synchronization were exercised; ordinary MSCAN scheduler submission is outside these results.

Dedicated projects: `Bridge_expanded_20261120_standard`, `Bridge_expanded_20261120_test`, and `Bridge_remaining_20261120`. Existing non-test samples and application source were not intentionally changed. The pre-existing local validation stack stopped during browser testing; a loopback-only replacement reused its isolated test identity/state. Prior receipts were restored to its validation results directory. Interruption evidence is retained and excluded from clean pass claims.

Browser acceptance used a separate loopback-only validation profile and a synthetic test identity. Its login, account mapping and logout checks do not establish real CAS authentication.

## Example data

Bacterial annotation and profiling used the unmodified E. coli K-12 MG1655 reference and deterministic simulated reads. The [NCBI reference](https://www.ncbi.nlm.nih.gov/nuccore/NC_000913.3) identifies the strain; [ATCC](https://www.atcc.org/products/700926) classifies this strain as BSL 1. PAO1 examples were replaced for BGC, defense and secretion annotation. Templates used bundled toy data; basic variant analysis used the bundled phiX174 example; routine viral typing/traceback used the bundled public examples. Screening used a synthetic negative control.

[Exact provenance, sizes and hashes](mscan_interoperability_2026-11-20/evidence/input-provenance.json). Simulated reads are software test data. Empty or negative outputs do not demonstrate successful detection of a positive biological target.

The paired-read PHI control contains 64 pairs of artificial low-complexity 150-base reads. The single-read case uses its first mate only. The genome control contains 20,000 bases of artificial repetitive DNA. Both PHI families completed with `no_hits`; hit and summary tables are valid header-only outputs. These cases do not validate detection of a biological target. The common label “noncoding” in the fixture filename is a test label; gene prediction may still emit an artificial open reading frame. [Input byte counts and hashes](mscan_remaining_validation_2026-11-20/evidence/inputs.json).

Additional single-end QC, MetaX, growth-rate and marker branches used the same K-12 simulated reads. TCDB read and protein branches used artificial controls. [Branch inventory](mscan_remaining_validation_2026-11-20/evidence/extra-branch-inventory.json).

## Pipeline execution and exchange coverage

These columns score workflow execution, native import and file identity. They do not score annotator table rendering; the observed TCDB web/API failure is recorded in Findings.

The matrix gives one representative execution per catalog family. Initial cases are retained except where the follow-up completed assembly or tested PHI with artificial controls. The original assembly timeout and initial PHI exclusions remain in their linked evidence. Additional input branches are listed separately below.

“File native” is the outcome of pushing the actual result bundle. “Direct sync” is the distinct `website_result_sync` path using a real succeeded BioAgent job and its recorded Cromwell UUID. Template formats may remain unsupported while their files are fully downloadable.

| Pipeline bundle | Execution | File native | Direct sync | Hash checks | Evidence |
|---|---|---|---|---|---|
| `bacterial_biosynthetic_gene_clusters` | succeeded | imported | imported | 5/5 | [JSON](mscan_interoperability_2026-11-20/evidence/pipelines/bacterial_biosynthetic_gene_clusters.json) |
| `bacterial_defense_system_annotation` | succeeded | imported | imported | 5/5 | [JSON](mscan_interoperability_2026-11-20/evidence/pipelines/bacterial_defense_system_annotation.json) |
| `bacterial_secretion_system_annotation` | succeeded | imported | imported | 4/4 | [JSON](mscan_interoperability_2026-11-20/evidence/pipelines/bacterial_secretion_system_annotation.json) |
| `bacterial_viral_variant_analysis` | succeeded | unsupported | imported | 6/6 | [JSON](mscan_interoperability_2026-11-20/evidence/pipelines/bacterial_viral_variant_analysis.json) |
| `genomic_pathogen_identification` | succeeded | unsupported | imported | 9/9 | [JSON](mscan_interoperability_2026-11-20/evidence/pipelines/genomic_pathogen_identification.json) |
| `metagenomic_de_novo_assembly` | succeeded on retry | imported | imported | 4/6 | [Initial](mscan_interoperability_2026-11-20/evidence/pipelines/metagenomic_de_novo_assembly.json), [follow-up](mscan_remaining_validation_2026-11-20/evidence/cases/assembly_extended.json) |
| `metagenomic_growth_rate_Calculation` | succeeded | imported | imported | 4/4 | [JSON](mscan_interoperability_2026-11-20/evidence/pipelines/metagenomic_growth_rate_Calculation.json) |
| `metagenomic_pathogen_identification` | succeeded | unsupported | failed | 8/8 | [JSON](mscan_interoperability_2026-11-20/evidence/pipelines/metagenomic_pathogen_identification.json) |
| `metagenomic_pathogen_identification_kmer` | succeeded | unsupported | failed | 6/6 | [JSON](mscan_interoperability_2026-11-20/evidence/pipelines/metagenomic_pathogen_identification_kmer.json) |
| `metagenomic_pathogen_identification_marker` | succeeded | imported | imported | 6/6 | [JSON](mscan_interoperability_2026-11-20/evidence/pipelines/metagenomic_pathogen_identification_marker.json) |
| `metagenomic_qc_UniVec_Host` | succeeded | imported | imported | 7/7 | [JSON](mscan_interoperability_2026-11-20/evidence/pipelines/metagenomic_qc_UniVec_Host.json) |
| `metagenomic_read_quality_control` | succeeded | imported | imported | 7/7 | [JSON](mscan_interoperability_2026-11-20/evidence/pipelines/metagenomic_read_quality_control.json) |
| `metax_classification_abundance_analysis` | succeeded | imported | imported | 4/4 | [JSON](mscan_interoperability_2026-11-20/evidence/pipelines/metax_classification_abundance_analysis.json) |
| `pathogen_variant_risk_assessment` | skipped_safety | inert only | — | 1/1 | [JSON](mscan_interoperability_2026-11-20/evidence/pipelines/pathogen_variant_risk_assessment.json) |
| `pathogen_variant_risk_assessment_consensus` | skipped_safety | inert only | — | 1/1 | [JSON](mscan_interoperability_2026-11-20/evidence/pipelines/pathogen_variant_risk_assessment_consensus.json) |
| `phi_annotator_genome` | succeeded; artificial control | imported | imported | 8/8 | [Initial](mscan_interoperability_2026-11-20/evidence/pipelines/phi_annotator_genome.json), [follow-up](mscan_remaining_validation_2026-11-20/evidence/cases/phi_genome_dna_negative.json) |
| `phi_annotator_metagenome` | succeeded; artificial control | imported | imported | 10/10 | [Initial](mscan_interoperability_2026-11-20/evidence/pipelines/phi_annotator_metagenome.json), [follow-up](mscan_remaining_validation_2026-11-20/evidence/cases/phi_metagenome_paired_negative.json) |
| `risk_screen` | succeeded | unsupported | imported | 3/3 | [JSON](mscan_interoperability_2026-11-20/evidence/pipelines/risk_screen.json) |
| `tcdb_annotator_genome` | succeeded | imported after retry | imported | 9/9 | [JSON](mscan_interoperability_2026-11-20/evidence/pipelines/tcdb_annotator_genome.json) |
| `tcdb_annotator_metagenome` | succeeded | imported | imported | 10/10 | [JSON](mscan_interoperability_2026-11-20/evidence/pipelines/tcdb_annotator_metagenome.json) |
| `template_bio` | succeeded | unsupported | — | 20/20 | [JSON](mscan_interoperability_2026-11-20/evidence/pipelines/template_bio.json) |
| `template_nextflow` | succeeded | unsupported | — | 6/6 | [JSON](mscan_interoperability_2026-11-20/evidence/pipelines/template_nextflow.json) |
| `template_shell` | succeeded | unsupported | — | 7/7 | [JSON](mscan_interoperability_2026-11-20/evidence/pipelines/template_shell.json) |
| `template_snakemake` | succeeded | unsupported | — | 6/6 | [JSON](mscan_interoperability_2026-11-20/evidence/pipelines/template_snakemake.json) |
| `template_wdl` | succeeded | unsupported | unsupported | 5/5 | [JSON](mscan_interoperability_2026-11-20/evidence/pipelines/template_wdl.json) |
| `traceback_covid19` | succeeded | unsupported | imported | 9/9 | [JSON](mscan_interoperability_2026-11-20/evidence/pipelines/traceback_covid19.json) |
| `viral_genome_molecular_typing` | succeeded | unsupported | imported | 6/6 | [JSON](mscan_interoperability_2026-11-20/evidence/pipelines/viral_genome_molecular_typing.json) |
| `viral_read_molecular_typing` | succeeded | unsupported | imported | 7/7 | [JSON](mscan_interoperability_2026-11-20/evidence/pipelines/viral_read_molecular_typing.json) |

### Follow-up input branches

| Case | Execution | Bundle native import | Direct sync | Repeat sync | Download hashes |
|---|---|---|---|---|---|
| [`assembly_extended`](mscan_remaining_validation_2026-11-20/evidence/cases/assembly_extended.json) | succeeded | imported | succeeded | succeeded | 4/6 |
| [`growth_single_end`](mscan_remaining_validation_2026-11-20/evidence/cases/growth_single_end.json) | succeeded | imported | succeeded | succeeded | 3/3 |
| [`marker_single_end`](mscan_remaining_validation_2026-11-20/evidence/cases/marker_single_end.json) | succeeded | imported | succeeded | succeeded | 5/5 |
| [`metax_single_end`](mscan_remaining_validation_2026-11-20/evidence/cases/metax_single_end.json) | succeeded | imported | succeeded | succeeded | 2/3 |
| [`phi_genome_dna_negative`](mscan_remaining_validation_2026-11-20/evidence/cases/phi_genome_dna_negative.json) | succeeded | imported | succeeded | succeeded | 8/8 |
| [`phi_genome_protein_negative`](mscan_remaining_validation_2026-11-20/evidence/cases/phi_genome_protein_negative.json) | failed | — | — | — | 0/0 |
| [`phi_metagenome_paired_negative`](mscan_remaining_validation_2026-11-20/evidence/cases/phi_metagenome_paired_negative.json) | succeeded | imported | succeeded | succeeded | 10/10 |
| [`phi_metagenome_single_negative`](mscan_remaining_validation_2026-11-20/evidence/cases/phi_metagenome_single_negative.json) | succeeded | imported | succeeded | succeeded | 9/9 |
| [`qc_single_end`](mscan_remaining_validation_2026-11-20/evidence/cases/qc_single_end.json) | succeeded | imported | succeeded | succeeded | 5/5 |
| [`tcdb_genome_protein_negative`](mscan_remaining_validation_2026-11-20/evidence/cases/tcdb_genome_protein_negative.json) | failed | — | — | — | 0/0 |
| [`tcdb_metagenome_single_negative`](mscan_remaining_validation_2026-11-20/evidence/cases/tcdb_metagenome_single_negative.json) | succeeded | imported | succeeded | succeeded | 9/9 |

Completed workflow outputs were also inspected for table rows, sequence record counts and source/native QC values. Header-only results remain empty-output coverage. [Output value checks](mscan_remaining_validation_2026-11-20/evidence/output-value-checks.json).

## Output observations

Assembly repeats the original unmodified benign E. coli K-12 simulated paired reads and default configuration. Its allowed observation budget was increased from 20 to 45 minutes. This retry completed within about 20 minutes including transfer checks; the larger budget was not fully consumed. All workflow tasks completed. It produced three contigs totaling 99,923 bases, while both identification reports were zero-byte files. Execution success does not establish a successful biological identification or a fully transferable output set. [Remote states](mscan_remaining_validation_2026-11-20/evidence/remote-progress.json).

Single-end growth-rate execution produced a header-only CSV, so it yielded no estimate. MetaX produced an empty profile. Marker classification produced a nonempty profile reporting 100% `UNCLASSIFIED`, plus a roughly 64 MB compressed alignment artifact. TCDB’s artificial read control produced zero hit rows. These outcomes establish process and exchange behavior, not a positive analytical result.

Single-end QC counts matched both its native record and the actual FASTQ: **12,000 input → 12,000 after QC → 11,767 after host removal**. The earlier detached paired-read QC case reported **12,000 → 12,000 → 11,908**. These are different test inputs/modes. [Source/native value checks](mscan_remaining_validation_2026-11-20/evidence/output-value-checks.json).

## Findings

1. **TCDB annotator table loading fails after import.** The observed sample `tcdb_annotator_metagenome_sync` shows persisted dimension counts, while `/cncb/tcdbResult/query` fails when the dimension table reads remote Parquet. The backend log reports `Invalid Input Error: Failed to parse port from http_proxy 'http://127.0.0.1:10801/'`. The running Java process inherited this proxy URL, including its trailing slash. Overview counts come from MySQL; detail rows use DuckDB and S3, so one can load while the other fails. This is a real web/API failure. The earlier success checks covered execution, import and file identity, and did not verify this annotator table endpoint. The report must not count that as an end-to-end display pass. Correct the backend's proxy environment or DuckDB proxy configuration, then verify the actual page and API. No runtime remediation has been applied by this diagnosis. [Diagnostic](mscan_remaining_validation_2026-11-20/evidence/annotator-ui-diagnostic.json).
2. **The intended browser account did not receive the results.** The connector used xiaomimi; the observed browser used mscan2026. The data existed under the linked account, but visibility in the intended account was not established. See [account and project visibility](#account-and-project-visibility).
3. **Zero-byte outputs cannot complete individual pull.** Assembly's two identification reports and MetaX's single-end profile were empty. Push/import and direct synchronization accepted them, while pull returned `IllegalArgumentException: File exceeds the 5368709120 byte upload limit.` The upload handler requires `0 < size <= file_bytes` and uses the oversized-file message for both bounds; workspace publication also requires at least one byte. [Upload boundary](../../interfaces/uploads.py); [workspace publication](../../isolation/storage.py); [zero/one-byte control](mscan_remaining_validation_2026-11-20/evidence/empty-file-boundary.json). All three original empty outputs were verified inside the downloaded result ZIPs. [ZIP recovery](mscan_remaining_validation_2026-11-20/evidence/archive-fallback.json).
4. **Protein-only PHI and TCDB inputs fail during preparation.** Both manifests advertise `protein_fasta` as an alternative, but the common context builder reported that `input_path` was required. Neither case reached remote submission. No application code, manifest, database or analysis threshold was changed to bypass this failure. [PHI diagnostic](mscan_remaining_validation_2026-11-20/evidence/protein-preparation-diagnostic.json); [TCDB diagnostic](mscan_remaining_validation_2026-11-20/evidence/tcdb-protein-preparation-diagnostic.json).
5. **Empty growth imports can erase a valid native result while reporting success.** A valid software fixture exported one native record. A header-only CSV then returned `imported` and exported zero records. A `NaN` fixture was also reported `imported`, with no valid record exported. This was confined to a dedicated test sample. [Before/after evidence](mscan_interoperability_2026-11-20/evidence/growth-preservation.json).
6. **Two native result synchronizations fail reproducibly.** Broad metagenomic detection fails because its workflow output contract lacks `depth_track_archives`, which MSCAN’s importer requires. K-mer detection produced 24,000 classification rows and 150 report rows, but its signature-coverage CSV was header-only; the current parser rejects CSV input with no data rows. Both same-ID retries failed again. The workflow files remained transferable with matching hashes. [Contract diagnostics](mscan_interoperability_2026-11-20/evidence/sync-contract-diagnostics.json); [broad-detection retry](mscan_interoperability_2026-11-20/evidence/sync-retries/metagenomic_pathogen_identification.json); [k-mer retry](mscan_interoperability_2026-11-20/evidence/sync-retries/metagenomic_pathogen_identification_kmer.json).
7. **Successful file delivery and native import must be assessed independently.** TCDB genome execution succeeded, but its first bundle push reported native failure after delivering the files. Its delivered files were recovered through search/pull and checked separately. Retrying the same transfer ID subsequently imported successfully; direct Cromwell synchronization also succeeded. [Recovery evidence](mscan_interoperability_2026-11-20/evidence/delivered-after-native-failure.json); [same-ID retry](mscan_interoperability_2026-11-20/evidence/native-retries.json).
8. **Some push formats remain unsupported or ambiguous.** Basic variant and genomic-identification files were downloadable, while their file-based native importer returned `unsupported`; their direct synchronization path imported successfully. Template native schemas are unsupported by design.
9. **Browser helper failures are preserved separately.** Initial direct callback calls timed out and an earlier test stack stopped. Live model/UI results and native table/figure/export checks are reported separately; a generic successful model run alone is not counted as proof that every requested callback succeeded. [Browser checks](mscan_interoperability_2026-11-20/evidence/browser-test.json); [interruption](mscan_interoperability_2026-11-20/evidence/browser-test-interrupted.json).
10. **Harness corrections remain auditable.** The first genome-typing attempt paired the H3N2 bundled FASTA with an H1N1 preset. The corrected attempt uses H3N2; the initial attempt is retained. Screening destinations must use `synthetic`, as advertised by the connector. Any corrective exchange is recorded separately.
11. **Native synchronization does not guarantee a native export resource.** Some imported programs are absent from the connector’s native-resource catalog. For example, the synchronized genomic-identification sample returned only the sample resource, with no native result resource to pull. File-push attachments remain a separate available exchange path. [Native export matrix](mscan_interoperability_2026-11-20/evidence/sync-native-exports.json); [genomic sample check](mscan_interoperability_2026-11-20/evidence/genomic-sync-resource-check.json).

## File exchange and parser fixtures

Actual inputs and actual result bundles were pushed to dedicated projects, then discovered through search and pulled back. `website_result_sync` used real owned BioAgent jobs and their Cromwell UUIDs, with repeats directed to the same sample. Individual file delivery, native import, direct sync and byte identity were assessed independently.

[Initial source comparisons](mscan_interoperability_2026-11-20/evidence/source-integrity.json); [follow-up source comparisons](mscan_remaining_validation_2026-11-20/evidence/source-integrity.json). ZIP containers were checked against transfer receipts, and recovered output contents were checked against actual source artifacts. The failed empty-file pulls remain failures even though their ZIP members matched.

The standard connector round-tripped CSV, TSV, JSON, text, Markdown, FASTA, FASTQ, gzip, ZIP, binary bytes and UTF-8 content across `meta`, `shortReads`, `genomic` and `synthetic` sample types. Repeated push reused the destination sample; invalid-resource retry retained the transfer ID; another owner could not read a transfer. This is a service-level ownership check, not a second real CNCB-account login.

Clearly labelled inert fixtures exercised TCDB/PHI schemas, QC counts, MetaX/marker/growth results, invalid schemas, unknown formats and missing roles. Files delivered with a native parser error remained a failed native import. The initial round did not execute PHI workflows. The follow-up ran PHI wrappers only with artificial negative controls; positive biological detection was not validated.

[Format and parser matrix](mscan_interoperability_2026-11-20/evidence/formats-standard.json).

## Native result pullback coverage

Counts below are resources exposed on the first page for the exact synchronized sample. Zero means no native resource was available to pull through this connector; it does not establish that the native database import failed.

| Pipeline | Native resources exposed | Successful sampled pulls |
|---|---|---|
| `bacterial_biosynthetic_gene_clusters` | 9 | 2/2 |
| `bacterial_defense_system_annotation` | 9 | 2/2 |
| `bacterial_secretion_system_annotation` | 6 | 2/2 |
| `bacterial_viral_variant_analysis` | 3 | 2/2 |
| `genomic_pathogen_identification` | 0 | 0/0 |
| `metagenomic_growth_rate_Calculation` | 1 | 1/1 |
| `metagenomic_pathogen_identification_marker` | 9 | 2/2 |
| `metagenomic_qc_UniVec_Host` | 4 | 2/2 |
| `metagenomic_read_quality_control` | 4 | 2/2 |
| `metax_classification_abundance_analysis` | 2 | 2/2 |
| `tcdb_annotator_genome` | 5 | 2/2 |
| `tcdb_annotator_metagenome` | 5 | 2/2 |
| `traceback_covid19` | 0 | 0/0 |
| `viral_genome_molecular_typing` | 0 | 0/0 |
| `viral_read_molecular_typing` | 0 | 0/0 |
| `risk_screen` | 0 | 0/0 |

[Exact native export and sample ownership evidence](mscan_interoperability_2026-11-20/evidence/sync-native-exports.json).

Source/native value checks also compare the QC counts and all five TCDB summary dimension totals with their native records: [comparisons](mscan_interoperability_2026-11-20/evidence/native-value-comparison.json).

### Follow-up native resource pulls

Counts refer to resources exposed on the first page for each exact synchronized sample. A zero count is a catalog/export limitation, not proof of a failed import.

| Case | Native resources exposed | Successful sampled pulls |
|---|---|---|
| `assembly_extended` | 6 | 2/2 |
| `growth_single_end` | 0 | 0/0 |
| `marker_single_end` | 1 | 1/1 |
| `metax_single_end` | 2 | 1/2 |
| `phi_genome_dna_negative` | 5 | 2/2 |
| `phi_metagenome_paired_negative` | 5 | 2/2 |
| `phi_metagenome_single_negative` | 5 | 2/2 |
| `qc_single_end` | 3 | 2/2 |
| `tcdb_metagenome_single_negative` | 5 | 2/2 |

[Follow-up export evidence](mscan_remaining_validation_2026-11-20/evidence/native-exports.json). MetaX native-file pull also encountered the zero-byte limitation.

## Agent and browser acceptance

A real model run searched the standard test project, pulled the exact 49-byte CSV, inspected its two rows, wrote a report and pushed it back successfully. A separate agent-driven remote QC run completed while the MSCAN page was closed and explicitly synchronized its results. Reopening restored the conversation and native metrics of 12,000 input, 12,000 after QC, and 11,908 after host removal. These are the workflow’s reported counts for simulated paired reads.

[Detached QC run and actual tool evidence](mscan_interoperability_2026-11-20/evidence/acceptance/detached-real-qc.json); [acceptance outcomes](mscan_interoperability_2026-11-20/evidence/acceptance.json). The broader combined page-callback acceptance exceeded its observation window and was cancelled; it is not marked passed. Individual live table, figure, CSV-export and navigation checks passed. Highlight was unsupported in the active adapter. A focused real UI Stop test verified server status `cancelled`: [evidence](mscan_interoperability_2026-11-20/evidence/stop-button-focused.json).

[Model-backed search, pull, report and push evidence](mscan_interoperability_2026-11-20/evidence/nl-backend.json).

## Account and project visibility

The standard connector was linked to MSCAN account **xiaomimi** during testing. The follow-up project is **Bridge_remaining_20261120**. Its Metagenomic and Synthetic entries are separate projects with the same name; select the appropriate sample category. The live database visibility check confirmed 16 Metagenomic samples and completed QC status for `qc_single_end_sync`, with counts of 12,000 input, 12,000 after QC and 11,767 after host removal.

[Saved QC result for the linked account](http://localhost:8848/sample/metagenomic?sampleId=b152b4a815a43100b09959580f53cdf4&program=qc). Its location is Metagenomic → `Bridge_remaining_20261120` → `qc_single_end_sync` → QC.

Subsequent inspection of the user’s actual browser confirmed that it was signed in as **mscan2026**, a different MSCAN user. Scoped database queries confirmed six Metagenomic projects for mscan2026, matching the browser sidebar, and no remaining-test project under that account. At that inspection, the linked xiaomimi account owned 21 Metagenomic projects, including the test project. The missing project is therefore an account/destination mismatch, not missing workflow output. The earlier tests did not establish visibility through the user’s mscan2026 browser session. Copies must be delivered under the intended account to appear there. [Live ownership and browser visibility evidence](mscan_remaining_validation_2026-11-20/evidence/website-visibility.json).

The existing account link was used without confirming it matched the user browser before testing. Refreshing or navigating to a direct link does not change ownership. Results had not been copied into mscan2026 by these checks.

A later browser inspection confirmed the user had signed in as **xiaomimi** and could see the test projects. The remaining TCDB table error was therefore a separate backend Parquet-query failure, not the previous account mismatch. [Later browser and backend diagnostic](mscan_remaining_validation_2026-11-20/evidence/annotator-ui-diagnostic.json).

## Result inspection and screenshots

Actual workflow outputs were opened through their owned local or remote artifact interfaces. Inspection records include file size/hash, table row counts, JSON structure, FASTQ record counts and FASTA record/length checks. Header-only tables remain explicitly visible. [Output inspection](mscan_interoperability_2026-11-20/evidence/output-inspection.json).

| Browser evidence | Screenshot |
|---|---|
| Delivered files in MSCAN | [Download menu](mscan_interoperability_2026-11-20/screenshots/02-download-menu.png) |
| Native QC software fixture, expected 100/90/80 | [QC view](mscan_interoperability_2026-11-20/screenshots/10-native-qc.png) |
| Embedded assistant | [Assistant](mscan_interoperability_2026-11-20/screenshots/08-assistant-opened.png) |
| Live model result | [Chat result](mscan_interoperability_2026-11-20/screenshots/04-live-model-result.png) |
| Actual QC after detached completion | [Native metrics and restored assistant](mscan_interoperability_2026-11-20/screenshots/20-actual-qc-after-detach.png) |
| Actual QC native view and available downloads | [Metrics](mscan_interoperability_2026-11-20/screenshots/25-actual-qc-native-view.png), [downloads](mscan_interoperability_2026-11-20/screenshots/26-actual-qc-downloads.png) |
| Real Stop control and cancelled run | [Stop](mscan_interoperability_2026-11-20/screenshots/23-stop-button.png), [cancelled UI](mscan_interoperability_2026-11-20/screenshots/24-stopped-run.png) |
| Captured execution matrix, supplementary generated evidence | [Matrix](mscan_interoperability_2026-11-20/screenshots/27-execution-matrix.png) |

Screenshots of inert QC/native fixtures demonstrate presentation and interchange, not a new scientific QC run. Per-pipeline evidence summaries, if included, are labelled as generated execution evidence rather than MSCAN UI.

The actual educational `template_bio` QC figure was also opened for visual inspection: [bundled-example figure](mscan_interoperability_2026-11-20/figures/template-bio-qc-overview.png).

An additional source-integrity comparison checks pulled inputs and extracted pipeline outputs against the actual owned originals and remote artifact bytes, rather than relying only on the website’s advertised hash. ZIP container identities are checked against their transfer receipts, with extracted contents checked separately. [Source comparison](mscan_interoperability_2026-11-20/evidence/source-integrity.json). Native exports were sampled at up to two resources per synchronized case; this does not exhaustively test every database record.

### Follow-up artifact screenshots

The following are explicitly labelled views of captured job/output evidence, not screenshots proving an authenticated MSCAN session for mscan2026.

- [Execution and transfer outcomes](mscan_remaining_validation_2026-11-20/screenshots/01-remaining-execution-matrix.png)
- [Actual negative-control report and output counts](mscan_remaining_validation_2026-11-20/screenshots/02-negative-control-output.png)
- [Additional input branch outputs and native QC comparisons](mscan_remaining_validation_2026-11-20/screenshots/03-additional-branch-outputs.png)

[Actual follow-up output values](mscan_remaining_validation_2026-11-20/evidence/output-value-checks.json); [artifact browser inspection](mscan_remaining_validation_2026-11-20/evidence/browser-inspection.json). The later screenshot used to identify the user browser account remains private because it contains unrelated browser tab titles.

## Supporting verification

| Check | Result | Evidence |
|---|---|---|
| Python bridge regression suite | 52 passed | [Log](mscan_interoperability_2026-11-20/evidence/bridge-tests.log) |
| OAuth regression suite | 28 passed | [Log](mscan_interoperability_2026-11-20/evidence/oauth-tests-rerun.log) |
| Java boundary/import/security/concurrency checks | Passed | [Log](mscan_interoperability_2026-11-20/evidence/java-checks.log) |
| Java logout checks | Passed | [Log](mscan_interoperability_2026-11-20/evidence/logout-checks.log) |
| MSCAN frontend type check | Passed | [Log](mscan_interoperability_2026-11-20/evidence/frontend-types.log) |

## Limits and service lifecycle

Real CNCB sign-in, two authenticated production users, arbitrary existing user data, positive biological detection for PHI, and scientific accuracy were not validated. Inert parser fixtures and negative controls establish software behavior only. The broader combined page-callback acceptance timed out; its successful individual checks remain separate. All files were retained in the dedicated test projects and evidence directories.

All **31 recorded remote test workflows were terminal** when checked before shutdown. No local test runners or worker containers remained; temporary validation ports 18000, 18080, 18090 and 18848 were closed. [Stop verification](mscan_remaining_validation_2026-11-20/evidence/test-stop-state.json).

The original final-state snapshots recorded the four standard services running. At the user's subsequent request, BioAgent, OAuth, MSCAN backend and frontend were stopped, and ports 8000, 8090, 8080 and 8848 were confirmed closed. A later passive check during this report merge found those ports listening again under new process IDs. The merge did not start tests or services. [Service lifecycle and later observation](mscan_remaining_validation_2026-11-20/evidence/service-lifecycle.json).

Application source and pipeline manifests were preserved. OAuth login bypass was disabled on the standard service during validation. Credential scans and link checks passed for the published validation artifacts. The original snapshots remain historical evidence: [initial final state](mscan_interoperability_2026-11-20/evidence/final-state.json), [follow-up final state](mscan_remaining_validation_2026-11-20/evidence/final-state.json), [artifact validation](mscan_remaining_validation_2026-11-20/evidence/artifact-validation.json).

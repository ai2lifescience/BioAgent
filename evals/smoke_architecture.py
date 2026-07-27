"""No-network architecture smoke checks."""

from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent_core.router import IntentRouter
from agent_core.planner import Planner
from registries.skill_registry import list_skill_names
from registries.tool_registry import list_tool_names


def main() -> int:
    skills = set(list_skill_names())
    assert {
        "example_skill",
        "ncbi_retrieval",
        "pipeline_runner",
        "species_report",
        "pdb_download",
        "protein_structure_analysis",
        "genome_map",
        "pipeline_results",
    } <= skills
    tools = set(list_tool_names())
    assert {
        "echo",
        "ncbi_fetch",
        "pipeline_runner",
        "sequence_analyze",
        "genome_map",
        "protein_structure_analyze",
        "bio_database_search",
        "pdb_download",
        "pipeline_results_collect",
    } <= tools

    router = IntentRouter()
    example_route = router.route(
        "Please test skill calling by running the example skill with message hello and tag smoke."
    )
    assert example_route.mode == "direct_skill"
    assert example_route.skill_name == "example_skill"

    shell_route = router.route("Run the shell pipeline.")
    assert shell_route.mode == "direct_skill"
    assert shell_route.skill_name == "pipeline_runner"
    assert shell_route.arguments["pipeline_name"] == "generic_shell"

    snakemake_route = router.route("Run the example snakemake pipeline dry-run with 2 cores.")
    assert snakemake_route.mode == "direct_skill"
    assert snakemake_route.skill_name == "pipeline_runner"
    assert snakemake_route.arguments["pipeline_name"] == "generic_snakemake"
    assert snakemake_route.arguments["dry_run"] is True
    assert snakemake_route.arguments["cores"] == 2

    generic_bio_route = router.route(
        "Run pipeline with pipeline_name: generic_bio "
        'reads: "pipelines/generic_bio/data/input/reads.fastq" '
        'reference: "pipelines/generic_bio/data/input/reference.fasta" '
        'metadata: "pipelines/generic_bio/data/input/samples.tsv"'
    )
    assert generic_bio_route.mode == "direct_skill"
    assert generic_bio_route.skill_name == "pipeline_runner"
    assert generic_bio_route.arguments["pipeline_name"] == "generic_bio"
    assert generic_bio_route.arguments["input_overrides"] == {
        "reads": "pipelines/generic_bio/data/input/reads.fastq",
        "reference": "pipelines/generic_bio/data/input/reference.fasta",
        "metadata": "pipelines/generic_bio/data/input/samples.tsv",
    }
    assert "input_path" not in generic_bio_route.arguments

    bacterial_annotation_route = router.route(
        "Annotate bacterial genome "
        'genome: "pipelines/bacterial_annotation/data/input/contigs.fasta" '
        'genus Escherichia species coli strain "K-12" cpus 4'
    )
    assert bacterial_annotation_route.mode == "direct_skill"
    assert bacterial_annotation_route.skill_name == "pipeline_runner"
    assert bacterial_annotation_route.arguments["pipeline_name"] == "bacterial_annotation"
    assert bacterial_annotation_route.arguments["input_overrides"] == {
        "genome": "pipelines/bacterial_annotation/data/input/contigs.fasta"
    }
    assert bacterial_annotation_route.arguments["config_overrides"] == {
        "genus": "Escherichia",
        "species": "coli",
        "strain": "K-12",
        "cpus": "4",
    }

    bacterial_annotation_cores_route = router.route(
        'Annotate this bacterial genome "contigs.fna" with 3 cores'
    )
    assert bacterial_annotation_cores_route.arguments["pipeline_name"] == "bacterial_annotation"
    assert bacterial_annotation_cores_route.arguments["input_overrides"] == {
        "genome": "contigs.fna"
    }
    assert bacterial_annotation_cores_route.arguments["config_overrides"]["cpus"] == 3

    bakta_annotation_route = router.route(
        "annotate_bacterial_genome "
        'genome: "contigs.fna" annotator bakta '
        'bakta_db_path: "/opt/bakta-db/db-full" translation_table 11 gram - cpus 8'
    )
    assert bakta_annotation_route.skill_name == "pipeline_runner"
    assert bakta_annotation_route.arguments["pipeline_name"] == "bacterial_annotation"
    assert bakta_annotation_route.arguments["config_overrides"] == {
        "annotator": "bakta",
        "cpus": "8",
        "translation_table": "11",
        "bakta_db_path": "/opt/bakta-db/db-full",
        "gram": "-",
    }

    natural_bakta_route = router.route('Annotate bacterial genome "contigs.fna" using Bakta')
    assert natural_bakta_route.arguments["config_overrides"]["annotator"] == "bakta"

    pipeline_results_route = router.route(
        "Collect and show all results from the generic_bio pipeline run"
    )
    assert pipeline_results_route.mode == "direct_skill"
    assert pipeline_results_route.skill_name == "pipeline_results"
    assert pipeline_results_route.arguments == {"pipeline_name": "generic_bio"}

    latest_pipeline_results_route = router.route(
        "Collect and show all results from this pipeline run."
    )
    assert latest_pipeline_results_route.mode == "direct_skill"
    assert latest_pipeline_results_route.skill_name == "pipeline_results"
    assert latest_pipeline_results_route.arguments == {}

    ncbi_route = router.route("download 10 records phiX174 genes A G")
    assert ncbi_route.mode == "direct_skill"
    assert ncbi_route.skill_name == "ncbi_retrieval"

    report_route = router.route(
        "Summarize genome structure and host range of PhiX174 with trusted sources."
    )
    assert report_route.mode == "direct_skill"
    assert report_route.skill_name == "species_report"

    compare_route = router.route(
        "Compare PhiX174 and M13 genome structure, host range, and applications."
    )
    assert compare_route.mode == "llm_skill_loop"
    assert compare_route.arguments["entities"] == ["PhiX174", "M13"]
    assert "genome structure" in compare_route.arguments["focus"]
    compare_plan = Planner().plan(
        user_request="Compare PhiX174 and M13 genome structure, host range, and applications.",
        route=compare_route,
    )
    assert compare_plan.mode == "llm_skill_loop"
    assert [step.kind for step in compare_plan.steps] == [
        "llm_skill_loop",
        "evidence",
        "verification",
        "respond",
    ]
    natural_compare_route = router.route("How are PhiX174 and M13 different?")
    assert natural_compare_route.mode == "llm_skill_loop"
    assert natural_compare_route.arguments["entities"] == ["PhiX174", "M13"]

    evidence_review_route = router.route(
        "Summarize evidence for gene X in disease Y from PubMed and explain conflicts"
    )
    assert evidence_review_route.mode == "llm_skill_loop"
    assert evidence_review_route.skill_name is None
    assert evidence_review_route.arguments["task_type"] == "literature_evidence_review"

    pubmed_gene_route = router.route("Find PubMed papers for TP53")
    assert pubmed_gene_route.mode == "llm_skill_loop"
    assert pubmed_gene_route.skill_name is None

    sequence_route = router.route("Analyze PhiX174 segment sequence GAGTTTTATCGCTTCCATGACGCAGAAGTTAACACTTTCGGATATTTCTGATGAGTCGAAAAATTATCTT")
    assert sequence_route.mode == "direct_skill"
    assert sequence_route.skill_name == "sequence_analysis"

    genome_map_route = router.route("Show genome structure of the latest FASTA as a circular map")
    assert genome_map_route.mode == "direct_skill"
    assert genome_map_route.skill_name == "genome_map"
    assert genome_map_route.arguments["artifact_ref"] == "latest_fasta"
    assert genome_map_route.arguments["layout"] == "circular"
    species_structure_route = router.route("Show genome structure and host range for PhiX174")
    assert species_structure_route.mode == "direct_skill"
    assert species_structure_route.skill_name == "species_report"

    uniprot_route = router.route("Search UniProt for BRCA1 human")
    assert uniprot_route.mode == "direct_skill"
    assert uniprot_route.skill_name == "database_lookup"

    interpro_route = router.route("Search InterPro domains for P0A7V8")
    assert interpro_route.skill_name == "database_lookup"
    assert interpro_route.arguments == {
        "database": "interpro",
        "query": "P0A7V8",
        "operation": "protein_domains",
    }

    kegg_route = router.route("Get KEGG query: eco:b0002")
    assert kegg_route.skill_name == "database_lookup"
    assert kegg_route.arguments["query"] == "eco:b0002"

    quickgo_route = router.route(
        "Find QuickGO annotations for UniProtKB:P0A7V8 taxid 562"
    )
    assert quickgo_route.skill_name == "database_lookup"
    assert quickgo_route.arguments["operation"] == "annotation_search"
    assert quickgo_route.arguments["taxid"] == 562

    alphafold_route = router.route("Download AlphaFold structure for P0A7V8 as cif")
    assert alphafold_route.skill_name == "database_lookup"
    assert alphafold_route.arguments["query"] == "P0A7V8"
    assert alphafold_route.arguments["download"] is True

    rna_route = router.route(
        "Predict RNA secondary structure "
        'rna: "pipelines/rna_secondary_structure/data/input/example_rna.fasta" '
        "temperature_c 30"
    )
    assert rna_route.skill_name == "pipeline_runner"
    assert rna_route.arguments["pipeline_name"] == "rna_secondary_structure"
    assert rna_route.arguments["input_overrides"] == {
        "rna": "pipelines/rna_secondary_structure/data/input/example_rna.fasta"
    }
    assert rna_route.arguments["config_overrides"] == {"temperature_c": "30"}

    named_rna_route = router.route(
        'predict_rna_secondary_structure rna_path: "sequences.fasta"'
    )
    assert named_rna_route.arguments["pipeline_name"] == "rna_secondary_structure"

    named_interpro_route = router.route("query_interpro P0A7V8")
    assert named_interpro_route.skill_name == "database_lookup"
    assert named_interpro_route.arguments["query"] == "P0A7V8"

    pdb_download_route = router.route("Download PDB structure 1A3N as cif")
    assert pdb_download_route.mode == "direct_skill"
    assert pdb_download_route.skill_name == "pdb_download"
    assert pdb_download_route.arguments["pdb_id"] == "1A3N"
    assert pdb_download_route.arguments["file_format"] == "cif"

    structure_route = router.route(
        "Analyze structure file runtime/sessions/demo/artifacts/structures/1A3N.cif"
    )
    assert structure_route.mode == "direct_skill"
    assert structure_route.skill_name == "protein_structure_analysis"
    assert structure_route.arguments["structure_path"].endswith("1A3N.cif")

    latest_structure_route = router.route("Analyze the latest structure")
    assert latest_structure_route.mode == "direct_skill"
    assert latest_structure_route.skill_name == "protein_structure_analysis"
    assert latest_structure_route.arguments["artifact_ref"] == "latest_structure"

    pdb_structure_route = router.route("Analyze the structure of 3GOU")
    assert pdb_structure_route.mode == "direct_skill"
    assert pdb_structure_route.skill_name == "protein_structure_analysis"
    assert pdb_structure_route.arguments["pdb_id"] == "3GOU"

    help_route = router.route("help")
    assert help_route.mode == "control_response"
    help_plan = Planner().plan(user_request="help", route=help_route)
    assert help_plan.mode == "control_response"
    assert [(step.kind, step.name) for step in help_plan.steps] == [
        ("respond", "control_response"),
    ]

    llm_response_route = router.route("What is GC content?")
    assert llm_response_route.mode == "llm_response"
    llm_response_plan = Planner().plan(
        user_request="What is GC content?",
        route=llm_response_route,
    )
    assert llm_response_plan.mode == "llm_response"
    assert [step.kind for step in llm_response_plan.steps] == [
        "llm_response",
        "verification",
        "respond",
    ]

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

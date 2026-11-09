"""Validate the intent metadata exposed by every registered pipeline."""

from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.infrastructure.pipeline_engine import service


EXPECTED_PIPELINES = {
    "bacterial_biosynthetic_gene_clusters",
    "bacterial_defense_system_annotation",
    "bacterial_secretion_system_annotation",
    "bacterial_viral_variant_analysis",
    "genomic_pathogen_identification",
    "metagenomic_de_novo_assembly",
    "metagenomic_growth_rate_Calculation",
    "metagenomic_pathogen_identification",
    "metagenomic_pathogen_identification_kmer",
    "metagenomic_pathogen_identification_marker",
    "metagenomic_qc_UniVec_Host",
    "metagenomic_read_quality_control",
    "metax_classification_abundance_analysis",
    "pathogen_variant_risk_assessment",
    "pathogen_variant_risk_assessment_consensus",
    "phi_annotator_genome",
    "phi_annotator_metagenome",
    "risk_screen",
    "tcdb_annotator_genome",
    "tcdb_annotator_metagenome",
    "template_bio",
    "template_nextflow",
    "template_shell",
    "template_snakemake",
    "template_wdl",
    "traceback_covid19",
    "viral_genome_molecular_typing",
    "viral_read_molecular_typing",
}


def main() -> int:
    catalog = service.catalog()
    names = {entry["name"] for entry in catalog}
    assert names == EXPECTED_PIPELINES, sorted(names ^ EXPECTED_PIPELINES)
    assert all("error" not in entry for entry in catalog), catalog
    assert all(entry["display_name"] for entry in catalog)
    assert all(entry["description"] for entry in catalog)
    assert all(entry["use_when"] for entry in catalog)
    assert all(entry["avoid_when"] for entry in catalog)
    assert all(entry["input_summary"] for entry in catalog)
    assert all(entry["output_summary"] for entry in catalog)
    assert all(entry["limitations"] for entry in catalog)
    assert all(entry["execution"]["boundary"] == "container" for entry in catalog)
    print(f"pipeline catalog metadata: {len(catalog)} pipelines ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

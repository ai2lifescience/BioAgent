"""Validate the intent metadata exposed by every registered pipeline."""

from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.runtime_tools.pipeline_runtime import service


EXPECTED_PIPELINES = {
    "antimicrobial_resistance_detection",
    "bacterial_functional_annotation",
    "bacterial_genome_annotation",
    "bacterial_genome_mutation_analysis",
    "bacterial_read_variant_analysis",
    "bacterial_virulence_factor_detection",
    "dna_analysis_demo",
    "metagenomic_de_novo_assembly",
    "metagenomic_pathogen_identification",
    "metagenomic_read_quality_control",
    "pathogen_variant_risk_assessment",
    "rna_secondary_structure_prediction",
    "sequence_metadata_assignment",
    "sequence_normalization_nextflow_demo",
    "sequence_normalization_snakemake_demo",
    "sequence_normalization_wdl_demo",
    "sequence_qc_demo",
    "viral_genome_mutation_analysis",
    "viral_molecular_typing",
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

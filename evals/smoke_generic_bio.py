"""No-network smoke check for the generic bioinformatics demo pipeline."""

from __future__ import annotations

from pathlib import Path
import sys
from tempfile import TemporaryDirectory


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.pipeline_runner.core import run_pipeline
from agent_core.artifacts import artifact_content_type, can_serve_artifact


def main() -> int:
    pipeline_dir = PROJECT_ROOT / "pipelines" / "generic_bio"
    with TemporaryDirectory(prefix="bioagent-generic-bio-") as artifact_dir:
        result = run_pipeline(
            pipeline_name="generic_bio",
            artifact_dir=artifact_dir,
            run_id="smoke",
            input_overrides={
                "reads": str(pipeline_dir / "data/input/example_reads.fastq"),
                "reference": str(pipeline_dir / "data/input/example_reference.fasta"),
                "metadata": str(pipeline_dir / "data/input/example_samples.tsv"),
            },
        )

        assert result["status"] == "ok"
        assert result["metrics"]["input_read_count"] == 5
        assert result["metrics"]["passed_read_count"] == 3
        assert result["metrics"]["variant_count"] == 1
        assert len(result["output_records"]) == 16
        assert result["metrics"]["phylogenetic_tree_emitted"] is True
        assert all(record["exists"] for record in result["output_records"])
        optional_records = [record for record in result["output_records"] if not record["required"]]
        assert {record["name"] for record in optional_records} == {
            "phylogenetic_tree",
            "phylogenetic_tree_figure",
        }

        output_paths = {Path(path).name: Path(path) for path in result["files"]}
        assert set(output_paths) == {
            "report.md",
            "report.html",
            "metrics.json",
            "filtered_reads.fastq",
            "read_qc.tsv",
            "sample_summary.tsv",
            "coverage.tsv",
            "alignments.sam",
            "consensus.fasta",
            "variants.vcf",
            "variant_summary.tsv",
            "qc_overview.png",
            "coverage.png",
            "variant_allele_fraction.png",
            "phylogenetic_tree.nwk",
            "phylogenetic_tree.png",
        }
        assert all(can_serve_artifact(path) for path in output_paths.values())
        assert "demo_reference\t8\t.\tT\tA" in output_paths["variants.vcf"].read_text(
            encoding="utf-8"
        )
        assert output_paths["qc_overview.png"].stat().st_size > 1_000
        assert can_serve_artifact(output_paths["qc_overview.png"])
        assert artifact_content_type(output_paths["qc_overview.png"]) == "image/png"
        assert can_serve_artifact(output_paths["report.html"])
        assert artifact_content_type(output_paths["report.html"]) == "text/html; charset=utf-8"
        assert "Generic Bioinformatics Pipeline Report" in output_paths["report.html"].read_text(
            encoding="utf-8"
        )
        assert can_serve_artifact(output_paths["phylogenetic_tree.nwk"])
        assert artifact_content_type(output_paths["phylogenetic_tree.nwk"]) == "text/plain; charset=utf-8"
        newick = output_paths["phylogenetic_tree.nwk"].read_text(encoding="utf-8")
        assert "demo_reference" in newick
        assert "sample_demo_consensus" in newick
        assert output_paths["phylogenetic_tree.png"].stat().st_size > 1_000

        no_tree_result = run_pipeline(
            pipeline_name="generic_bio",
            artifact_dir=artifact_dir,
            run_id="smoke-no-tree",
            input_overrides={
                "reads": str(pipeline_dir / "data/input/example_reads.fastq"),
                "reference": str(pipeline_dir / "data/input/example_reference.fasta"),
                "metadata": str(pipeline_dir / "data/input/example_samples.tsv"),
            },
            config_overrides={"emit_phylogenetic_tree": False},
        )
        assert no_tree_result["metrics"]["phylogenetic_tree_emitted"] is False
        assert all(
            record["exists"]
            for record in no_tree_result["output_records"]
            if record["required"]
        )
        no_tree_optional = [
            record for record in no_tree_result["output_records"] if not record["required"]
        ]
        assert not any(record["exists"] for record in no_tree_optional)
        no_tree_names = {Path(path).name for path in no_tree_result["files"]}
        assert "phylogenetic_tree.nwk" not in no_tree_names
        assert "phylogenetic_tree.png" not in no_tree_names
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

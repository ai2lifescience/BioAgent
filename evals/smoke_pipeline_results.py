"""End-to-end smoke check for explicit pipeline result collection."""

from __future__ import annotations

from pathlib import Path
import sys
import zipfile


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent_core import BioAgentOrchestrator
from agent_core.artifacts import SessionArtifactStore
from agent_core.memory import InMemoryStateStore
from agent_core.trace import InMemoryTraceStore


def main() -> int:
    memory = InMemoryStateStore()
    artifacts = SessionArtifactStore(memory)
    orchestrator = BioAgentOrchestrator(
        memory=memory,
        trace_store=InMemoryTraceStore(),
        artifact_store=artifacts,
    )
    pipeline_dir = PROJECT_ROOT / "pipelines" / "generic_bio" / "data" / "input"
    reads_path = pipeline_dir / "example_reads.fastq"
    reference_path = pipeline_dir / "example_reference.fasta"
    metadata_path = pipeline_dir / "example_samples.tsv"
    run_result = orchestrator.run(
        user_request=(
            "Run pipeline with pipeline_name: generic_bio "
            f'reads: "{reads_path}" '
            f'reference: "{reference_path}" '
            f'metadata: "{metadata_path}" '
            "emit_phylogenetic_tree true"
        )
    )
    assert run_result["route"]["skill_name"] == "pipeline_runner"
    assert "previews are hidden by default" in run_result["answer"]

    collected = orchestrator.run(
        user_request="Collect and show all results from the generic_bio pipeline run",
        session_id=run_result["session_id"],
    )
    assert collected["route"]["skill_name"] == "pipeline_results"
    assert "# Collected generic_bio results" in collected["answer"]
    assert "## Key metrics" in collected["answer"]
    assert "## read_qc.tsv" in collected["answer"]
    assert "## Output manifest" in collected["answer"]
    assert "phylogenetic_tree.nwk" in collected["answer"]

    current_artifacts = collected.get("artifacts") or []
    images = [artifact for artifact in current_artifacts if artifact.get("kind") == "image"]
    bundles = [artifact for artifact in current_artifacts if artifact.get("kind") == "compressed"]
    assert len(images) == 4
    assert len(bundles) == 1
    assert Path(bundles[0]["path"]).is_file()
    with zipfile.ZipFile(bundles[0]["path"]) as archive:
        assert "phylogenetic_tree.nwk" in archive.namelist()
        assert "phylogenetic_tree.png" in archive.namelist()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

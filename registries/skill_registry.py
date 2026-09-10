"""Central registry for high-level skills."""

from __future__ import annotations

from typing import Any, Callable

from skills.base import SkillDefinition
from skills.ask_user import SKILL_SPEC as ASK_USER_SPEC, ask_user
from skills.bio_database_search import SKILL_SPEC as DATABASE_LOOKUP_SPEC, database_lookup
from skills.blast_search import SKILL_SPEC as BLAST_SEARCH_SPEC, blast_search
from skills.example_skill import SKILL_SPEC as EXAMPLE_SPEC, example_skill
from skills.file_inspection import SKILL_SPEC as FILE_INSPECTION_SPEC, file_inspection
from skills.genome_map import SKILL_SPEC as GENOME_MAP_SPEC, genome_map
from skills.ncbi_retrieval import SKILL_SPEC as NCBI_RETRIEVAL_SPEC, ncbi_retrieval
from skills.pdb_download import SKILL_SPEC as PDB_DOWNLOAD_SPEC, pdb_download
from skills.pipeline_runner import SKILL_SPEC as PIPELINE_RUNNER_SPEC, pipeline_runner
from skills.pipeline_results import SKILL_SPEC as PIPELINE_RESULTS_SPEC, pipeline_results
from skills.sequence_analysis import SKILL_SPEC as SEQUENCE_ANALYSIS_SPEC, sequence_analysis
from skills.species_report.workflow import SKILL_SPEC as SPECIES_REPORT_SPEC, species_report
from skills.protein_structure_analysis import SKILL_SPEC as PROTEIN_STRUCTURE_ANALYSIS_SPEC, protein_structure_analysis


SKILL_DEFINITIONS = [
    SkillDefinition(
        skill_spec=ASK_USER_SPEC,
        handler=ask_user,
        category="interaction",
        tools=("ask_user",),
        instruction_path="skills/ask_user/SKILL.md",
    ),
    SkillDefinition(
        skill_spec=EXAMPLE_SPEC,
        handler=example_skill,
        category="diagnostics",
        tools=("echo",),
        instruction_path="skills/example_skill/SKILL.md",
    ),
    SkillDefinition(
        skill_spec=PIPELINE_RUNNER_SPEC,
        handler=pipeline_runner,
        category="pipeline",
        tools=("pipeline_runner",),
        instruction_path="skills/pipeline_runner/SKILL.md",
    ),
    SkillDefinition(
        skill_spec=PIPELINE_RESULTS_SPEC,
        handler=pipeline_results,
        category="pipeline",
        tools=("pipeline_results_collect",),
        instruction_path="skills/pipeline_results/SKILL.md",
    ),
    SkillDefinition(
        skill_spec=SPECIES_REPORT_SPEC,
        handler=species_report,
        category="retrieval",
        tools=(
            "pubmed_collect",
            "trusted_web_collect",
            "rag_chunk",
            "rag_store",
            "rag_retrieve",
            "rag_citations",
            "species_model_opinions",
            "species_report_synthesis",
            "markdown_report_writer",
        ),
        instruction_path="skills/species_report/SKILL.md",
    ),
    SkillDefinition(
        skill_spec=NCBI_RETRIEVAL_SPEC,
        handler=ncbi_retrieval,
        category="bio_data",
        tools=("ncbi_fetch",),
        instruction_path="skills/ncbi_retrieval/SKILL.md",
    ),
    SkillDefinition(
        skill_spec=DATABASE_LOOKUP_SPEC,
        handler=database_lookup,
        category="bio_api",
        tools=("bio_database_search",),
        instruction_path="skills/bio_database_search/SKILL.md",
    ),
    SkillDefinition(
        skill_spec=PDB_DOWNLOAD_SPEC,
        handler=pdb_download,
        category="bio_api",
        tools=("pdb_download",),
        instruction_path="skills/pdb_download/SKILL.md",
    ),
    SkillDefinition(
        skill_spec=SEQUENCE_ANALYSIS_SPEC,
        handler=sequence_analysis,
        category="bio_tool",
        tools=("sequence_analyze",),
        instruction_path="skills/sequence_analysis/SKILL.md",
    ),
    SkillDefinition(
        skill_spec=GENOME_MAP_SPEC,
        handler=genome_map,
        category="bio_tool",
        tools=("genome_map",),
        instruction_path="skills/genome_map/SKILL.md",
    ),
    SkillDefinition(
        skill_spec=PROTEIN_STRUCTURE_ANALYSIS_SPEC,
        handler=protein_structure_analysis,
        category="bio_tool",
        tools=("pdb_download", "protein_structure_analyze"),
        instruction_path="skills/protein_structure_analysis/SKILL.md",
    ),
    SkillDefinition(
        skill_spec=BLAST_SEARCH_SPEC,
        handler=blast_search,
        category="bio_tool",
        tools=("blast_search",),
        instruction_path="skills/blast_search/SKILL.md",
    ),
    SkillDefinition(
        skill_spec=FILE_INSPECTION_SPEC,
        handler=file_inspection,
        category="file_io",
        tools=("file_inspect",),
        instruction_path="skills/file_inspection/SKILL.md",
    ),
]

SKILL_SPECS = [skill.skill_spec for skill in SKILL_DEFINITIONS]

SKILLS: dict[str, Callable[..., dict[str, Any]]] = {
    skill.name: skill.handler for skill in SKILL_DEFINITIONS
}


def get_skill_definition(name: str) -> SkillDefinition | None:
    for skill in SKILL_DEFINITIONS:
        if skill.name == name:
            return skill
    return None


def list_skill_names() -> list[str]:
    return [skill.name for skill in SKILL_DEFINITIONS]


def list_skill_prompt_hints() -> list[str]:
    """Return model-facing skill descriptions from registered skill specs."""
    hints: list[str] = []
    for skill in SKILL_DEFINITIONS:
        function = skill.skill_spec.get("function", {})
        description = str(function.get("description") or "").strip()
        if not description:
            description = f"Registered {skill.category} skill."
        tool_text = f" Tools: {', '.join(skill.tools)}." if skill.tools else ""
        hints.append(f"- {skill.name}: {description}{tool_text}")
    return hints

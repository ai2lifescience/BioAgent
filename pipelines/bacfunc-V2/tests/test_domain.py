from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
import yaml

from bacfunc.config import load_config
from bacfunc.eggnog import (
    REQUIRED_DATABASE_FILES,
    TERM_FIELDS,
    eggnog_command,
    expand_terms,
    parse_annotations,
    validate_database_path,
)

from bacfunc.read_search import (
    aggregate_annotations, annotation_command, diamond_command, parse_diamond,
    write_seed_orthologs,
)

ROOT = Path(__file__).resolve().parents[1]


def make_database(path: Path, version: str = "5.0-test") -> Path:
    path.mkdir(parents=True)
    connection = sqlite3.connect(path / "eggnog.db")
    connection.execute("CREATE TABLE version (version TEXT)")
    connection.execute("INSERT INTO version VALUES (?)", (version,))
    connection.commit()
    connection.close()
    for name in REQUIRED_DATABASE_FILES[1:]:
        (path / name).write_bytes(b"fixture")
    return path


def configured(tmp_path: Path, data_dir: Path) -> Path:
    data = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    data["pipeline"]["threads"] = 6
    data["databases"]["eggnog"]["data_dir"] = str(data_dir)
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


def test_four_files_sqlite_and_version_preflight(tmp_path: Path) -> None:
    data_dir = make_database(tmp_path / "eggnog data")
    result = validate_database_path(data_dir)
    assert result["detected_version"] == "5.0-test"
    assert set(result["files"]) == set(REQUIRED_DATABASE_FILES)
    (data_dir / "eggnog_proteins.dmnd").unlink()
    with pytest.raises(Exception, match="missing"):
        validate_database_path(data_dir)


def test_invalid_sqlite_is_rejected(tmp_path: Path) -> None:
    data_dir = tmp_path / "bad"
    data_dir.mkdir()
    for name in REQUIRED_DATABASE_FILES:
        (data_dir / name).write_bytes(b"not sqlite")
    with pytest.raises(Exception, match="SQLite"):
        validate_database_path(data_dir)


def test_eggnog_command_uses_data_dir_diamond_and_proteins(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    command = eggnog_command(
        tmp_path / "proteins.faa",
        tmp_path / "raw",
        "sample",
        load_config(configured(tmp_path, data_dir)),
    )
    assert command[command.index("--data_dir") + 1] == str(data_dir.resolve())
    assert command[command.index("-m") + 1] == "diamond"
    assert command[command.index("--itype") + 1] == "proteins"
    assert command[command.index("--cpu") + 1] == "6"


def test_dynamic_header_unknown_columns_and_missing_optional(tmp_path: Path) -> None:
    path = tmp_path / "a.emapper.annotations"
    path.write_text(
        "## emapper-2.1.15\n"
        "#query\tGOs\tKEGG_ko\tFuture_namespace\n"
        "g1\tGO:1,GO:2\tko:K00001\tFUT:1\n",
        encoding="utf-8",
    )
    header, rows = parse_annotations(path)
    assert header == ["query", "GOs", "KEGG_ko", "Future_namespace"]
    assert rows[0]["Future_namespace"] == "FUT:1"
    assert "EC" not in rows[0]
    terms = expand_terms(rows, "sample")
    assert {(item["namespace"], item["term_id"]) for item in terms} == {
        ("GO", "GO:1"),
        ("GO", "GO:2"),
        ("KEGG_KO", "ko:K00001"),
    }


def test_all_required_term_namespaces_and_empty_values() -> None:
    row = {
        "query": "g1",
        "GOs": "GO:1,GO:2",
        "COG_category": "CG",
        "eggNOG_OGs": "OG1@1,OG2@2",
        "EC": "1.1.1.1,2.2.2.2",
        "KEGG_ko": "ko:K1,ko:K2",
        "KEGG_Pathway": "map1",
        "KEGG_Module": "M1",
        "KEGG_Reaction": "R1",
        "KEGG_rclass": "RC1",
        "BRITE": "br1",
        "KEGG_TC": "TC1",
        "CAZy": "GH1,GT2",
        "BiGG_Reaction": "BIGG1",
        "PFAMs": "PF1,PF2",
        "Description": "description",
        "Preferred_name": "name",
    }
    terms = expand_terms([row, {"query": "g2", "GOs": "-", "EC": ""}], "s")
    namespaces = {item["namespace"] for item in terms}
    assert namespaces == {
        "GO", "COG_CATEGORY", "EGGNOG_OG", "EC", "KEGG_KO",
        "KEGG_PATHWAY", "KEGG_MODULE", "KEGG_REACTION", "KEGG_RCLASS",
        "BRITE", "KEGG_TC", "CAZY", "BIGG_REACTION", "PFAM",
    }
    assert terms == sorted(
        terms,
        key=lambda item: (
            item["gene_id"], item["namespace"], item["term_id"], item["source_column"]
        ),
    )
    assert TERM_FIELDS == [
        "sample_id", "gene_id", "namespace", "term_id", "term_name", "source_column"
    ]


def test_duplicate_terms_are_deduplicated() -> None:
    terms = expand_terms(
        [{"query": "g", "GOs": "GO:1,GO:1", "EC": "1.1.1.1;1.1.1.1"}],
        "s",
    )
    assert len(terms) == 2


def test_missing_or_empty_annotation_header_errors(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(Exception, match="#query"):
        parse_annotations(empty)
    header_only = tmp_path / "header"
    header_only.write_text("#query\tGOs\n", encoding="utf-8")
    header, rows = parse_annotations(header_only)
    assert header == ["query", "GOs"] and rows == []


def test_no_legacy_224_pathway_catalog_is_packaged_or_generated() -> None:
    project = Path(__file__).resolve().parents[1]
    assert not (project / "data" / "reference" / "selected_pathways.tsv").exists()
    assert not any("224" in path.name for path in project.rglob("*") if path.is_file())

def test_reads_translated_search_commands_parser_and_aggregation(tmp_path: Path) -> None:
    data_dir = make_database(tmp_path / "eggnog reads")
    config = load_config(configured(tmp_path, data_dir))
    query = tmp_path / "reads.fasta"
    raw = tmp_path / "reads.tsv"
    command = diamond_command(query, raw, config)
    assert command[:2] == ["diamond", "blastx"]
    assert command[command.index("--db") + 1] == str(data_dir / "eggnog_proteins.dmnd")
    assert command[command.index("--threads") + 1] == "6"
    raw.write_text(
        "q1\thit1\t90\t30\t90\t100\t1e-20\t100\n"
        "q2\thit1\t80\t24\t90\t100\t1e-10\t80\n",
        encoding="utf-8",
    )
    hits = parse_diamond(raw)
    seed = write_seed_orthologs(tmp_path / "seed.tsv", hits)
    annotate = annotation_command(seed, tmp_path, "sample", config)
    assert annotate[annotate.index("-m") + 1] == "no_search"
    assert annotate[annotate.index("--annotate_hits_table") + 1] == str(seed)
    header = ["query", "seed_ortholog", "GOs", "Preferred_name", "Description"]
    source_rows = [
        {"query": "q1", "seed_ortholog": "hit1", "GOs": "GO:1", "Preferred_name": "abc", "Description": "function"},
        {"query": "q2", "seed_ortholog": "hit1", "GOs": "GO:1", "Preferred_name": "abc", "Description": "function"},
    ]
    output_header, rows = aggregate_annotations(header, source_rows, hits)
    assert len(rows) == 1
    assert rows[0]["query"] == rows[0]["accession"] == "hit1"
    assert rows[0]["supporting_reads"] == 2
    assert rows[0]["mean_pct_identity"] == 85.0
    assert "mean_query_coverage" in output_header

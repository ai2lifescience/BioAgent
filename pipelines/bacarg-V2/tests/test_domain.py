from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

from bacarg.abricate import ARG_FIELDS, abricate_command, enrich_hits, parse_abricate
from bacarg.config import load_config
from bacarg.gff import add_context, load_cds
from bacarg.metadata import load_metadata
from bacarg.read_mapping import minimap2_command, parse_paf, reference_sequences
from scripts.prepare_megares_v3 import prepare_database


ROOT = Path(__file__).resolve().parents[1]


def configured(tmp_path: Path) -> Path:
    data = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    data["pipeline"]["threads"] = 3
    data["databases"] = {
        "abricate_datadir": "db root",
        "metadata": "meta.tsv",
        "manifest": None,
    }
    data["tools"]["abricate"].update(
        {"database_name": "custom_megares", "min_identity": 81.25, "min_coverage": 62.5}
    )
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


def test_abricate_command_uses_all_deployment_values(tmp_path: Path) -> None:
    config = load_config(configured(tmp_path))
    command = abricate_command(tmp_path / "assembly.fa", config)
    assert command[command.index("--datadir") + 1] == str((tmp_path / "db root").resolve())
    assert command[command.index("--db") + 1] == "custom_megares"
    assert command[command.index("--minid") + 1] == "81.25"
    assert command[command.index("--mincov") + 1] == "62.5"
    assert command[command.index("--threads") + 1] == "3"


def test_header_based_parsing_empty_multiple_and_strands(tmp_path: Path) -> None:
    path = tmp_path / "hits.tsv"
    path.write_text(
        "#FILE\tGENE\tEND\tSEQUENCE\tSTART\tACCESSION\t%IDENTITY\t%COVERAGE\tSTRAND\tPRODUCT\n"
        "a\tg2\t10\tc2\t30\tACC2\t99.123\t80.5\t-\tp2\n"
        "a\tg1\t20\tc1\t5\t.\t90.0\t70.0\t+\tp1\n",
        encoding="utf-8",
    )
    rows = parse_abricate(path)
    assert rows[0]["start"] == 10
    assert rows[0]["end"] == 30
    assert rows[0]["strand"] == "-"
    assert rows[1]["accession"] == ""
    empty = tmp_path / "empty.tsv"
    empty.write_text("#FILE\tSEQUENCE\tSTART\tEND\tGENE\n", encoding="utf-8")
    assert parse_abricate(empty) == []


def test_metadata_alias_bom_join_hierarchy_and_duplicate(tmp_path: Path) -> None:
    metadata = tmp_path / "metadata.csv"
    metadata.write_text(
        "\ufeffAccession Number,Gene Name,Type,Drug Class,Resistance Mechanism,Gene Group,SNP Confirmation Required\n"
        "ACC1.1,blaX,beta-lactam,beta-lactams,enzyme,g1,yes\n",
        encoding="utf-8",
    )
    loaded = load_metadata(metadata)
    warnings: list[str] = []
    rows = enrich_hits(
        [{"contig": "c", "start": 1, "end": 10, "strand": "+", "gene": "blaX", "accession": "ACC1"}],
        loaded,
        "s",
        "megares_v3",
        "3.0",
        warnings,
    )
    assert rows[0]["compound_type"] == "beta-lactam"
    assert rows[0]["mechanism"] == "enzyme"
    assert rows[0]["requires_snp_confirmation"] == "true"
    assert rows[0]["snp_status"] == "not_evaluated"
    assert rows[0]["final_call"] == "candidate_hit"
    assert warnings == []
    duplicate = tmp_path / "duplicate.tsv"
    duplicate.write_text("accession\nACC1\nACC1.2\n", encoding="utf-8")
    with pytest.raises(Exception, match="Duplicate"):
        load_metadata(duplicate)


def test_unmatched_accession_is_retained_with_warning() -> None:
    warnings: list[str] = []
    rows = enrich_hits(
        [{"contig": "c", "start": 2, "end": 3, "strand": "+", "gene": "x", "accession": "NOPE"}],
        {},
        "sample",
        "megares_v3",
        "3.0",
        warnings,
    )
    assert rows[0]["accession"] == "NOPE"
    assert warnings and "did not match" in warnings[0]


def test_gff_overlap_context_and_stable_columns(tmp_path: Path) -> None:
    gff = tmp_path / "genes.gff"
    gff.write_text(
        "##gff-version 3\n"
        "c\tProkka\tCDS\t1\t100\t.\t+\t0\tID=L1;locus_tag=L1;gene=abc;product=Protein%20A\n",
        encoding="utf-8",
    )
    rows = add_context(
        [{"contig": "c", "start": 20, "end": 40, "gene": "hit"}], load_cds(gff)
    )
    assert rows[0]["locus_tag"] == "L1"
    assert rows[0]["prokka_product"] == "Protein A"
    assert ARG_FIELDS == [
        "sample_id", "contig", "start", "end", "strand", "gene", "accession",
        "product", "compound_type", "class", "mechanism", "group", "resistance",
        "pct_identity", "pct_coverage", "coverage", "gaps", "supporting_reads",
        "depth", "database_name", "database_version", "locus_tag", "prokka_gene",
        "prokka_product", "requires_snp_confirmation", "snp_status", "final_call",
    ]




def test_prepare_database_rewrites_header_and_builds_indexes(tmp_path: Path) -> None:
    fasta = tmp_path / "official.fa"
    fasta.write_text(">ACC1\nACGT\n", encoding="utf-8")
    metadata = tmp_path / "official.tsv"
    metadata.write_text(
        "accession\tgene\tclass\tproduct\nACC1\tblaX\tbeta-lactam\tprotein X\n",
        encoding="utf-8",
    )
    script = tmp_path / "fake_makeblastdb.py"
    script.write_text(
        "import sys\nfrom pathlib import Path\n"
        "args=sys.argv[1:]\nout=Path(args[args.index('-out')+1])\n"
        "[(Path(str(out)+s)).write_text('index',encoding='utf-8') for s in ('.nhr','.nin','.nsq')]\n",
        encoding="utf-8",
    )
    command = prepare_database(
        fasta,
        metadata,
        tmp_path / "db root",
        makeblastdb=sys.executable,
        makeblastdb_prefix_options=[str(script)],
    )
    target = tmp_path / "db root" / "megares_v3"
    assert "megares_v3~~~blaX~~~ACC1~~~beta-lactam" in (
        target / "sequences"
    ).read_text(encoding="utf-8")
    assert (target / "sequences.nhr").is_file()
    assert command[0] == sys.executable
    manifest = json.loads((target / "database_manifest.json").read_text(encoding="utf-8"))
    assert manifest["record_count"] == 1


def test_gff_parser_stops_at_embedded_fasta(tmp_path: Path) -> None:
    gff = tmp_path / "embedded.gff"
    gff.write_text(
        "##gff-version 3\n"
        "contig1\tProkka\tCDS\t1\t4\t.\t+\t0\tID=L1;locus_tag=L1\n"
        "##FASTA\n"
        ">contig1\n"
        "ACGT\n",
        encoding="utf-8",
    )
    parsed = load_cds(gff)
    assert parsed["contig1"][0]["locus_tag"] == "L1"

def test_reads_mapping_command_and_paf_aggregation(tmp_path: Path) -> None:
    config = load_config(configured(tmp_path))
    reference = reference_sequences(config)
    command = minimap2_command(
        [tmp_path / "trimmed_R1.fastq.gz", tmp_path / "trimmed_R2.fastq.gz"],
        reference,
        config,
    )
    assert command[0] == "minimap2"
    assert command[command.index("-t") + 1] == "3"
    assert command[-3] == str(reference)
    paf = tmp_path / "hits.paf"
    target = "custom_megares~~~blaX~~~ACC1~~~beta-lactam"
    paf.write_text(
        f"r1\t100\t0\t60\t+\t{target}\t100\t0\t60\t58\t60\t60\n"
        f"r2\t100\t0\t60\t+\t{target}\t100\t40\t100\t55\t60\t60\n",
        encoding="utf-8",
    )
    rows = parse_paf(paf, config)
    assert len(rows) == 1
    assert rows[0]["gene"] == "blaX" and rows[0]["accession"] == "ACC1"
    assert rows[0]["supporting_reads"] == 2
    assert rows[0]["pct_coverage"] == 100.0 and rows[0]["depth"] == 1.2
    assert rows[0]["contig"] == rows[0]["start"] == rows[0]["strand"] == ""
    assert "supporting_reads" in ARG_FIELDS and "depth" in ARG_FIELDS


def test_empty_reads_mapping_is_a_valid_zero_hit_result(tmp_path: Path) -> None:
    empty = tmp_path / "empty.paf"
    empty.write_text("", encoding="utf-8")
    assert parse_paf(empty, load_config(configured(tmp_path))) == []

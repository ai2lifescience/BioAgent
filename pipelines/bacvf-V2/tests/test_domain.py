from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

from bacvf.abricate import VF_FIELDS, abricate_command, enrich_hits, parse_abricate
from bacvf.config import load_config
from bacvf.gff import add_context, load_cds
from bacvf.metadata import load_metadata
from bacvf.read_mapping import minimap2_command, parse_paf, reference_sequences
from scripts.prepare_vfdb_core import prepare_database


ROOT = Path(__file__).resolve().parents[1]


def configured(tmp_path: Path) -> Path:
    data = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    data["pipeline"]["threads"] = 4
    data["databases"] = {
        "abricate_datadir": "db",
        "metadata": "vf-meta.tsv",
        "manifest": None,
    }
    data["tools"]["abricate"].update(
        {"database_name": "my_vfdb_core", "min_identity": 82, "min_coverage": 64}
    )
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


def test_custom_vfdb_core_command_and_thresholds(tmp_path: Path) -> None:
    command = abricate_command(tmp_path / "a.fa", load_config(configured(tmp_path)))
    assert command[command.index("--db") + 1] == "my_vfdb_core"
    assert command[command.index("--db") + 1] != "vfdb"
    assert command[command.index("--datadir") + 1] == str((tmp_path / "db").resolve())
    assert command[command.index("--minid") + 1] == "82"
    assert command[command.index("--mincov") + 1] == "64"
    assert command[command.index("--threads") + 1] == "4"


def test_dynamic_abricate_parse_empty_and_sort(tmp_path: Path) -> None:
    path = tmp_path / "hits.tsv"
    path.write_text(
        "#FILE\tGENE\tEND\tSEQUENCE\tSTART\tACCESSION\t%IDENTITY\t%COVERAGE\tSTRAND\n"
        "a\tz\t20\tc2\t30\tA2\t99.2\t80.1\t-\n"
        "a\ta\t10\tc1\t1\tA1\t90\t70\t+\n",
        encoding="utf-8",
    )
    parsed = parse_abricate(path)
    warnings: list[str] = []
    rows = enrich_hits(parsed, {}, "s", "vfdb_core", "core", warnings)
    assert [row["contig"] for row in rows] == ["c1", "c2"]
    assert rows[1]["start"] == 20 and rows[1]["end"] == 30
    empty = tmp_path / "empty.tsv"
    empty.write_text("#FILE\tSEQUENCE\tSTART\tEND\tGENE\n", encoding="utf-8")
    assert parse_abricate(empty) == []


def test_metadata_join_categories_pathogen_and_unmatched(tmp_path: Path) -> None:
    path = tmp_path / "vf.csv"
    path.write_text(
        "\ufeffGenBank Accession,VFID,Gene Name,VF Name,VF Category,VF Subcategory,Pathogen\n"
        "ACC1.1,VF0001,fimH,Type 1 fimbrial adhesin,Adherence,Fimbriae,Escherichia coli\n",
        encoding="utf-8",
    )
    metadata = load_metadata(path)
    warnings: list[str] = []
    rows = enrich_hits(
        [
            {"contig": "c", "start": 1, "end": 10, "strand": "+", "gene": "fimH", "accession": "ACC1"},
            {"contig": "d", "start": 2, "end": 8, "strand": "+", "gene": "x", "accession": "MISS"},
        ],
        metadata,
        "sample",
        "vfdb_core",
        "2026-01",
        warnings,
    )
    assert rows[0]["vf_id"] == "VF0001"
    assert rows[0]["category"] == "Adherence"
    assert rows[0]["subcategory"] == "Fimbriae"
    assert rows[0]["associated_pathogen"] == "Escherichia coli"
    assert rows[1]["accession"] == "MISS"
    assert warnings and "did not match" in warnings[0]


def test_missing_join_and_duplicate_fail(tmp_path: Path) -> None:
    missing = tmp_path / "missing.tsv"
    missing.write_text("gene\tcategory\nx\ty\n", encoding="utf-8")
    with pytest.raises(Exception, match="accession"):
        load_metadata(missing)
    duplicate = tmp_path / "duplicate.tsv"
    duplicate.write_text("accession\tgene\nA1\tx\nA1.2\ty\n", encoding="utf-8")
    with pytest.raises(Exception, match="Duplicate"):
        load_metadata(duplicate)


def test_prokka_context_and_output_columns(tmp_path: Path) -> None:
    gff = tmp_path / "p.gff"
    gff.write_text(
        "c\tProkka\tCDS\t1\t50\t.\t+\t0\tID=L1;locus_tag=L1;gene=fimH;product=adhesin\n",
        encoding="utf-8",
    )
    row = add_context(
        [{"contig": "c", "start": 2, "end": 40}], load_cds(gff)
    )[0]
    assert row["locus_tag"] == "L1"
    assert "associated_pathogen" in VF_FIELDS
    assert VF_FIELDS == [
        "sample_id", "contig", "start", "end", "strand", "vf_id", "gene",
        "accession", "factor_name", "category", "subcategory", "associated_pathogen",
        "product", "pct_identity", "pct_coverage", "coverage", "gaps",
        "supporting_reads", "depth", "database_name", "database_version", "locus_tag",
        "prokka_gene", "prokka_product",
    ]



def test_prepare_vfdb_core_script(tmp_path: Path) -> None:
    fasta = tmp_path / "core.fa"
    fasta.write_text(">ACC1\nACGT\n", encoding="utf-8")
    metadata = tmp_path / "core.tsv"
    metadata.write_text(
        "accession\tgene\tfactor_name\tcategory\n"
        "ACC1\tfimH\tadhesin\tAdherence\n",
        encoding="utf-8",
    )
    fake = tmp_path / "makeblastdb.py"
    fake.write_text(
        "import sys\nfrom pathlib import Path\n"
        "a=sys.argv[1:]; out=Path(a[a.index('-out')+1])\n"
        "[(Path(str(out)+s)).write_text('i',encoding='utf-8') for s in ('.nhr','.nin','.nsq')]\n",
        encoding="utf-8",
    )
    prepare_database(
        fasta,
        metadata,
        tmp_path / "datadir",
        makeblastdb=sys.executable,
        makeblastdb_prefix_options=[str(fake)],
    )
    target = tmp_path / "datadir" / "vfdb_core"
    assert "vfdb_core~~~fimH~~~ACC1~~~Adherence" in (
        target / "sequences"
    ).read_text(encoding="utf-8")
    manifest = json.loads((target / "database_manifest.json").read_text(encoding="utf-8"))
    assert manifest["database_name"] == "vfdb_core"


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
    assert command[command.index("-t") + 1] == "4"
    assert command[-3] == str(reference)
    paf = tmp_path / "hits.paf"
    target = "my_vfdb_core~~~toxA~~~VF001~~~adhesion"
    paf.write_text(
        f"r1\t100\t0\t60\t+\t{target}\t100\t0\t60\t58\t60\t60\n"
        f"r2\t100\t0\t60\t+\t{target}\t100\t40\t100\t55\t60\t60\n",
        encoding="utf-8",
    )
    rows = parse_paf(paf, config)
    assert len(rows) == 1
    assert rows[0]["gene"] == "toxA" and rows[0]["accession"] == "VF001"
    assert rows[0]["supporting_reads"] == 2
    assert rows[0]["pct_coverage"] == 100.0 and rows[0]["depth"] == 1.2
    assert rows[0]["contig"] == rows[0]["start"] == rows[0]["strand"] == ""
    assert "supporting_reads" in VF_FIELDS and "depth" in VF_FIELDS


def test_empty_reads_mapping_is_a_valid_zero_hit_result(tmp_path: Path) -> None:
    empty = tmp_path / "empty.paf"
    empty.write_text("", encoding="utf-8")
    assert parse_paf(empty, load_config(configured(tmp_path))) == []

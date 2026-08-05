from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import yaml

from bacfunc.eggnog import REQUIRED_DATABASE_FILES
from bacfunc.pipeline import run_pipeline


ROOT = Path(__file__).resolve().parents[1]


def _database(path: Path) -> Path:
    path.mkdir()
    connection = sqlite3.connect(path / "eggnog.db")
    connection.execute("CREATE TABLE version (version TEXT)")
    connection.execute("INSERT INTO version VALUES ('5-fixture')")
    connection.commit()
    connection.close()
    for name in REQUIRED_DATABASE_FILES[1:]:
        (path / name).write_bytes(b"fixture")
    return path


def _fake_tools(path: Path) -> Path:
    script = path / "fake tools.py"
    script.write_text(
        "import sys\nfrom pathlib import Path\n"
        "tool=sys.argv[1]; a=sys.argv[2:]\n"
        "if tool=='trimmomatic':\n"
        "  idx=(5,6,7,8) if a[0]=='PE' else (4,)\n"
        "  [Path(a[i]).parent.mkdir(parents=True,exist_ok=True) for i in idx]\n"
        "  [Path(a[i]).write_text('@r\\nACGT\\n+\\nIIII\\n',encoding='utf-8') for i in idx]\n"
        "elif tool=='metaspades':\n"
        "  out=Path(a[a.index('-o')+1]); out.mkdir(parents=True,exist_ok=True); (out/'contigs.fasta').write_text('>contig1\\nACGTACGTACGT\\n',encoding='utf-8')\n"
        "elif tool=='prokka':\n"
        "  out=Path(a[a.index('--outdir')+1]); p=a[a.index('--prefix')+1]; out.mkdir(parents=True,exist_ok=True)\n"
        "  (out/(p+'.faa')).write_text('>L1\\nMKK\\n>L2\\nMNN\\n',encoding='utf-8'); (out/(p+'.ffn')).write_text('>L1\\nATGAAA\\n',encoding='utf-8')\n"
        "  (out/(p+'.gff')).write_text('contig1\\tProkka\\tCDS\\t1\\t6\\t.\\t+\\t0\\tID=L1;locus_tag=L1\\n',encoding='utf-8')\n"
        "  (out/(p+'.tsv')).write_text('locus_tag\\nL1\\n',encoding='utf-8'); (out/(p+'.txt')).write_text('ok\\n',encoding='utf-8')\n"
        "elif tool=='reads_search':\n"
        "  out=Path(a[a.index('--out')+1]); out.parent.mkdir(parents=True,exist_ok=True)\n"
        "  content='' if '--no-hits' in a else 'R1_1_r\\thit1\\t90\\t1\\t4\\t100\\t1e-20\\t100\\nR2_1_r\\thit1\\t85\\t1\\t4\\t100\\t1e-10\\t80\\n'\n"
        "  out.write_text(content,encoding='utf-8')\n"
        "elif tool=='eggnog':\n"
        "  out=Path(a[a.index('--output_dir')+1]); p=a[a.index('--output')+1]; out.mkdir(parents=True,exist_ok=True)\n"
        "  content='## emapper\\n#query\\tseed_ortholog\\tGOs\\tEC\\tKEGG_ko\\tCAZy\\tPFAMs\\tPreferred_name\\tDescription\\nR1_1_r\\thit1\\tGO:1,GO:2\\t1.1.1.1\\tko:K1\\tGH1\\tPF1\\tabc\\tfunction\\nR2_1_r\\thit1\\tGO:1,GO:2\\t1.1.1.1\\tko:K1\\tGH1\\tPF1\\tabc\\tfunction\\n' if '--annotate_hits_table' in a else '## emapper\\n#query\\tGOs\\tEC\\tKEGG_ko\\tCAZy\\tPFAMs\\tFuture\\nL1\\tGO:1,GO:2\\t1.1.1.1\\tko:K1\\tGH1\\tPF1\\tX:1\\nL2\\t-\\t-\\t-\\t-\\t-\\tX:2\\n'\n"
        "  (out/(p+'.emapper.annotations')).write_text(content,encoding='utf-8')\n"
        "  (out/(p+'.emapper.seed_orthologs')).write_text('seed\\n',encoding='utf-8'); (out/(p+'.emapper.hits')).write_text('hits\\n',encoding='utf-8')\n"
        "else: raise SystemExit(7)\n",
        encoding="utf-8",
    )
    return script


def test_fake_tool_full_fastq_pipeline(tmp_path: Path) -> None:
    fake = _fake_tools(tmp_path)
    data = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    data["pipeline"]["threads"] = 2
    for name in ("trimmomatic", "reads_search", "assembler", "prokka", "eggnog"):
        data["tools"][name]["executable"] = sys.executable
        data["tools"][name]["prefix_options"] = [
            str(fake),
            name if name != "assembler" else "metaspades",
        ]
    data_dir = _database(tmp_path / "eggnog data")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"database_version": "5-fixture"}), encoding="utf-8")
    data["databases"]["eggnog"] = {
        "data_dir": str(data_dir),
        "manifest": str(manifest),
    }
    config = tmp_path / "integration.yaml"
    config.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    r1, r2 = tmp_path / "R1.fastq", tmp_path / "R2.fastq"
    r1.write_text("@r1\nACGT\n+\nIIII\n", encoding="utf-8")
    r2.write_text("@r2\nTGCA\n+\nIIII\n", encoding="utf-8")
    output = tmp_path / "output with spaces"
    status = run_pipeline([r1, r2], output, config_path=config)
    assert status["status"] == "success"
    assert status["gene_annotation_count"] == 2
    assert status["term_count"] == 6
    wide = (output / "gene_annotations.tsv").read_text(encoding="utf-8")
    assert "Future" in wide and "X:2" in wide
    terms = (output / "annotation_terms.tsv").read_text(encoding="utf-8")
    assert "GO:1" in terms and "GH1" in terms and "PF1" in terms
    assert not (output / ("selected" + "_pathways.tsv")).exists()
    assert not any("abundance" in path.name.lower() for path in output.iterdir())
    manifest_result = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert len(manifest_result["commands"]) == 4
    assert manifest_result["database"]["detected_version"] == "5-fixture"
    reads_output = tmp_path / "direct reads output"
    reads_status = run_pipeline(
        [r1, r2],
        reads_output,
        config_path=config,
        input_type="reads",
        analysis_mode="reads",
    )
    assert reads_status["status"] == "success"
    assert reads_status["gene_annotation_count"] == 1
    reads_wide = (reads_output / "gene_annotations.tsv").read_text(encoding="utf-8")
    assert "accession" in reads_wide and "supporting_reads" in reads_wide
    assert "hit1" in reads_wide and "\t2\t" in reads_wide
    reads_terms = (reads_output / "annotation_terms.tsv").read_text(encoding="utf-8")
    assert "hit1" in reads_terms and "GO:1" in reads_terms and "PF1" in reads_terms
    reads_manifest = json.loads((reads_output / "manifest.json").read_text(encoding="utf-8"))
    reads_qc = json.loads((reads_output / "qc.json").read_text(encoding="utf-8"))
    assert len(reads_manifest["commands"]) == 3
    command_text = " ".join(part for command in reads_manifest["commands"] for part in command).lower()
    assert "metaspades" not in command_text and "prokka" not in command_text
    assert reads_qc["assembly"]["source"] == "not_applicable"
    assert reads_qc["reads"]["trimmed"]["read_count"] == 2
    for name in ("status.json", "qc.json", "manifest.json"):
        assert json.loads((reads_output / name).read_text(encoding="utf-8"))
    reads_output = tmp_path / "direct reads output"
    reads_status = run_pipeline(
        [r1, r2],
        reads_output,
        config_path=config,
        input_type="reads",
        analysis_mode="reads",
    )
    assert reads_status["status"] == "success"
    assert reads_status["gene_annotation_count"] == 1
    reads_wide = (reads_output / "gene_annotations.tsv").read_text(encoding="utf-8")
    assert "accession" in reads_wide and "supporting_reads" in reads_wide
    assert "hit1" in reads_wide and "\t2\t" in reads_wide
    reads_terms = (reads_output / "annotation_terms.tsv").read_text(encoding="utf-8")
    assert "hit1" in reads_terms and "GO:1" in reads_terms and "PF1" in reads_terms
    reads_manifest = json.loads((reads_output / "manifest.json").read_text(encoding="utf-8"))
    reads_qc = json.loads((reads_output / "qc.json").read_text(encoding="utf-8"))
    assert len(reads_manifest["commands"]) == 3
    command_text = " ".join(part for command in reads_manifest["commands"] for part in command).lower()
    assert "metaspades" not in command_text and "prokka" not in command_text
    assert reads_qc["assembly"]["source"] == "not_applicable"
    assert reads_qc["reads"]["trimmed"]["read_count"] == 2
    for name in ("status.json", "qc.json", "manifest.json"):
        assert json.loads((reads_output / name).read_text(encoding="utf-8"))
    data["tools"]["reads_search"]["options"] = ["--no-hits"]
    no_hit_config = tmp_path / "no-hit.yaml"
    no_hit_config.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    no_hit_output = tmp_path / "no-hit-output"
    no_hit_status = run_pipeline(
        [r1, r2], no_hit_output, config_path=no_hit_config,
        input_type="reads", analysis_mode="reads",
    )
    assert no_hit_status["status"] == "success"
    assert no_hit_status["gene_annotation_count"] == 0
    assert len((no_hit_output / "gene_annotations.tsv").read_text(encoding="utf-8").splitlines()) == 1
    assert len((no_hit_output / "annotation_terms.tsv").read_text(encoding="utf-8").splitlines()) == 1
    no_hit_manifest = json.loads((no_hit_output / "manifest.json").read_text(encoding="utf-8"))
    assert len(no_hit_manifest["commands"]) == 2

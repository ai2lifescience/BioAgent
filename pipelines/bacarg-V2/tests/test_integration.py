from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

from bacarg.pipeline import run_pipeline


ROOT = Path(__file__).resolve().parents[1]


def _fake_tools(path: Path) -> Path:
    script = path / "fake tools.py"
    script.write_text(
        "import sys\n"
        "from pathlib import Path\n"
        "tool=sys.argv[1]; a=sys.argv[2:]\n"
        "if tool=='trimmomatic':\n"
        "  indexes=(5,6,7,8) if a[0]=='PE' else (4,)\n"
        "  [Path(a[i]).parent.mkdir(parents=True,exist_ok=True) for i in indexes]\n"
        "  [Path(a[i]).write_text('@r\\nACGT\\n+\\nIIII\\n',encoding='utf-8') for i in indexes]\n"
        "elif tool=='metaspades':\n"
        "  out=Path(a[a.index('-o')+1]); out.mkdir(parents=True,exist_ok=True)\n"
        "  (out/'contigs.fasta').write_text('>contig1\\nACGTACGTACGT\\n',encoding='utf-8')\n"
        "elif tool=='prokka':\n"
        "  out=Path(a[a.index('--outdir')+1]); prefix=a[a.index('--prefix')+1]; out.mkdir(parents=True,exist_ok=True)\n"
        "  (out/(prefix+'.faa')).write_text('>L1\\nMKK\\n',encoding='utf-8')\n"
        "  (out/(prefix+'.ffn')).write_text('>L1\\nATGAAAAAA\\n',encoding='utf-8')\n"
        "  (out/(prefix+'.gff')).write_text('##gff-version 3\\ncontig1\\tProkka\\tCDS\\t1\\t12\\t.\\t+\\t0\\tID=L1;locus_tag=L1;gene=ctx;product=context\\n',encoding='utf-8')\n"
        "  (out/(prefix+'.tsv')).write_text('locus_tag\\tgene\\nL1\\tctx\\n',encoding='utf-8')\n"
        "  (out/(prefix+'.txt')).write_text('non-empty\\n',encoding='utf-8')\n"
        "elif tool=='abricate':\n"
        "  print('#FILE\\tSEQUENCE\\tSTART\\tEND\\tSTRAND\\tGENE\\tACCESSION\\t%IDENTITY\\t%COVERAGE\\tPRODUCT')\n"
        "  print('a\\tcontig1\\t2\\t10\\t+\\tblaX\\tACC1\\t99.5\\t95.0\\tprotein X')\n"
        "elif tool=='reads_mapper':\n"
        "  print('r1\\t100\\t0\\t60\\t+\\tmegares_v3~~~blaX~~~ACC1~~~beta-lactam\\t100\\t0\\t60\\t58\\t60\\t60')\n"
        "  print('r2\\t100\\t0\\t60\\t+\\tmegares_v3~~~blaX~~~ACC1~~~beta-lactam\\t100\\t40\\t100\\t55\\t60\\t60')\n"
        "else:\n"
        "  raise SystemExit(7)\n",
        encoding="utf-8",
    )
    return script


def test_fake_tool_full_fastq_pipeline(tmp_path: Path) -> None:
    fake = _fake_tools(tmp_path)
    data = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    data["pipeline"]["threads"] = 2
    for name in ("trimmomatic", "reads_mapper", "assembler", "prokka", "abricate"):
        data["tools"][name]["executable"] = sys.executable
        data["tools"][name]["prefix_options"] = [str(fake), name if name != "assembler" else "metaspades"]
    datadir = tmp_path / "database root"
    db = datadir / "megares_v3"
    db.mkdir(parents=True)
    (db / "sequences").write_text(">x\nACGT\n", encoding="utf-8")
    for suffix in (".nhr", ".nin", ".nsq"):
        (db / f"sequences{suffix}").write_text("index", encoding="utf-8")
    metadata = tmp_path / "metadata.tsv"
    metadata.write_text(
        "accession\tgene\tclass\tmechanism\trequires_snp_confirmation\n"
        "ACC1\tblaX\tbeta-lactam\tenzyme\tfalse\n",
        encoding="utf-8",
    )
    manifest = tmp_path / "db-manifest.json"
    manifest.write_text(json.dumps({"database_version": "3.0"}), encoding="utf-8")
    data["databases"] = {
        "abricate_datadir": str(datadir),
        "metadata": str(metadata),
        "manifest": str(manifest),
    }
    config = tmp_path / "integration.yaml"
    config.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    r1 = tmp_path / "reads R1.fastq"
    r2 = tmp_path / "reads R2.fastq"
    r1.write_text("@r1\nACGT\n+\nIIII\n", encoding="utf-8")
    r2.write_text("@r2\nTGCA\n+\nIIII\n", encoding="utf-8")
    output = tmp_path / "result with spaces"
    status = run_pipeline([r1, r2], output, config_path=config)
    assert status["status"] == "success"
    assert status["hit_count"] == 1
    assert (output / "arg_hits.jsonl").read_text(encoding="utf-8").count("\n") == 1
    rows = (output / "arg_hits.tsv").read_text(encoding="utf-8").splitlines()
    assert len(rows) == 2
    assert "\tL1\tctx\tcontext\t" in rows[1]
    manifest_result = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert len(manifest_result["commands"]) == 4
    reads_output = tmp_path / "direct reads result"
    reads_status = run_pipeline(
        [r1, r2],
        reads_output,
        config_path=config,
        input_type="reads",
        analysis_mode="reads",
    )
    assert reads_status["status"] == "success" and reads_status["hit_count"] == 1
    read_row = json.loads((reads_output / "arg_hits.jsonl").read_text(encoding="utf-8").strip())
    assert read_row["gene"] == "blaX" and read_row["accession"] == "ACC1"
    assert read_row["supporting_reads"] == 2 and read_row["depth"] == 1.2
    assert read_row["contig"] == read_row["start"] == read_row["strand"] == ""
    read_manifest = json.loads((reads_output / "manifest.json").read_text(encoding="utf-8"))
    read_qc = json.loads((reads_output / "qc.json").read_text(encoding="utf-8"))
    assert len(read_manifest["commands"]) == 2
    command_text = " ".join(part for command in read_manifest["commands"] for part in command).lower()
    assert "metaspades" not in command_text and "prokka" not in command_text
    assert read_qc["assembly"]["source"] == "not_applicable"
    assert read_qc["reads"]["trimmed"]["read_count"] == 2

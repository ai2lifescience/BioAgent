from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

from bacvf.pipeline import run_pipeline


ROOT = Path(__file__).resolve().parents[1]


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
        "  (out/(p+'.faa')).write_text('>L1\\nMKK\\n',encoding='utf-8'); (out/(p+'.ffn')).write_text('>L1\\nATGAAAAAA\\n',encoding='utf-8')\n"
        "  (out/(p+'.gff')).write_text('contig1\\tProkka\\tCDS\\t1\\t12\\t.\\t+\\t0\\tID=L1;locus_tag=L1;gene=fimH;product=adhesin\\n',encoding='utf-8')\n"
        "  (out/(p+'.tsv')).write_text('locus_tag\\nL1\\n',encoding='utf-8'); (out/(p+'.txt')).write_text('ok\\n',encoding='utf-8')\n"
        "elif tool=='abricate':\n"
        "  print('#FILE\\tSEQUENCE\\tSTART\\tEND\\tSTRAND\\tGENE\\tACCESSION\\t%IDENTITY\\t%COVERAGE\\tPRODUCT')\n"
        "  print('a\\tcontig1\\t2\\t10\\t+\\tfimH\\tACC1\\t99.5\\t95.0\\tadhesin')\n"
        "elif tool=='reads_mapper':\n"
        "  print('r1\\t100\\t0\\t60\\t+\\tvfdb_core~~~fimH~~~ACC1~~~adhesion\\t100\\t0\\t60\\t58\\t60\\t60')\n"
        "  print('r2\\t100\\t0\\t60\\t+\\tvfdb_core~~~fimH~~~ACC1~~~adhesion\\t100\\t40\\t100\\t55\\t60\\t60')\n"
        "else: raise SystemExit(7)\n",
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
    datadir = tmp_path / "database"
    db = datadir / "vfdb_core"
    db.mkdir(parents=True)
    (db / "sequences").write_text(">x\nACGT\n", encoding="utf-8")
    for suffix in (".nhr", ".nin", ".nsq"):
        (db / f"sequences{suffix}").write_text("i", encoding="utf-8")
    metadata = tmp_path / "vf.tsv"
    metadata.write_text(
        "accession\tvf_id\tgene\tfactor_name\tcategory\tsubcategory\tassociated_pathogen\n"
        "ACC1\tVF1\tfimH\tadhesin\tAdherence\tFimbriae\tE. coli\n",
        encoding="utf-8",
    )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"database_version": "core-2026"}), encoding="utf-8")
    data["databases"] = {
        "abricate_datadir": str(datadir),
        "metadata": str(metadata),
        "manifest": str(manifest),
    }
    config = tmp_path / "integration.yaml"
    config.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    r1, r2 = tmp_path / "R1.fastq", tmp_path / "R2.fastq"
    r1.write_text("@r1\nACGT\n+\nIIII\n", encoding="utf-8")
    r2.write_text("@r2\nTGCA\n+\nIIII\n", encoding="utf-8")
    output = tmp_path / "output"
    status = run_pipeline([r1, r2], output, config_path=config)
    assert status["status"] == "success" and status["hit_count"] == 1
    result = (output / "vf_hits.tsv").read_text(encoding="utf-8")
    assert "VF1" in result and "Adherence" in result and "E. coli" in result
    assert json.loads((output / "manifest.json").read_text(encoding="utf-8"))["commands"]
    reads_output = tmp_path / "direct-reads"
    reads_status = run_pipeline(
        [r1, r2],
        reads_output,
        config_path=config,
        input_type="reads",
        analysis_mode="reads",
    )
    assert reads_status["status"] == "success" and reads_status["hit_count"] == 1
    read_row = json.loads((reads_output / "vf_hits.jsonl").read_text(encoding="utf-8").strip())
    assert read_row["vf_id"] == "VF1" and read_row["accession"] == "ACC1"
    assert read_row["supporting_reads"] == 2 and read_row["depth"] == 1.2
    assert read_row["contig"] == read_row["start"] == read_row["strand"] == ""
    read_manifest = json.loads((reads_output / "manifest.json").read_text(encoding="utf-8"))
    read_qc = json.loads((reads_output / "qc.json").read_text(encoding="utf-8"))
    assert len(read_manifest["commands"]) == 2
    command_text = " ".join(part for command in read_manifest["commands"] for part in command).lower()
    assert "metaspades" not in command_text and "prokka" not in command_text
    assert read_qc["assembly"]["source"] == "not_applicable"
    assert read_qc["reads"]["trimmed"]["read_count"] == 2

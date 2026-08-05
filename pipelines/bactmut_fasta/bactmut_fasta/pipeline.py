"""End-to-end bacterial SNP pipeline orchestration."""

import logging
import math
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence, Set, Tuple

from .align import align_sample, choose_alignment_backend, load_reference
from .filtering import filter_snps
from .models import SampleCalls
from .reporting import (
    write_initial_snp_list,
    write_mutation_report,
    write_snp_matrix,
    write_variants_table,
    write_summary,
)
from .simulation import generate_simulated_samples
from .tree import build_tree


LOGGER = logging.getLogger(__name__)
FASTA_SUFFIXES = frozenset({".fa", ".fasta", ".fna", ".fas"})


def discover_queries(query_dir: Path) -> List[Path]:
    if not query_dir.is_dir():
        raise ValueError(f"Query directory does not exist: {query_dir}")
    paths = sorted(
        path for path in query_dir.iterdir() if path.is_file() and path.suffix.lower() in FASTA_SUFFIXES
    )
    if len(paths) < 5:
        raise ValueError(f"At least 5 query FASTA files are required; found {len(paths)} in {query_dir}")
    return paths


def _unique_sample_names(paths: Sequence[Path]) -> List[str]:
    names: List[str] = []
    used = set()
    for path in paths:
        base = path.stem.replace(" ", "_")
        name = base
        suffix = 2
        while name in used:
            name = f"{base}_{suffix}"
            suffix += 1
        used.add(name)
        names.append(name)
    return names


def _write_paf(
    reference,
    query_path: Path,
    sample_name: str,
    threads: int,
    paf_dir: Path,
) -> Path:
    paf_dir.mkdir(parents=True, exist_ok=True)
    paf_path = paf_dir / f"{sample_name}.paf"
    command = [
        "minimap2",
        "-c",
        "--cs",
        "-x",
        "asm5",
        "-t",
        str(max(1, threads)),
        str(reference.path),
        str(query_path),
    ]
    LOGGER.debug("Running: %s", " ".join(command))
    with paf_path.open("w", encoding="ascii") as output:
        process = subprocess.run(
            command,
            stdout=output,
            stderr=subprocess.PIPE,
            text=True,
            encoding="ascii",
            errors="replace",
        )
    if process.returncode != 0:
        raise RuntimeError(
            f"minimap2 PAF generation failed for {query_path.name} "
            f"(exit {process.returncode}): {process.stderr.strip()}"
        )
    return paf_path


def _align_one(
    reference,
    path: Path,
    name: str,
    backend: str,
    threads: int,
    paf_dir: Optional[Path],
) -> SampleCalls:
    calls = align_sample(reference, path, name, backend, threads)
    if backend == "minimap2" and paf_dir is not None:
        calls.paf_path = _write_paf(reference, path, name, threads, paf_dir)
    return calls


def _align_all(
    reference,
    paths: Sequence[Path],
    backend: str,
    total_threads: int,
    paf_dir: Optional[Path] = None,
) -> List[SampleCalls]:
    names = _unique_sample_names(paths)
    worker_count = min(len(paths), max(1, total_threads))
    threads_per_worker = max(1, total_threads // worker_count)
    results: List[Optional[SampleCalls]] = [None] * len(paths)
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {
            executor.submit(
                _align_one,
                reference,
                path,
                name,
                backend,
                threads_per_worker,
                paf_dir,
            ): index
            for index, (path, name) in enumerate(zip(paths, names))
        }
        for completed_count, future in enumerate(as_completed(futures), 1):
            index = futures[future]
            results[index] = future.result()
            LOGGER.info("Aligned %d/%d: %s", completed_count, len(paths), names[index])
    return [result for result in results if result is not None]


def run_pipeline(arguments: Mapping[str, object]) -> int:
    overall_start = time.perf_counter()
    out_dir = Path(str(arguments["out_dir"])).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # ----- 解析参考基因组来源 -----
    reference_path = None
    temp_ref_path = None  # 用于清理临时文件
    
    if arguments.get("taxonid"):
        # 通过 NCBI Taxon ID 获取参考基因组
        from .ref_manager import get_reference_manager
        manager = get_reference_manager()
        temp_ref_path = manager.get_reference_by_taxonid(str(arguments["taxonid"]))
        reference_path = Path(temp_ref_path)
        LOGGER.info("已为 Taxon ID '%s' 提取参考基因组", arguments["taxonid"])
    elif arguments.get("species"):
        # 通过物种名获取参考基因组
        from .ref_manager import get_reference_manager
        manager = get_reference_manager()
        temp_ref_path = manager.get_reference(str(arguments["species"]))
        reference_path = Path(temp_ref_path)
        LOGGER.info("已为物种 '%s' 提取参考基因组", arguments["species"])
    elif arguments.get("reference"):
        reference_path = Path(str(arguments["reference"])).resolve()
    else:
        raise ValueError("必须提供 --reference、--species 或 --taxonid")
    
    if not reference_path or not reference_path.is_file():
        raise ValueError(f"参考基因组文件不存在: {reference_path}")
    temp_map_path = (
        reference_path.with_suffix(".contig_map.tsv") if temp_ref_path else None
    )
    if temp_map_path and temp_map_path.is_file():
        shutil.copyfile(temp_map_path, out_dir / "reference_contig_map.tsv")
    # ----- 解析结束 -----
    
    timings: Dict[str, float] = {}
    
    # 用 try-finally 包裹核心逻辑，确保临时文件被清理
    try:
        step_start = time.perf_counter()
        reference = load_reference(reference_path)
        truth: Optional[Set[int]] = None
        if bool(arguments["simulate"]):
            LOGGER.info("Generating simulated genomes")
            query_paths, truth = generate_simulated_samples(
                reference,
                out_dir / "simulated_queries",
                float(arguments["simulate_snp_rate"]),
                int(arguments["simulate_samples"]),
                int(arguments["seed"]),
            )
        else:
            query_dir_value = arguments.get("query_dir")
            if not query_dir_value:
                raise ValueError("--query_dir is required unless --simulate is enabled")
            query_paths = discover_queries(Path(str(query_dir_value)).resolve())
        timings["input_and_simulation"] = time.perf_counter() - step_start

        backend = choose_alignment_backend(str(arguments["aligner"]))
        if backend == "internal" and str(arguments["aligner"]) == "auto":
            LOGGER.warning(
                "minimap2 was not found; using the internal equal-length-genome aligner. "
                "Install minimap2 to process contigs or indels."
            )
        step_start = time.perf_counter()
        samples = _align_all(
            reference,
            query_paths,
            backend,
            int(arguments["threads"]),
            out_dir / "alignments",
        )
        timings["alignment_and_snp_detection"] = time.perf_counter() - step_start

        step_start = time.perf_counter()
        result = filter_snps(
            samples,
            reference.length,
            float(arguments["min_coverage"]),
            int(arguments["window_size"]),
            int(arguments["step_size"]),
            float(arguments["sd_threshold"]),
        )
        timings["coverage_and_recombination_filtering"] = time.perf_counter() - step_start

        step_start = time.perf_counter()
        write_initial_snp_list(
            out_dir / "initial_snp_list.csv", reference, samples, result.initial_positions
        )
        matrix_path = out_dir / "filtered_snp_matrix.fasta"
        write_snp_matrix(matrix_path, reference, samples, result.final_positions)
        write_mutation_report(out_dir / "mutation_report.csv", reference, samples, result)
        write_variants_table(
            out_dir / "variants.tsv",
            reference,
            samples,
            result,
            out_dir / "variants_summary.txt",
        )
        timings["output_writing"] = time.perf_counter() - step_start

        step_start = time.perf_counter()
        tree_status, _ = build_tree(
            matrix_path, out_dir, len(result.final_positions), arguments["threads"]
        )
        timings["tree_building"] = time.perf_counter() - step_start

        validation = None
        if truth is not None:
            detected = set(result.initial_positions)
            true_positives = len(truth & detected)
            validation = {
                "true_snps": float(len(truth)),
                "detected_snps": float(len(detected)),
                "true_positives": float(true_positives),
                "recovery_rate": true_positives / len(truth) if truth else 1.0,
                "precision": true_positives / len(detected) if detected else (1.0 if not truth else 0.0),
            }
        timings["total"] = time.perf_counter() - overall_start
        write_summary(
            out_dir / "summary.txt",
            len(samples),
            result,
            timings,
            arguments,
            backend,
            tree_status,
            validation,
        )
        LOGGER.info(
            "Completed: %d initial SNPs, %d final SNPs", len(result.initial_positions), len(result.final_positions)
        )
        return 0
    
    finally:
        # 清理临时参考基因组文件
        if temp_ref_path and Path(temp_ref_path).exists():
            try:
                Path(temp_ref_path).unlink()
                if temp_map_path:
                    temp_map_path.unlink(missing_ok=True)
                LOGGER.debug("已清理临时参考基因组文件: %s", temp_ref_path)
            except OSError as e:
                LOGGER.warning("无法清理临时文件 %s: %s", temp_ref_path, e)

#!/usr/bin/env python3
"""
Reference Genome Manager for bactmut pipeline.
Provides fast, memory-efficient access to GTDB reference genomes.
"""

import csv
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

CACHE_DIR = Path.home() / ".bactmut"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
CACHE_VERSION = 3
CONTIG_GAP_SIZE = 20

Record = Tuple[str, int]
SpeciesCache = Dict[str, Dict[str, List[Record]]]
RepresentativeIndex = Dict[str, Set[str]]
_REQUIRED_METADATA_FIELDS = (
    "accession",
    "ncbi_genbank_assembly_accession",
    "gtdb_taxonomy",
    "gtdb_representative",
)
_REQUIRED_TAXID_METADATA_FIELDS = ("ncbi_taxid", "ncbi_species_taxid")
_ASSEMBLY_ACCESSION_RE = re.compile(r"^(?:(?:RS|GB)_)?(GC[AF]_\d+)(?:\.\d+)?$")


class ReferenceManager:
    """Manage GTDB reference genomes with on-the-fly extraction."""

    def __init__(
        self, db_path: Optional[str] = None, metadata_path: Optional[str] = None
    ):
        if db_path is None:
            db_path = os.environ.get("GTDB_DB_PATH")
            if not db_path:
                raise ValueError(
                    "请设置环境变量 GTDB_DB_PATH\n"
                    "  export GTDB_DB_PATH=/path/to/representative.fa"
                )
        self.db_path = Path(db_path)
        if not self.db_path.exists():
            raise FileNotFoundError(f"数据库不存在: {self.db_path}")

        configured_metadata = metadata_path or os.environ.get("GTDB_METADATA_PATH")
        self.metadata_path = Path(configured_metadata) if configured_metadata else None
        self._species_cache: SpeciesCache = {}
        self._representative_index: Optional[RepresentativeIndex] = None
        self._taxid_index: Optional[RepresentativeIndex] = None
        self._species_taxid_index: Optional[RepresentativeIndex] = None
        self._cache_loaded = False

        # 缓存文件路径（基于数据库路径的哈希值，避免不同数据库混用）
        db_hash = hashlib.md5(str(self.db_path).encode()).hexdigest()[:8]
        self.cache_file = CACHE_DIR / f"gtdb_index_{db_hash}.json"

    @staticmethod
    def _file_identity(path: Path) -> Dict[str, int]:
        stat = path.stat()
        return {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}

    @staticmethod
    def _normalize_assembly_id(value: object) -> Optional[str]:
        """Normalize a GTDB/NCBI assembly accession to its GCF/GCA identifier."""
        if not isinstance(value, str):
            return None
        match = _ASSEMBLY_ACCESSION_RE.fullmatch(value.strip())
        return match.group(1) if match else None

    @staticmethod
    def _gtdb_species(taxonomy: object) -> Optional[str]:
        """Extract the exact GTDB species name from a taxonomy string."""
        if not isinstance(taxonomy, str):
            return None
        for field in taxonomy.split(";"):
            field = field.strip()
            if field.startswith("s__"):
                species = field[3:].strip().lower()
                return species or None
        return None

    def _load_cache(self) -> bool:
        """Load the FASTA index and any valid representative index from disk."""
        if not self.cache_file.exists():
            return False
        try:
            with open(self.cache_file, "r") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError, TypeError):
            self.cache_file.unlink(missing_ok=True)
            return False

        if not self._is_valid_fasta_cache(data):
            return False

        self._species_cache = {
            species: {
                assembly_id: [tuple(record) for record in records]
                for assembly_id, records in assemblies.items()
            }
            for species, assemblies in data["index"].items()
        }
        self._cache_loaded = True

        if self.metadata_path and self._is_valid_metadata_cache(data):
            self._representative_index = {
                species: set(assemblies)
                for species, assemblies in data["representatives"].items()
            }
            self._taxid_index = {
                taxid: set(assemblies)
                for taxid, assemblies in data["taxid_index"].items()
            }
            self._species_taxid_index = {
                taxid: set(assemblies)
                for taxid, assemblies in data["species_taxid_index"].items()
            }
        return True

    def _is_valid_fasta_cache(self, data: object) -> bool:
        """Return whether a disk cache has a valid FASTA index for this database."""
        if not isinstance(data, dict) or data.get("cache_version") != CACHE_VERSION:
            return False
        if data.get("db_path") != str(self.db_path):
            return False
        identity = self._file_identity(self.db_path)
        if data.get("db_size") != identity["size"]:
            return False
        if data.get("db_mtime_ns") != identity["mtime_ns"]:
            return False
        return self._is_valid_cache_index(data.get("index"))

    def _is_valid_metadata_cache(self, data: object) -> bool:
        """Return whether cached representatives match the configured metadata file."""
        if not isinstance(data, dict) or self.metadata_path is None:
            return False
        if not self.metadata_path.exists():
            return False
        identity = self._file_identity(self.metadata_path)
        if data.get("metadata_path") != str(self.metadata_path):
            return False
        if data.get("metadata_size") != identity["size"]:
            return False
        if data.get("metadata_mtime_ns") != identity["mtime_ns"]:
            return False
        return (
            self._is_valid_representative_index(data.get("representatives"))
            and self._is_valid_representative_index(data.get("taxid_index"))
            and self._is_valid_representative_index(data.get("species_taxid_index"))
        )

    @staticmethod
    def _is_valid_cache_index(index: object) -> bool:
        """Return whether a disk cache has the expected nested FASTA structure."""
        if not isinstance(index, dict):
            return False
        for species, assemblies in index.items():
            if not isinstance(species, str) or not isinstance(assemblies, dict):
                return False
            for assembly_id, records in assemblies.items():
                if not isinstance(assembly_id, str) or not isinstance(records, list):
                    return False
                for record in records:
                    if (
                        not isinstance(record, list)
                        or len(record) != 2
                        or not isinstance(record[0], str)
                        or not isinstance(record[1], int)
                    ):
                        return False
        return True

    @staticmethod
    def _is_valid_representative_index(index: object) -> bool:
        """Return whether cached representatives have the expected JSON structure."""
        if not isinstance(index, dict):
            return False
        for species, assemblies in index.items():
            if not isinstance(species, str) or not isinstance(assemblies, list):
                return False
            if not all(isinstance(assembly_id, str) for assembly_id in assemblies):
                return False
        return True

    def _save_cache(self) -> None:
        """Save the FASTA index and any loaded representative indexes to disk."""
        db_identity = self._file_identity(self.db_path)
        data = {
            "cache_version": CACHE_VERSION,
            "db_path": str(self.db_path),
            "db_size": db_identity["size"],
            "db_mtime_ns": db_identity["mtime_ns"],
            "index": self._species_cache,
        }
        if (
            self._representative_index is not None
            and self._taxid_index is not None
            and self._species_taxid_index is not None
            and self.metadata_path is not None
        ):
            metadata_identity = self._file_identity(self.metadata_path)
            data.update(
                {
                    "metadata_path": str(self.metadata_path),
                    "metadata_size": metadata_identity["size"],
                    "metadata_mtime_ns": metadata_identity["mtime_ns"],
                    "representatives": {
                        species: sorted(assemblies)
                        for species, assemblies in self._representative_index.items()
                    },
                    "taxid_index": {
                        taxid: sorted(assemblies)
                        for taxid, assemblies in self._taxid_index.items()
                    },
                    "species_taxid_index": {
                        taxid: sorted(assemblies)
                        for taxid, assemblies in self._species_taxid_index.items()
                    },
                }
            )
        with open(self.cache_file, "w") as f:
            json.dump(data, f)

    def _build_cache(self) -> None:
        """Scan FASTA headers to build species→assembly→record mappings."""
        if self._cache_loaded:
            return

        if self._load_cache():
            print(f"✅ 从缓存加载索引成功，共 {len(self._species_cache)} 个物种")
            return

        print("⏳ 正在构建参考基因组索引（首次使用，约需30秒）...")
        with open(self.db_path, "r") as f:
            pos = 0
            line = f.readline()
            while line:
                if line.startswith(">"):
                    parts = line[1:].strip().split(" ", 1)
                    seq_id = parts[0]
                    description = parts[1] if len(parts) > 1 else ""

                    species_match = re.match(r"^([A-Za-z]+ [a-z]+)", description)
                    if species_match:
                        species_name = species_match.group(1).lower()
                    else:
                        species_name = description.split(" strain ")[0].lower()

                    accession_match = re.search(r"(?:^|\s)acc_label=([^\s]+)", description)
                    assembly_id = accession_match.group(1) if accession_match else seq_id
                    assemblies = self._species_cache.setdefault(species_name, {})
                    assemblies.setdefault(assembly_id, []).append((seq_id, pos))

                pos = f.tell()
                line = f.readline()

        self._cache_loaded = True
        self._save_cache()
        print(f"索引构建完成，共 {len(self._species_cache)} 个物种")

    def _build_representative_index(self, require_taxid_fields: bool = False) -> None:
        """Stream GTDB metadata into compact representative and taxid indexes."""
        if self._representative_index is not None and (
            not require_taxid_fields
            or (
                self._taxid_index is not None
                and self._species_taxid_index is not None
            )
        ):
            return
        if self.metadata_path is None:
            raise ValueError("未配置 GTDB_METADATA_PATH")
        if not self.metadata_path.exists():
            raise FileNotFoundError(f"GTDB metadata 不存在: {self.metadata_path}")

        representatives: RepresentativeIndex = {}
        taxid_index: RepresentativeIndex = {}
        species_taxid_index: RepresentativeIndex = {}
        with open(self.metadata_path, "r", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            fieldnames = set(reader.fieldnames or [])
            missing = [field for field in _REQUIRED_METADATA_FIELDS if field not in fieldnames]
            if missing:
                raise ValueError(f"GTDB metadata 缺少必要字段: {', '.join(missing)}")
            missing_taxid = [
                field for field in _REQUIRED_TAXID_METADATA_FIELDS if field not in fieldnames
            ]
            if require_taxid_fields and missing_taxid:
                raise ValueError(f"GTDB metadata 缺少必要字段: {', '.join(missing_taxid)}")
            has_taxid_fields = not missing_taxid

            for row in reader:
                if row["gtdb_representative"] != "t":
                    continue
                species = self._gtdb_species(row.get("gtdb_taxonomy"))
                assembly_id = self._normalize_assembly_id(row.get("accession"))
                if assembly_id is None:
                    assembly_id = self._normalize_assembly_id(
                        row.get("ncbi_genbank_assembly_accession")
                    )
                if not species or not assembly_id:
                    continue

                representatives.setdefault(species, set()).add(assembly_id)
                if has_taxid_fields:
                    taxid = (row.get("ncbi_taxid") or "").strip()
                    species_taxid = (row.get("ncbi_species_taxid") or "").strip()
                    if taxid:
                        taxid_index.setdefault(taxid, set()).add(assembly_id)
                    if species_taxid:
                        species_taxid_index.setdefault(species_taxid, set()).add(assembly_id)

        self._representative_index = representatives
        if has_taxid_fields:
            self._taxid_index = taxid_index
            self._species_taxid_index = species_taxid_index
        else:
            self._taxid_index = None
            self._species_taxid_index = None
        self._save_cache()

    def _find_records_by_assembly_id(self, assembly_id: str) -> Optional[List[Record]]:
        """Find FASTA records for an assembly in the loaded species cache."""
        for assemblies in self._species_cache.values():
            records = assemblies.get(assembly_id)
            if records is not None:
                return records
        return None

    @staticmethod
    def _display_gtdb_species_name(species: str) -> str:
        """Format a normalized GTDB species key for user-facing errors."""
        parts = species.split(" ", 1)
        if len(parts) == 1:
            return parts[0].capitalize()
        epithet = parts[1]
        if "_" in epithet:
            base, *suffixes = epithet.split("_")
            epithet = "_".join(
                [base]
                + [suffix.upper() if len(suffix) == 1 else suffix for suffix in suffixes]
            )
        return f"{parts[0].capitalize()} {epithet}"

    def _taxid_candidate_text(self, assembly_ids: Set[str]) -> str:
        """Render taxid candidate assemblies with their GTDB species names."""
        representatives = self._representative_index or {}
        chunks = []
        for assembly_id in sorted(assembly_ids):
            species_names = sorted(
                self._display_gtdb_species_name(species)
                for species, assemblies in representatives.items()
                if assembly_id in assemblies
            )
            if species_names:
                chunks.append(f"{assembly_id} ({', '.join(species_names)})")
            else:
                chunks.append(assembly_id)
        return ", ".join(chunks)

    def _all_fasta_assembly_ids(self) -> List[str]:
        """Return all assembly identifiers present in the loaded FASTA cache."""
        return sorted(
            assembly_id
            for assemblies in self._species_cache.values()
            for assembly_id in assemblies
        )

    def _select_representative_assembly(
        self, species_name: str, matched_species: str, assemblies: Dict[str, List[Record]]
    ) -> List[Record]:
        """Resolve a multi-assembly species through GTDB representative metadata."""
        candidates = sorted(assemblies)
        candidate_text = ", ".join(candidates)
        if self.metadata_path is None:
            raise ValueError(
                f"物种名 '{species_name}' 对应多个 FASTA assembly: {candidate_text}; "
                "请设置 GTDB_METADATA_PATH"
            )

        self._build_representative_index()
        assert self._representative_index is not None
        representatives = self._representative_index.get(matched_species, set())
        if not representatives:
            raise ValueError(
                f"未找到物种名 '{species_name}' 的 GTDB representative; "
                f"FASTA 候选 assembly: {candidate_text}"
            )
        if len(representatives) > 1:
            representative_text = ", ".join(sorted(representatives))
            raise ValueError(
                f"物种名 '{species_name}' 对应多个 GTDB representative: "
                f"{representative_text}"
            )

        representative = next(iter(representatives))
        if representative not in assemblies:
            raise ValueError(
                f"物种名 '{species_name}' 的 GTDB representative '{representative}' "
                f"不在 FASTA 候选 assembly 中: {candidate_text}"
            )
        return assemblies[representative]

    def get_reference(self, species_name: str) -> str:
        """Retrieve a reference genome for a given species name."""
        self._build_cache()

        query = species_name.strip().lower()
        if query in self._species_cache:
            matched_species = query
        else:
            matches = [key for key in self._species_cache if query in key]
            if not matches:
                raise ValueError(f"未找到物种 '{species_name}' 在参考数据库中")
            if len(matches) > 1:
                raise ValueError(
                    f"物种名 '{species_name}' 不唯一，匹配项: {', '.join(matches[:5])}"
                )
            matched_species = matches[0]

        assemblies = self._species_cache[matched_species]
        if len(assemblies) == 1:
            records = next(iter(assemblies.values()))
        else:
            records = self._select_representative_assembly(
                species_name, matched_species, assemblies
            )
        return self._extract_sequence(records)

    def get_reference_by_taxonid(self, taxid: str) -> str:
        """Retrieve a GTDB representative reference selected by NCBI Taxon ID."""
        if self.metadata_path is None:
            raise ValueError(
                f"Taxon ID '{taxid}' 查询需要配置 GTDB_METADATA_PATH"
            )

        if not self._cache_loaded and not self._load_cache():
            self._build_cache()
        self._build_representative_index(require_taxid_fields=True)
        assert self._taxid_index is not None
        assert self._species_taxid_index is not None

        assemblies = self._taxid_index.get(taxid, set())
        if not assemblies:
            assemblies = self._species_taxid_index.get(taxid, set())
        if not assemblies:
            raise ValueError(f"未找到 taxid '{taxid}' 对应的 GTDB representative")

        if len(assemblies) > 1:
            raise ValueError(
                f"taxid '{taxid}' 对应多个 GTDB representative: "
                f"{self._taxid_candidate_text(assemblies)}; "
                "请使用更具体的菌株级 Taxon ID 或改用 --species"
            )

        assembly_id = next(iter(assemblies))
        records = self._find_records_by_assembly_id(assembly_id)
        if records is None:
            candidate_text = ", ".join(self._all_fasta_assembly_ids())
            raise ValueError(
                f"taxid '{taxid}' 的 GTDB representative '{assembly_id}' "
                f"不在 FASTA 候选 assembly 中: {candidate_text}"
            )
        return self._extract_sequence(records)

    def _extract_sequence(self, records: List[Record]) -> str:
        """Create one pseudo-reference and a sidecar contig-coordinate map."""
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".fa", prefix="ref_")
        os.close(tmp_fd)
        map_path = Path(tmp_path).with_suffix(".contig_map.tsv")
        extracted: List[Tuple[str, str]] = []
        with open(self.db_path, "r") as f_in:
            for seq_id, offset in records:
                f_in.seek(offset)
                line = f_in.readline()
                if not line.startswith(">"):
                    raise ValueError(f"在偏移量 {offset} 处未找到序列头部")
                chunks = []
                while True:
                    line = f_in.readline()
                    if not line or line.startswith(">"):
                        break
                    chunks.append(line.strip())
                extracted.append((seq_id, "".join(chunks)))

        if not extracted:
            Path(tmp_path).unlink(missing_ok=True)
            raise ValueError("所选 assembly 不包含 FASTA 序列")

        pseudo_name = (
            extracted[0][0] if len(extracted) == 1 else f"{extracted[0][0]}_pseudo"
        )
        with open(tmp_path, "w") as f_out, open(map_path, "w") as map_out:
            f_out.write(f">{pseudo_name}\n")
            map_out.write(
                "pseudo_start\tpseudo_end\tcontig_id\tcontig_start\tcontig_end\n"
            )
            pseudo_position = 1
            for index, (seq_id, sequence) in enumerate(extracted):
                if index:
                    f_out.write("N" * CONTIG_GAP_SIZE)
                    pseudo_position += CONTIG_GAP_SIZE
                start = pseudo_position
                end = start + len(sequence) - 1
                f_out.write(sequence)
                map_out.write(f"{start}\t{end}\t{seq_id}\t1\t{len(sequence)}\n")
                pseudo_position = end + 1
            f_out.write("\n")

        return tmp_path

    def clear_cache(self) -> None:
        """Clear in-memory cache to free memory."""
        self._species_cache.clear()
        self._representative_index = None
        self._taxid_index = None
        self._species_taxid_index = None
        self._cache_loaded = False


_global_manager: Optional[ReferenceManager] = None


def get_reference_manager(db_path: Optional[str] = None) -> ReferenceManager:
    """Get the global ReferenceManager instance (singleton)."""
    global _global_manager
    if _global_manager is None:
        _global_manager = ReferenceManager(db_path)
    return _global_manager

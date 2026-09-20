"""PDB/mmCIF protein structure inspection helpers backed by Biopython."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from Bio.PDB import PDBParser
from Bio.PDB.MMCIF2Dict import MMCIF2Dict


WATER_NAMES = {"HOH", "WAT", "H2O", "DOD"}


def analyze_protein_structure_file(structure_path: str) -> dict[str, Any]:
    """Analyze a local text PDB or mmCIF protein structure file."""
    path = Path(structure_path)
    if not path.exists():
        raise FileNotFoundError(f"Structure file not found: {structure_path}")
    if not path.is_file():
        raise ValueError(f"Structure path is not a file: {structure_path}")

    suffix = path.suffix.lower()
    if suffix == ".bcif":
        raise ValueError("BinaryCIF (.bcif) analysis is not supported. Download the structure as cif or pdb.")
    if suffix in {".cif", ".mmcif"} or _looks_like_mmcif(path):
        result = _analyze_mmcif(path)
        file_format = "cif"
    else:
        result = _analyze_pdb(path)
        file_format = "pdb"

    summary = (
        f"{result['chain_count']} chain(s), {result['residue_count']} residue(s), "
        f"{result['atom_count']} atom(s), {result['ligand_count']} ligand type(s)."
    )
    return {
        "status": "ok",
        "structure_path": str(path),
        "file_format": file_format,
        "parser": "biopython",
        "bytes": path.stat().st_size,
        "summary": summary,
        **result,
    }


def _analyze_mmcif(path: Path) -> dict[str, Any]:
    cif = MMCIF2Dict(str(path))
    groups = _as_list(cif.get("_atom_site.group_PDB"))
    comp_ids = _first_present_list(cif, "_atom_site.auth_comp_id", "_atom_site.label_comp_id")
    chain_ids = _first_present_list(cif, "_atom_site.auth_asym_id", "_atom_site.label_asym_id")
    seq_ids = _first_present_list(cif, "_atom_site.auth_seq_id", "_atom_site.label_seq_id")
    insertion_codes = _as_list(cif.get("_atom_site.pdbx_PDB_ins_code"))
    model_ids = _as_list(cif.get("_atom_site.pdbx_PDB_model_num"))

    atom_count = len(groups)
    hetatm_count = 0
    water_count = 0
    chains: set[str] = set()
    residues: set[tuple[str, str, str, str, str]] = set()
    ligands: set[str] = set()
    models: set[str] = set()

    for index, group in enumerate(groups):
        group_name = group.upper()
        residue_name = _item_at(comp_ids, index, "UNK").upper()
        chain_id = _item_at(chain_ids, index, "_")
        seq_id = _item_at(seq_ids, index, str(index + 1))
        insertion_code = _clean_optional(_item_at(insertion_codes, index, ""))
        model_id = _item_at(model_ids, index, "1")

        if group_name == "HETATM":
            hetatm_count += 1
        chains.add(chain_id)
        residues.add((model_id, chain_id, seq_id, insertion_code, residue_name))
        models.add(model_id)
        if residue_name in WATER_NAMES:
            water_count += 1
        elif group_name == "HETATM":
            ligands.add(residue_name)

    return _summary_record(
        atom_count=atom_count,
        hetatm_count=hetatm_count,
        water_count=water_count,
        chains=chains,
        residues=residues,
        ligands=ligands,
        model_count=len(models),
        title=_first_scalar(cif, "_struct.title"),
        experimental_method=_joined_scalar(cif, "_exptl.method"),
        resolution_angstrom=_float_scalar(cif, "_refine.ls_d_res_high"),
    )


def _analyze_pdb(path: Path) -> dict[str, Any]:
    parser = PDBParser(QUIET=True)
    structure = parser.get_structure(path.stem or "structure", str(path))
    header = getattr(structure, "header", {}) or {}

    atom_count = 0
    hetatm_count = 0
    water_count = 0
    chains: set[str] = set()
    residues: set[tuple[str, str, str, str, str]] = set()
    ligands: set[str] = set()
    models: set[str] = set()

    for model in structure:
        model_id = str(model.id)
        models.add(model_id)
        for chain in model:
            chain_id = str(chain.id or "_")
            chains.add(chain_id)
            for residue in chain:
                residue_name = str(residue.resname or "UNK").strip().upper()
                hetfield, seq_id, insertion_code = residue.id
                residue_atoms = list(residue.get_atoms())
                atom_count += len(residue_atoms)
                residues.add((model_id, chain_id, str(seq_id), str(insertion_code).strip(), residue_name))
                if hetfield.strip():
                    hetatm_count += len(residue_atoms)
                if hetfield == "W" or residue_name in WATER_NAMES:
                    water_count += len(residue_atoms)
                elif hetfield.strip():
                    ligands.add(residue_name)

    return _summary_record(
        atom_count=atom_count,
        hetatm_count=hetatm_count,
        water_count=water_count,
        chains=chains,
        residues=residues,
        ligands=ligands,
        model_count=len(models),
        title=_clean_scalar(header.get("name")),
        experimental_method=_clean_scalar(header.get("structure_method")),
        resolution_angstrom=_clean_float(header.get("resolution")),
    )


def _summary_record(
    atom_count: int,
    hetatm_count: int,
    water_count: int,
    chains: set[str],
    residues: set[tuple[str, str, str, str, str]],
    ligands: set[str],
    model_count: int,
    title: str | None,
    experimental_method: str | None,
    resolution_angstrom: float | None,
) -> dict[str, Any]:
    return {
        "atom_count": atom_count,
        "hetatm_count": hetatm_count,
        "water_count": water_count,
        "chain_count": len(chains),
        "chains": sorted(chains),
        "residue_count": len(residues),
        "ligand_count": len(ligands),
        "ligands": sorted(ligands),
        "model_count": model_count,
        "title": title,
        "experimental_method": experimental_method,
        "resolution_angstrom": resolution_angstrom,
    }


def _looks_like_mmcif(path: Path) -> bool:
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        start = handle.read(256)
    return start.lstrip().startswith("data_")


def _first_present_list(cif: dict[str, Any], *keys: str) -> list[str]:
    for key in keys:
        values = _as_list(cif.get(key))
        if values:
            return values
    return []


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def _item_at(values: list[str], index: int, default: str) -> str:
    if index < len(values):
        clean = _clean_optional(values[index])
        return clean or default
    return default


def _first_scalar(cif: dict[str, Any], key: str) -> str | None:
    return _clean_scalar(_item_at(_as_list(cif.get(key)), 0, ""))


def _joined_scalar(cif: dict[str, Any], key: str) -> str | None:
    values = [_clean_scalar(item) for item in _as_list(cif.get(key))]
    clean_values = [item for item in values if item]
    return "; ".join(clean_values) if clean_values else None


def _float_scalar(cif: dict[str, Any], key: str) -> float | None:
    return _clean_float(_first_scalar(cif, key))


def _clean_optional(value: str) -> str:
    clean = str(value).strip()
    return "" if clean in {"?", "."} else clean


def _clean_scalar(value: Any) -> str | None:
    if value is None:
        return None
    clean = _clean_optional(str(value))
    return clean or None


def _clean_float(value: Any) -> float | None:
    clean = _clean_scalar(value)
    if clean is None:
        return None
    try:
        return float(clean)
    except ValueError:
        return None

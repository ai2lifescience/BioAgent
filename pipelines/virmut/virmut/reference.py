"""Reference source resolution for the local virus database."""

from __future__ import annotations

import csv
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, NamedTuple


VIRUS_DB_ENV = "VIRUS_DB"
VIRUS_METADATA_ENV = "VIRUS_METADATA"
DB_REQUIRED_MESSAGE = "VIRUS_DB and VIRUS_METADATA are required"
_REQUIRED_METADATA_FIELDS = (
    "Accession",
    "Sequence_type",
    "Completeness",
    "Curated_species",
    "Lineage",
    "Ranks",
    "Family",
    "Species_taxid",
    "Accession_tax_name",
    "Accession_taxid",
    "Distance_to_species",
    "Group_name",
)


class ReferenceError(ValueError):
    """Base error for reference resolution."""


class DBRequiredError(ReferenceError):
    """Raised when the local virus database is required but unavailable."""


SEQDBRequiredError = DBRequiredError


class MultipleReferenceCandidatesError(ReferenceError):
    """Raised when a lookup returns more than one possible reference."""


@dataclass(frozen=True)
class ReferenceCandidate:
    path: str = ""
    species: str | None = None
    taxonid: str | None = None
    accession: str | None = None

    def display(self) -> str:
        parts = []
        if self.accession:
            parts.append(f"accession={self.accession}")
        if self.species:
            parts.append(f"species={self.species}")
        if self.taxonid:
            parts.append(f"taxonid={self.taxonid}")
        if self.path:
            parts.append(self.path)
        return " | ".join(parts)


class ResolvedReference(NamedTuple):
    path: Path


def resolve_reference(
    *,
    reference: str | None = None,
    species: str | None = None,
    taxonid: str | None = None,
    seq_db: str | None = None,
    candidates: Iterable[ReferenceCandidate] | None = None,
    db_fasta: str | Path | None = None,
    db_metadata: str | Path | None = None,
) -> ResolvedReference:
    supplied = [value is not None for value in (reference, species, taxonid)]
    if sum(supplied) != 1:
        raise ReferenceError("provide exactly one of --reference, --species, or --taxonid")

    if reference is not None:
        return ResolvedReference(path=Path(reference))

    if candidates is not None:
        return _resolve_candidates(candidates)

    db_fasta_path, db_metadata_path = _resolve_db_paths(
        db_fasta=db_fasta,
        db_metadata=db_metadata,
        seq_db=seq_db,
    )

    if species is not None:
        query = species.strip().casefold()
        matches = _metadata_candidates(
            db_metadata_path,
            db_fasta_path,
            lambda row: _clean(row.get("Curated_species")).casefold() == query,
            taxonid_field="Species_taxid",
        )
        return _resolve_db_candidates(matches, db_fasta_path)

    assert taxonid is not None
    accession_matches = _metadata_candidates(
        db_metadata_path,
        db_fasta_path,
        lambda row: _clean(row.get("Accession_taxid")) == taxonid,
        taxonid_field="Accession_taxid",
    )
    if accession_matches:
        return _resolve_db_candidates(accession_matches, db_fasta_path)

    species_matches = _metadata_candidates(
        db_metadata_path,
        db_fasta_path,
        lambda row: _clean(row.get("Species_taxid")) == taxonid,
        taxonid_field="Species_taxid",
    )
    return _resolve_db_candidates(species_matches, db_fasta_path)


def _resolve_db_paths(
    *,
    db_fasta: str | Path | None,
    db_metadata: str | Path | None,
    seq_db: str | None,
) -> tuple[Path, Path]:
    if seq_db is not None:
        seq_db_path = Path(seq_db)
        db_fasta = db_fasta or seq_db_path / "reference.fasta"
        db_metadata = db_metadata or seq_db_path / "meta.tsv"

    configured_fasta = db_fasta or os.environ.get(VIRUS_DB_ENV)
    configured_metadata = db_metadata or os.environ.get(VIRUS_METADATA_ENV)
    missing = []
    if not configured_fasta:
        missing.append(VIRUS_DB_ENV)
    if not configured_metadata:
        missing.append(VIRUS_METADATA_ENV)
    if missing:
        raise DBRequiredError(f"{DB_REQUIRED_MESSAGE}: {', '.join(missing)}")

    db_fasta_path = Path(configured_fasta)
    db_metadata_path = Path(configured_metadata)
    if not db_fasta_path.is_file():
        raise FileNotFoundError(f"virus reference FASTA not found: {db_fasta_path}")
    if not db_metadata_path.is_file():
        raise FileNotFoundError(f"virus metadata not found: {db_metadata_path}")
    return db_fasta_path, db_metadata_path


def _metadata_candidates(
    metadata_path: Path,
    db_fasta_path: Path,
    predicate,
    *,
    taxonid_field: str,
) -> list[ReferenceCandidate]:
    matches: list[ReferenceCandidate] = []
    with metadata_path.open(encoding="utf-8", newline="") as metadata:
        reader = csv.DictReader(metadata, delimiter="\t")
        fieldnames = set(reader.fieldnames or [])
        missing = [field for field in _REQUIRED_METADATA_FIELDS if field not in fieldnames]
        if missing:
            raise ReferenceError(
                "virus metadata missing required columns: " + ", ".join(missing)
            )
        for row in reader:
            if predicate(row):
                accession = _clean(row.get("Accession"))
                if not accession:
                    continue
                matches.append(
                    ReferenceCandidate(
                        path=str(db_fasta_path),
                        species=_clean(row.get("Curated_species")) or None,
                        taxonid=_clean(row.get(taxonid_field)) or None,
                        accession=accession,
                    )
                )
    return matches


def _resolve_candidates(candidates: Iterable[ReferenceCandidate]) -> ResolvedReference:
    matches = list(candidates)
    if len(matches) > 1:
        raise _multiple_candidates_error(matches)

    if len(matches) == 1:
        return ResolvedReference(path=Path(matches[0].path))

    raise ReferenceError("no matching reference")


def _resolve_db_candidates(
    candidates: Iterable[ReferenceCandidate],
    db_fasta_path: Path,
) -> ResolvedReference:
    matches = list(candidates)
    if len(matches) > 1:
        raise _multiple_candidates_error(matches)

    if len(matches) == 1:
        accession = matches[0].accession
        if accession is None:
            raise ReferenceError("matching reference is missing an accession")
        return ResolvedReference(path=_extract_accession_fasta(db_fasta_path, accession))

    raise ReferenceError("no matching reference")


def _multiple_candidates_error(
    candidates: Iterable[ReferenceCandidate],
) -> MultipleReferenceCandidatesError:
    candidate_lines = "\n".join(f"- {candidate.display()}" for candidate in candidates)
    return MultipleReferenceCandidatesError(
        "multiple reference candidates found; refusing to choose silently:\n"
        f"{candidate_lines}\n"
        "Hint: use a more specific taxonid or --reference to narrow the search."
    )


def _extract_accession_fasta(db_fasta_path: Path, accession: str) -> Path:
    fd, tmp_name = tempfile.mkstemp(suffix=".fa", prefix="virmut_ref_")
    tmp_path = Path(tmp_name)
    found = False
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as output:
            with db_fasta_path.open(encoding="utf-8") as source:
                copying = False
                for line in source:
                    if line.startswith(">"):
                        if copying:
                            break
                        copying = _header_matches_accession(line, accession)
                        if copying:
                            found = True
                            output.write(line)
                    elif copying:
                        output.write(line)
        if not found:
            raise ReferenceError(
                f"accession '{accession}' was not found in {db_fasta_path}"
            )
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise
    return tmp_path


def _header_matches_accession(header: str, accession: str) -> bool:
    header = header.strip()
    if not header.startswith(">"):
        return False
    return header[1:].split(maxsplit=1)[0] == accession


def _clean(value: str | None) -> str:
    return (value or "").strip()

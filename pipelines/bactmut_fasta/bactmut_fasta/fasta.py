"""Small streaming FASTA helpers with no third-party dependencies."""

from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Sequence, Tuple


IUPAC = frozenset("ACGTRYSWKMBDHVN")
COMPLEMENT = str.maketrans("ACGTRYSWKMBDHVN", "TGCAYRSWMKVHDBN")


def read_fasta(path: Path) -> Iterator[Tuple[str, str]]:
    name = None
    chunks: List[str] = []
    with path.open("r", encoding="ascii") as handle:
        for line_number, raw_line in enumerate(handle, 1):
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith(">"):
                if name is not None:
                    yield name, "".join(chunks)
                name = line[1:].split()[0]
                if not name:
                    raise ValueError(f"Empty FASTA record name in {path}:{line_number}")
                chunks = []
            else:
                if name is None:
                    raise ValueError(f"Sequence before FASTA header in {path}:{line_number}")
                sequence = line.upper()
                invalid = set(sequence) - IUPAC
                if invalid:
                    raise ValueError(
                        f"Invalid FASTA symbols {sorted(invalid)} in {path}:{line_number}"
                    )
                chunks.append(sequence)
    if name is not None:
        yield name, "".join(chunks)
    elif not chunks:
        raise ValueError(f"No FASTA records found in {path}")


def load_fasta(path: Path) -> List[Tuple[str, str]]:
    records = list(read_fasta(path))
    if not records:
        raise ValueError(f"No FASTA records found in {path}")
    return records


def write_fasta(records: Iterable[Tuple[str, str]], path: Path) -> None:
    with path.open("w", encoding="ascii", newline="\n") as handle:
        for name, sequence in records:
            handle.write(f">{name}\n{sequence}\n")


def reverse_complement(sequence: str) -> str:
    return sequence.translate(COMPLEMENT)[::-1]


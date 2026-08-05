"""Data models used across the pipeline."""

from bisect import bisect_right
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class ReferenceGenome:
    path: Path
    records: Dict[str, str]
    offsets: Dict[str, int]
    length: int

    def base(self, global_position: int) -> str:
        for name, offset in self.offsets.items():
            sequence = self.records[name]
            if offset <= global_position < offset + len(sequence):
                return sequence[global_position - offset]
        raise IndexError(global_position)


@dataclass
class SampleCalls:
    name: str
    path: Path
    paf_path: Optional[Path] = None
    variants: Dict[int, str] = field(default_factory=dict)
    ambiguous: Dict[int, str] = field(default_factory=dict)
    intervals: List[Tuple[int, int]] = field(default_factory=list)
    _starts: List[int] = field(default_factory=list, init=False, repr=False)

    def finalize_intervals(self) -> None:
        if not self.intervals:
            self._starts = []
            return
        merged: List[Tuple[int, int]] = []
        for start, end in sorted(self.intervals):
            if start >= end:
                continue
            if merged and start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
            else:
                merged.append((start, end))
        self.intervals = merged
        self._starts = [start for start, _ in merged]

    def is_covered(self, position: int) -> bool:
        index = bisect_right(self._starts, position) - 1
        return index >= 0 and position < self.intervals[index][1]

    def base_at(self, position: int, reference_base: str) -> str:
        if position in self.variants:
            return self.variants[position]
        if position in self.ambiguous:
            return self.ambiguous[position]
        return reference_base if self.is_covered(position) else "N"


@dataclass(frozen=True)
class FilterResult:
    initial_positions: Tuple[int, ...]
    coverage_positions: Tuple[int, ...]
    final_positions: Tuple[int, ...]
    coverage_removed: frozenset
    recombination_removed: frozenset
    recombination_regions: Tuple[Tuple[int, int], ...]
    window_mean: float
    window_sd: float

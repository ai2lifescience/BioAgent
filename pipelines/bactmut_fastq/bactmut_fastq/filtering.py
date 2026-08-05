"""Coverage and sliding-window recombination filters."""

from __future__ import annotations

import math
from bisect import bisect_left
from dataclasses import dataclass
from statistics import fmean, pstdev
from typing import FrozenSet, List, Mapping, Protocol, Sequence, Set, Tuple


class CoverageCalls(Protocol):
    variants: Mapping[int, str]

    def is_covered(self, position: int) -> bool:
        ...


@dataclass(frozen=True)
class FilterResult:
    initial_positions: Tuple[int, ...]
    coverage_positions: Tuple[int, ...]
    final_positions: Tuple[int, ...]
    coverage_removed: FrozenSet[int]
    recombination_removed: FrozenSet[int]
    recombination_regions: Tuple[Tuple[int, int], ...]
    window_mean: float
    window_sd: float


def filter_snps(
    samples: Sequence[CoverageCalls],
    reference_length: int,
    min_coverage_fraction: float = 0.9,
    window_size: int = 50,
    step_size: int = 10,
    sd_threshold: float = 3.0,
) -> FilterResult:
    initial = sorted(
        {
            position
            for sample in samples
            for position, base in sample.variants.items()
            if base != "N"
        }
    )
    required_samples = math.ceil(min_coverage_fraction * len(samples))
    coverage_positions = [
        position
        for position in initial
        if sum(sample.is_covered(position) for sample in samples) >= required_samples
    ]
    coverage_removed = frozenset(set(initial) - set(coverage_positions))
    regions, mean_density, density_sd = find_recombination_regions(
        coverage_positions,
        reference_length,
        window_size,
        step_size,
        sd_threshold,
    )
    recombination_removed: Set[int] = set()
    for start, end in regions:
        left = bisect_left(coverage_positions, start)
        right = bisect_left(coverage_positions, end)
        recombination_removed.update(coverage_positions[left:right])
    final = [
        position
        for position in coverage_positions
        if position not in recombination_removed
    ]
    return FilterResult(
        initial_positions=tuple(initial),
        coverage_positions=tuple(coverage_positions),
        final_positions=tuple(final),
        coverage_removed=coverage_removed,
        recombination_removed=frozenset(recombination_removed),
        recombination_regions=tuple(regions),
        window_mean=mean_density,
        window_sd=density_sd,
    )


def find_recombination_regions(
    positions: Sequence[int],
    reference_length: int,
    window_size: int,
    step_size: int,
    sd_threshold: float,
) -> Tuple[List[Tuple[int, int]], float, float]:
    if reference_length <= 0:
        return [], 0.0, 0.0
    starts = list(range(0, max(1, reference_length - window_size + 1), step_size))
    final_start = max(0, reference_length - window_size)
    if not starts or starts[-1] != final_start:
        starts.append(final_start)
    densities = [
        (
            bisect_left(positions, min(reference_length, start + window_size))
            - bisect_left(positions, start)
        )
        / min(window_size, reference_length - start)
        for start in starts
    ]
    mean_density = fmean(densities) if densities else 0.0
    density_sd = pstdev(densities) if len(densities) > 1 else 0.0
    threshold = mean_density + sd_threshold * density_sd
    candidates = [
        (start, min(reference_length, start + window_size))
        for start, density in zip(starts, densities)
        if density > threshold
    ]
    merged: List[Tuple[int, int]] = []
    for start, end in candidates:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged, mean_density, density_sd

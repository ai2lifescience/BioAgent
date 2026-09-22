"""Render an existing feature artifact as a circular or linear SVG map."""
from __future__ import annotations

from typing import Annotated, Literal
from dataclasses import dataclass
from html import escape
from math import cos, pi, sin
import re

from agents import RunContextWrapper
from pydantic import Field, model_validator

from harness.context import AgentRunContext
from tools.infrastructure.tool_support.artifacts import artifact, destination, input_path, output
from tools.infrastructure.tool_support.decorators import bio_function_tool
from tools.infrastructure.tool_support.operations import invoke
from tools.infrastructure.tool_support.results import FunctionContract, FunctionResult


class Feature(FunctionContract):
    start: int = Field(ge=1)
    end: int = Field(ge=1)
    strand: Literal[-1, 0, 1]
    type: str
    label: str
    parts: list[tuple[int, int]] = Field(default_factory=list)
    qualifiers: dict[str, list[str]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def coordinates(self):
        if self.end < self.start or any(a < 1 or b < a for a, b in self.parts):
            raise ValueError("Features use 1-based inclusive coordinates.")
        return self


class FeatureSet(FunctionContract):
    sequence_id: str
    length: int = Field(ge=1)
    features: list[Feature]

    @model_validator(mode="after")
    def within_sequence(self):
        if any(f.end > self.length or any(b > self.length for a, b in f.parts) for f in self.features):
            raise ValueError("Feature coordinates exceed sequence length.")
        return self


class FeatureDocument(FunctionContract):
    schema_version: Literal[1] = 1
    coordinates: Literal["1-based-inclusive"] = "1-based-inclusive"
    records: list[FeatureSet]


class MapResult(FunctionContract):
    source_path: str
    image_path: str
    sequence_id: str
    genome_length: int
    total: int
    rendered: int
    truncated: bool


@dataclass(frozen=True)
class GenomeFeature:
    start: int
    end: int
    strand: int
    feature_type: str
    label: str


def _select_id(ids: list[str], selected: str | None):
    if selected:
        if selected not in ids:
            raise ValueError(f"Sequence {selected!r} is not present.")
        return selected
    if len(ids) != 1:
        raise ValueError("Provide sequence_id when input contains multiple sequences.")
    return ids[0]


FEATURE_COLORS = {
    "gene": "#2563eb",
    "CDS": "#0f766e",
    "ORF": "#7c3aed",
    "tRNA": "#d97706",
    "rRNA": "#dc2626",
    "repeat_region": "#64748b",
    "misc_feature": "#475569",
}


def _render_circular_svg(title: str, genome_length: int, features: list[GenomeFeature]) -> str:
    width = 920
    height = 760
    center_x = 360
    center_y = 385
    radius = 210
    parts = [_svg_header(width, height, title)]
    parts.append(f'<circle cx="{center_x}" cy="{center_y}" r="{radius}" fill="none" stroke="#26343d" stroke-width="3"/>')
    parts.append(f'<circle cx="{center_x}" cy="{center_y}" r="{radius - 34}" fill="none" stroke="#d8e1e6" stroke-width="1.5" stroke-dasharray="5 7"/>')
    parts.append(f'<text x="{center_x}" y="{center_y - 8}" text-anchor="middle" class="title">{escape(title)}</text>')
    parts.append(f'<text x="{center_x}" y="{center_y + 20}" text-anchor="middle" class="muted">{genome_length:,} bp</text>')

    limited = _limited_features(features)
    for index, feature in enumerate(limited):
        color = FEATURE_COLORS.get(feature.feature_type, "#475569")
        feature_radius = radius + 18 + (index % 3) * 16
        start_angle = _position_to_angle(feature.start, genome_length)
        end_angle = _position_to_angle(feature.end, genome_length)
        large_arc = 1 if _feature_span(feature, genome_length) > genome_length / 2 else 0
        start_x, start_y = _polar(center_x, center_y, feature_radius, start_angle)
        end_x, end_y = _polar(center_x, center_y, feature_radius, end_angle)
        parts.append(
            f'<path d="M {start_x:.2f} {start_y:.2f} A {feature_radius} {feature_radius} 0 {large_arc} 1 {end_x:.2f} {end_y:.2f}" '
            f'fill="none" stroke="{color}" stroke-width="10" stroke-linecap="round">'
            f'<title>{escape(feature.label)}: {feature.start}-{feature.end} ({feature.feature_type})</title></path>'
        )
        mid_angle = (start_angle + end_angle) / 2
        if index < 24 and _feature_span(feature, genome_length) >= max(60, genome_length * 0.015):
            text_x, text_y = _polar(center_x, center_y, feature_radius + 24, mid_angle)
            anchor = "start" if cos(mid_angle) >= 0 else "end"
            parts.append(f'<text x="{text_x:.2f}" y="{text_y:.2f}" text-anchor="{anchor}" class="label">{escape(_short_label(feature.label))}</text>')

    parts.append(_legend(650, 185, features))
    parts.append("</svg>")
    return "\n".join(parts)


def _render_linear_svg(title: str, genome_length: int, features: list[GenomeFeature]) -> str:
    width = 1040
    height = 520
    left = 80
    right = 930
    axis_y = 230
    parts = [_svg_header(width, height, title)]
    parts.append(f'<text x="{left}" y="58" class="title">{escape(title)}</text>')
    parts.append(f'<text x="{left}" y="84" class="muted">{genome_length:,} bp</text>')
    parts.append(f'<line x1="{left}" y1="{axis_y}" x2="{right}" y2="{axis_y}" stroke="#26343d" stroke-width="3"/>')
    for tick in range(0, 6):
        x = left + ((right - left) * tick / 5)
        value = int(genome_length * tick / 5)
        parts.append(f'<line x1="{x:.1f}" y1="{axis_y - 9}" x2="{x:.1f}" y2="{axis_y + 9}" stroke="#26343d" stroke-width="2"/>')
        parts.append(f'<text x="{x:.1f}" y="{axis_y + 32}" text-anchor="middle" class="muted">{value:,}</text>')
    for index, feature in enumerate(_limited_features(features)):
        color = FEATURE_COLORS.get(feature.feature_type, "#475569")
        x1 = left + ((feature.start - 1) / max(1, genome_length)) * (right - left)
        x2 = left + (feature.end / max(1, genome_length)) * (right - left)
        lane = index % 5
        y = axis_y - 46 - lane * 24 if feature.strand != -1 else axis_y + 24 + lane * 24
        width_px = max(3, x2 - x1)
        parts.append(
            f'<rect x="{x1:.1f}" y="{y:.1f}" width="{width_px:.1f}" height="14" rx="4" fill="{color}">'
            f'<title>{escape(feature.label)}: {feature.start}-{feature.end} ({feature.feature_type})</title></rect>'
        )
        if index < 30 and width_px > 24:
            parts.append(f'<text x="{(x1 + x2) / 2:.1f}" y="{y - 4:.1f}" text-anchor="middle" class="label">{escape(_short_label(feature.label))}</text>')
    parts.append(_legend(760, 60, features))
    parts.append("</svg>")
    return "\n".join(parts)


def _svg_header(width: int, height: int, title: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)} genome map">\n'
        "<style>"
        "text{font-family:Inter,Arial,sans-serif;fill:#172026}.title{font-size:22px;font-weight:760}.label{font-size:12px;font-weight:680}.muted{font-size:13px;fill:#5f6f78}.legend{font-size:13px;font-weight:680}"
        "</style>\n"
        f'<rect width="{width}" height="{height}" fill="#ffffff"/>'
    )


def _legend(x: int, y: int, features: list[GenomeFeature]) -> str:
    counts = _feature_counts(features)
    parts = [f'<g transform="translate({x},{y})">', '<text class="title" font-size="16">Feature types</text>']
    for index, (feature_type, count) in enumerate(sorted(counts.items())):
        color = FEATURE_COLORS.get(feature_type, "#475569")
        row_y = 30 + index * 24
        parts.append(f'<rect x="0" y="{row_y - 12}" width="14" height="14" rx="3" fill="{color}"/>')
        parts.append(f'<text x="22" y="{row_y}" class="legend">{escape(feature_type)} ({count})</text>')
    parts.append("</g>")
    return "\n".join(parts)


def _position_to_angle(position: int, genome_length: int) -> float:
    return ((position - 1) / max(1, genome_length)) * 2 * pi - (pi / 2)


def _polar(center_x: int, center_y: int, radius: int, angle: float) -> tuple[float, float]:
    return center_x + radius * cos(angle), center_y + radius * sin(angle)


def _feature_span(feature: GenomeFeature, genome_length: int) -> int:
    return max(1, min(genome_length, feature.end) - max(1, feature.start) + 1)


def _limited_features(features: list[GenomeFeature], limit: int = 160) -> list[GenomeFeature]:
    return sorted(features, key=lambda item: (item.start, item.end))[:limit]


def _feature_counts(features: list[GenomeFeature]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for feature in features:
        counts[feature.feature_type] = counts.get(feature.feature_type, 0) + 1
    return counts


def _short_label(label: str, max_length: int = 18) -> str:
    clean = re.sub(r"\s+", " ", label).strip()
    return clean if len(clean) <= max_length else f"{clean[:max_length - 3]}..."



def _calculate(*, features_path: str, sequence_id: str | None, layout: str, label: str | None, context):
    path = input_path(context, features_path, (".json",))
    document = FeatureDocument.model_validate_json(path.read_text(encoding="utf-8"))
    selected = _select_id([record.sequence_id for record in document.records], sequence_id)
    record = next(record for record in document.records if record.sequence_id == selected)
    total_spans = sum(len(feature.parts) if feature.parts else 1 for feature in record.features)
    features = []
    for feature in record.features:
        for start, end in feature.parts or [(feature.start, feature.end)]:
            features.append(GenomeFeature(start=start, end=end, strand=feature.strand, feature_type=feature.type, label=feature.label))
            if len(features) >= 160:
                break
        if len(features) >= 160:
            break
    renderer = _render_circular_svg if layout == "circular" else _render_linear_svg
    target = destination(context, "genome_map.svg")
    target.write_text(renderer(label or selected, record.length, features), encoding="utf-8")
    file = artifact(context, target)
    return output({"source_path": features_path, "image_path": file["path"], "sequence_id": selected, "genome_length": record.length, "total": len(record.features), "rendered": len(features), "truncated": total_spans > len(features)}, file)


@bio_function_tool(timeout=120)
async def genome_render_map(ctx: RunContextWrapper[AgentRunContext], features_path: str, sequence_id: str | None = None, layout: Literal["circular", "linear"] = "circular", label: Annotated[str | None, Field(max_length=200)] = None) -> FunctionResult[MapResult]:
    """Render features supplied by genome_read_features or sequence_find_orfs."""
    return await invoke(ctx.context, "genome_render_map", _calculate, {"features_path": features_path, "sequence_id": sequence_id, "layout": layout, "label": label}, FunctionResult[MapResult])


__all__ = ["genome_render_map", "MapResult"]

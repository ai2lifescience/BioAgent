"""Genome feature map generation."""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from math import cos, pi, sin
from pathlib import Path
import re
from typing import Any

from Bio import SeqIO

from tools.sequence import find_orfs, parse_fasta_text


FEATURE_COLORS = {
    "gene": "#2563eb",
    "CDS": "#0f766e",
    "ORF": "#7c3aed",
    "tRNA": "#d97706",
    "rRNA": "#dc2626",
    "repeat_region": "#64748b",
    "misc_feature": "#475569",
}


@dataclass(frozen=True)
class GenomeFeature:
    start: int
    end: int
    strand: int
    feature_type: str
    label: str


def create_genome_map(
    fasta_path: str | None = None,
    genbank_path: str | None = None,
    gff_path: str | None = None,
    output_dir: str = "runtime/genome_maps",
    label: str | None = None,
    layout: str = "circular",
    min_orf_length: int = 90,
) -> dict[str, Any]:
    """Create a compact SVG genome feature map from GenBank, GFF+FASTA, or FASTA."""
    clean_layout = layout.lower().strip()
    if clean_layout not in {"circular", "linear"}:
        raise ValueError("layout must be circular or linear.")

    genome_label, sequence, features, source_format = _load_genome_features(
        fasta_path=fasta_path,
        genbank_path=genbank_path,
        gff_path=gff_path,
        min_orf_length=min_orf_length,
    )
    if not sequence:
        raise ValueError("No genome sequence was found.")
    genome_length = len(sequence)
    if not features:
        features = _predict_orf_features(sequence, min_orf_length=min_orf_length)
        source_format = f"{source_format}+orfs"

    title = label or genome_label or "genome"
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    image_path = output_root / f"{_slugify(title)}_{clean_layout}_genome_map.svg"
    svg = _render_circular_svg(title, genome_length, features) if clean_layout == "circular" else _render_linear_svg(title, genome_length, features)
    image_path.write_text(svg, encoding="utf-8")

    counts = _feature_counts(features)
    return {
        "status": "ok",
        "image_path": str(image_path),
        "genome_map_path": str(image_path),
        "output_dir": str(output_root),
        "label": title,
        "layout": clean_layout,
        "source_format": source_format,
        "genome_length": genome_length,
        "feature_count": len(features),
        "gene_count": counts.get("gene", 0),
        "cds_count": counts.get("CDS", 0),
        "orf_count": counts.get("ORF", 0),
        "feature_type_counts": counts,
        "features": [_feature_to_dict(feature) for feature in features[:200]],
        "summary": f"Created {clean_layout} genome map with {len(features)} feature(s) over {genome_length} bp.",
    }


def _load_genome_features(
    fasta_path: str | None,
    genbank_path: str | None,
    gff_path: str | None,
    min_orf_length: int,
) -> tuple[str, str, list[GenomeFeature], str]:
    if genbank_path:
        return _load_genbank(genbank_path)
    if fasta_path and gff_path:
        label, sequence = _load_fasta(fasta_path)
        return label, sequence, _load_gff(gff_path), "gff+fasta"
    if fasta_path:
        label, sequence = _load_fasta(fasta_path)
        return label, sequence, _predict_orf_features(sequence, min_orf_length=min_orf_length), "fasta+orfs"
    raise ValueError("Provide genbank_path or fasta_path.")


def _load_fasta(path: str) -> tuple[str, str]:
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    records = parse_fasta_text(text)
    if not records:
        raise ValueError(f"No FASTA records found in {path}.")
    record = records[0]
    return record["id"], record["sequence"]


def _load_genbank(path: str) -> tuple[str, str, list[GenomeFeature], str]:
    record = SeqIO.read(path, "genbank")
    sequence = str(record.seq).upper()
    features: list[GenomeFeature] = []
    for item in record.features:
        feature_type = str(item.type)
        if feature_type not in {"gene", "CDS", "tRNA", "rRNA", "repeat_region", "misc_feature"}:
            continue
        start = int(item.location.start) + 1
        end = int(item.location.end)
        if end <= start:
            continue
        label = _feature_label(item.qualifiers, feature_type)
        strand = int(item.location.strand or 0)
        features.append(GenomeFeature(start=start, end=end, strand=strand, feature_type=feature_type, label=label))
    return record.id or Path(path).stem, sequence, features, "genbank"


def _load_gff(path: str) -> list[GenomeFeature]:
    features: list[GenomeFeature] = []
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 9:
            continue
        feature_type = parts[2]
        if feature_type not in {"gene", "CDS", "tRNA", "rRNA", "repeat_region", "misc_feature"}:
            continue
        try:
            start = int(parts[3])
            end = int(parts[4])
        except ValueError:
            continue
        strand = -1 if parts[6] == "-" else 1 if parts[6] == "+" else 0
        attributes = _parse_gff_attributes(parts[8])
        label = attributes.get("Name") or attributes.get("gene") or attributes.get("ID") or feature_type
        features.append(GenomeFeature(start=start, end=end, strand=strand, feature_type=feature_type, label=label))
    return features


def _predict_orf_features(sequence: str, min_orf_length: int) -> list[GenomeFeature]:
    features = []
    for index, orf in enumerate(find_orfs(sequence, min_length=min_orf_length), start=1):
        features.append(
            GenomeFeature(
                start=int(orf["start"]),
                end=int(orf["end"]),
                strand=1,
                feature_type="ORF",
                label=f"ORF{index}",
            )
        )
    return features


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


def _feature_to_dict(feature: GenomeFeature) -> dict[str, Any]:
    return {
        "start": feature.start,
        "end": feature.end,
        "strand": feature.strand,
        "type": feature.feature_type,
        "label": feature.label,
    }


def _feature_label(qualifiers: dict[str, list[str]], fallback: str) -> str:
    for key in ("gene", "locus_tag", "product", "label", "note"):
        values = qualifiers.get(key)
        if values:
            return str(values[0])
    return fallback


def _parse_gff_attributes(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for item in text.split(";"):
        if not item:
            continue
        if "=" in item:
            key, value = item.split("=", 1)
        elif " " in item:
            key, value = item.split(" ", 1)
        else:
            continue
        values[key.strip()] = value.strip().strip('"')
    return values


def _short_label(label: str, max_length: int = 18) -> str:
    clean = re.sub(r"\s+", " ", label).strip()
    return clean if len(clean) <= max_length else f"{clean[:max_length - 3]}..."


def _slugify(value: str, max_length: int = 48) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip().lower()).strip("-._")
    return (slug or "genome")[:max_length].strip("-._") or "genome"

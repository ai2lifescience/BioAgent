"""NCBI Entrez date-filter helpers."""

from __future__ import annotations

def _resolve_year_range(
    year: int | None,
    year_start: int | None,
    year_end: int | None,
) -> tuple[int, int] | None:
    if year is not None and (year_start is not None or year_end is not None):
        raise ValueError("Use either year or year_start/year_end, not both.")
    if year is not None:
        if year < 1:
            raise ValueError("year must be a positive integer.")
        return year, year
    if year_start is None and year_end is None:
        return None
    if year_start is None or year_end is None:
        raise ValueError("year_start and year_end must be provided together.")
    if year_start < 1 or year_end < 1:
        raise ValueError("year_start and year_end must be positive integers.")
    if year_start > year_end:
        raise ValueError("year_start cannot be greater than year_end.")
    return year_start, year_end

def _date_filter_term(year_range: tuple[int, int], date_field: str) -> str:
    field = date_field.strip().upper()
    if field not in {"PDAT", "MDAT"}:
        raise ValueError("date_field must be PDAT or MDAT.")
    start_year, end_year = year_range
    return f'("{start_year}/01/01"[{field}] : "{end_year}/12/31"[{field}])'

def _apply_year_filter(
    term: str,
    year_range: tuple[int, int] | None,
    date_field: str,
) -> str:
    clean_term = term.strip()
    if year_range is None:
        return clean_term
    return f"({clean_term}) AND {_date_filter_term(year_range, date_field)}"

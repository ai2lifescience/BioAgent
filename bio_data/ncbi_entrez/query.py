"""NCBI query construction helpers."""

from __future__ import annotations

from bio_data.ncbi_entrez.filters import _apply_year_filter
from bio_data.ncbi_entrez.spec import DEFAULT_DATE_FIELD, DEFAULT_PHIX174_A_G_GENES, PHIX174_SEARCH_TERM

def _build_default_query_if_needed(
    term: str | None,
    genes: list[str] | None,
    terms: list[str] | None,
    accessions: list[str] | None,
) -> tuple[str | None, list[str] | None]:
    if (
        (not term or not term.strip())
        and not terms
        and not accessions
        and not genes
    ):
        return PHIX174_SEARCH_TERM, list(DEFAULT_PHIX174_A_G_GENES)
    return term, genes

def _accession_term(accessions: list[str]) -> str:
    accession_terms = [f"{accession.strip()}[Accession]" for accession in accessions if accession.strip()]
    return " OR ".join(accession_terms)

def _gene_term(term: str, gene: str) -> str:
    clean_gene = gene.strip()
    if not clean_gene:
        raise ValueError("genes cannot include empty values.")
    if len(clean_gene) == 1 and clean_gene.isalpha():
        gene_clause = (
            f'({clean_gene}[Gene] OR "gene {clean_gene}"[All Fields] OR '
            f'"protein {clean_gene}"[All Fields])'
        )
    else:
        gene_clause = f"{clean_gene}[Gene]"
    return f"({term}) AND {gene_clause}"

def _build_queries(
    term: str | None,
    terms: list[str] | None,
    genes: list[str] | None,
    accessions: list[str] | None,
    year_range: tuple[int, int] | None = None,
    date_field: str = DEFAULT_DATE_FIELD,
) -> list[dict[str, str | None]]:
    queries: list[dict[str, str | None]] = []

    if terms:
        queries.extend(
            {"term": _apply_year_filter(item, year_range, date_field), "label": None}
            for item in terms
            if item.strip()
        )

    if accessions:
        query = _accession_term(accessions)
        if query:
            if term and term.strip():
                query = f"({term.strip()}) AND ({query})"
            query = _apply_year_filter(query, year_range, date_field)
            queries.append({"term": query, "label": "accessions"})

    if genes:
        if not term or not term.strip():
            raise ValueError("term is required when genes are provided.")
        base_term = _apply_year_filter(term.strip(), year_range, date_field)
        queries.extend(
            {"term": _gene_term(base_term, gene), "label": gene.strip()}
            for gene in genes
            if gene.strip()
        )

    if not queries and term and term.strip():
        queries.append(
            {"term": _apply_year_filter(term.strip(), year_range, date_field), "label": None}
        )

    if not queries:
        raise ValueError("Provide term, terms, accessions, or term plus genes.")

    return queries

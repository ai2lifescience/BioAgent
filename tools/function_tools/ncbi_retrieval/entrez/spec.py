"""NCBI tool schema and constants."""

from __future__ import annotations

import os

EUTILS_BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
DEFAULT_BATCH_SIZE = 500
DEFAULT_MAX_RECORDS = 10
REQUEST_TIMEOUT = 60
REQUEST_RETRIES = 2
DEFAULT_OUTPUT_DIR_PREFIX = os.getenv("BIOAGENT_NCBI_DOWNLOAD_DIR", "runtime/downloads/ncbi")
DEFAULT_OUTPUT_DIR_TEMPLATE = f"{DEFAULT_OUTPUT_DIR_PREFIX}_{{species}}"
PHIX174_SEARCH_TERM = '"Escherichia phage phiX174"[Organism]'
DEFAULT_PHIX174_A_G_GENES = ("A", "G")
DEFAULT_DATE_FIELD = "PDAT"

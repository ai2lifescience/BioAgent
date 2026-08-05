"""Entry point for the bactmut_fasta package."""

import sys
from typing import Optional, Sequence

from bactmut_fasta.cli import main


if __name__ == "__main__":
    main(sys.argv[1:])

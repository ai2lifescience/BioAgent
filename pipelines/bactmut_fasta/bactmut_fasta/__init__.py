"""Bacterial genome SNP detection and filtering pipeline."""

from .ref_manager import ReferenceManager, get_reference_manager

__version__ = "1.0.0"
__all__ = ["ReferenceManager", "get_reference_manager"]
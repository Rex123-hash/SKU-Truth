"""ETIM 10.0 classification model — the deterministic backbone of SKUTruth.

Provides the expected attribute set per product class (the denominator of our
completeness metric), canonical units, and allowed picklist values. Loaded from the
vendored ODC-BY licensed release; see data/etim/ATTRIBUTION.md.
"""

from .loader import DEFAULT_ARCHIVE, DEFAULT_RELEASE, load_etim
from .model import EtimAllowedValue, EtimClass, EtimFeature, EtimModel

__all__ = [
    "DEFAULT_ARCHIVE",
    "DEFAULT_RELEASE",
    "EtimAllowedValue",
    "EtimClass",
    "EtimFeature",
    "EtimModel",
    "load_etim",
]

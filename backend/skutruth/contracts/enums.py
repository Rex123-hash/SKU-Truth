"""Closed vocabularies used by the frozen data contracts.

FROZEN CONTRACT — see contracts/README.md before changing anything here.
Adding a member is a minor change. Removing or renaming one is a breaking change.
"""

from __future__ import annotations

from enum import StrEnum


class EtimFeatureType(StrEnum):
    """ETIM feature types, taken verbatim from ETIMARTCLASSFEATUREMAP.FEATURETYPE."""

    NUMERIC = "N"
    ALPHANUMERIC = "A"  # picklist constrained by ETIMARTCLASSFEATUREVALUEMAP
    LOGICAL = "L"  # boolean
    RANGE = "R"  # numeric min/max pair


class IdentityKind(StrEnum):
    """What the supplied brand + MPN actually resolved to.

    The distinction drives abstention: a FAMILY cannot carry variant-dependent
    attribute values, no matter how good the evidence for any single variant is.
    """

    EXACT_SKU = "EXACT_SKU"
    FAMILY = "FAMILY"
    AMBIGUOUS = "AMBIGUOUS"
    UNKNOWN = "UNKNOWN"


class SourceType(StrEnum):
    """Publisher class of an evidence document.

    Ordering here carries no authority weight — authority is computed per
    (source_type, modality, sku_specificity) in adjudication, never from this enum alone.
    """

    MANUFACTURER_API = "MANUFACTURER_API"
    MANUFACTURER_DATASHEET = "MANUFACTURER_DATASHEET"
    MANUFACTURER_PAGE = "MANUFACTURER_PAGE"
    AUTHORIZED_DISTRIBUTOR = "AUTHORIZED_DISTRIBUTOR"
    TRUSTED_CATALOG = "TRUSTED_CATALOG"
    GENERAL_WEB = "GENERAL_WEB"


class EvidenceModality(StrEnum):
    """Where inside a document the value came from.

    A parametric table in a distributor page outranks marketing prose in a
    manufacturer page; modality is an independent axis from SourceType.
    """

    SPEC_TABLE = "SPEC_TABLE"
    SPEC_LINE = "SPEC_LINE"
    PROSE = "PROSE"
    MARKETING = "MARKETING"
    IMAGE_OCR = "IMAGE_OCR"


class SkuSpecificity(StrEnum):
    """How tightly the evidence document binds to the resolved identity."""

    EXACT_SKU = "EXACT_SKU"
    FAMILY = "FAMILY"
    RANGE = "RANGE"  # a catalogue page covering many families


class AttributeStatus(StrEnum):
    """Terminal state of one attribute on the golden record.

    INSUFFICIENT_EVIDENCE and VARIANT_DEPENDENT are both abstentions: the system
    declines to commit to a value. They are distinguished because the remedy differs
    (find more evidence vs. ask the user which variant).
    """

    VERIFIED = "VERIFIED"  # >=2 independent evidence clusters agree
    SINGLE_SOURCE = "SINGLE_SOURCE"  # exactly 1 independent cluster
    CONFLICTED = "CONFLICTED"  # unresolved factual disagreement
    VARIANT_DEPENDENT = "VARIANT_DEPENDENT"  # abstention: value varies across the family
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"  # abstention: nothing trustworthy found


class ConflictCause(StrEnum):
    """Why two extracted values disagree.

    Only FACTUAL is a genuine source disagreement. The others are resolvable
    deterministically and must not be surfaced as "sources disagree".
    """

    VARIANT = "VARIANT"  # different SKUs in the same family
    CONDITION = "CONDITION"  # same product, different rating condition
    UNIT_FORMAT = "UNIT_FORMAT"  # same value, different unit or formatting
    STALENESS = "STALENESS"  # superseded document revision
    FACTUAL = "FACTUAL"  # genuine disagreement, same SKU and condition


class ResolvedBy(StrEnum):
    DETERMINISTIC = "deterministic"
    ESCALATED_MODEL = "escalated_model"
    HUMAN = "human"
    UNRESOLVED = "unresolved"


class RunMode(StrEnum):
    """Provenance of the network and model interactions behind a run.

    Surfaced verbatim in the UI. A REPLAY run is a replay of previously recorded
    real interactions and must never be presented as a fresh live run.
    """

    LIVE = "live"
    REPLAY = "replay"
    AUTO = "auto"  # replay when a cassette exists, otherwise live

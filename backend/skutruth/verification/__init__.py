"""Mechanical evidence verification.

Locating a quote is not verifying a claim. See ./README.md.
"""

from .adapters import claim_from_candidate, claims_from_run
from .errors import ArtifactBindingError, VerificationError
from .eval_adapter import citation_from_outcome
from .models import (
    ConditionOutcome,
    EvidenceMode,
    EvidenceUnit,
    ProductClaim,
    TextMatchMode,
    VerificationFailure,
    VerificationOutcome,
)
from .quantities import Quantity, Relation, parse_quantities, quantity_supports
from .table import TableEvidence, find_row_evidence
from .text import LocatedUnit, locate_units
from .verifier import (
    VERIFIER_VERSION,
    artifact_scope_supports_exact,
    verify_claim,
    verify_table_claim,
)

__all__ = [
    "VERIFIER_VERSION",
    "ArtifactBindingError",
    "ConditionOutcome",
    "EvidenceMode",
    "EvidenceUnit",
    "LocatedUnit",
    "ProductClaim",
    "Quantity",
    "Relation",
    "TableEvidence",
    "TextMatchMode",
    "VerificationError",
    "VerificationFailure",
    "VerificationOutcome",
    "artifact_scope_supports_exact",
    "citation_from_outcome",
    "claim_from_candidate",
    "claims_from_run",
    "find_row_evidence",
    "locate_units",
    "parse_quantities",
    "quantity_supports",
    "verify_claim",
    "verify_table_claim",
]

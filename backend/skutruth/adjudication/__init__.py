"""Verified facts into Unilog delivery records.

Verification asks whether the evidence supports a claim. Adjudication asks whether a
supported claim is safe to commit to this output, and mapping says where it goes. See
./README.md.
"""

from .assembly import (
    AssemblyResult,
    assemble_verified_attributes,
    build_attributes,
    write_attributes,
)
from .conflicts import conflicted_targets, resolve_conflicts
from .errors import AdjudicationError, MalformedMappingError, SlotCapacityError
from .mapping import (
    DEFAULT_MAPPING_DIR,
    MappingRegistry,
    available_registries,
    load_registry,
    parse_registry,
)
from .models import (
    SUPPORTED_VALUE_KINDS,
    AdjudicatedFact,
    AdjudicationDecision,
    AdjudicationReason,
    AssemblySummary,
    AttributeMappingSpec,
    ConditionPolicy,
    MappedUnilogAttribute,
    MappingAuthority,
)
from .policy import adjudicate, adjudicate_one, render_uom, render_value

__all__ = [
    "DEFAULT_MAPPING_DIR",
    "SUPPORTED_VALUE_KINDS",
    "AdjudicatedFact",
    "AdjudicationDecision",
    "AdjudicationError",
    "AdjudicationReason",
    "AssemblyResult",
    "AssemblySummary",
    "AttributeMappingSpec",
    "ConditionPolicy",
    "MalformedMappingError",
    "MappedUnilogAttribute",
    "MappingAuthority",
    "MappingRegistry",
    "SlotCapacityError",
    "adjudicate",
    "adjudicate_one",
    "assemble_verified_attributes",
    "available_registries",
    "build_attributes",
    "conflicted_targets",
    "load_registry",
    "parse_registry",
    "render_uom",
    "render_value",
    "resolve_conflicts",
    "write_attributes",
]

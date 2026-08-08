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


class IdentityDisposition(StrEnum):
    """What the supplied brand + MPN was determined to refer to.

    `FAMILY_OR_INCOMPLETE_REFERENCE` deliberately does not assert that the input is
    "not a SKU". Some channels list a family stem or a configurable base reference as
    an orderable record. What we can defend is narrower and sufficient: the reference
    does not by itself pin down every attribute, because at least one discriminator
    is unbound.
    """

    EXACT = "EXACT"
    FAMILY_OR_INCOMPLETE_REFERENCE = "FAMILY_OR_INCOMPLETE_REFERENCE"
    UNKNOWN = "UNKNOWN"
    CONTRADICTORY = "CONTRADICTORY"


class Applicability(StrEnum):
    """Whether an ETIM feature applies to this product at all.

    Distinct from whether a value was found. An inapplicable feature is not a gap,
    and must not count against coverage as though it were one.
    """

    APPLICABLE = "APPLICABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNKNOWN = "UNKNOWN"


class SourceType(StrEnum):
    """Publisher class of an evidence artifact.

    Ordering here carries no authority weight. Authority is a property of the
    (source_type, modality, identity_scope, verification) combination and is never
    read off this enum alone.
    """

    MANUFACTURER_API = "MANUFACTURER_API"
    MANUFACTURER_DATASHEET = "MANUFACTURER_DATASHEET"
    MANUFACTURER_PAGE = "MANUFACTURER_PAGE"
    AUTHORIZED_DISTRIBUTOR = "AUTHORIZED_DISTRIBUTOR"
    TRUSTED_CATALOG = "TRUSTED_CATALOG"
    GENERAL_WEB = "GENERAL_WEB"

    @property
    def is_manufacturer(self) -> bool:
        return self in {
            SourceType.MANUFACTURER_API,
            SourceType.MANUFACTURER_DATASHEET,
            SourceType.MANUFACTURER_PAGE,
        }


class EvidenceModality(StrEnum):
    """The kind of document region the value came from.

    A table is not automatically correct; it is less ambiguous to parse than prose,
    which is the only thing this axis claims.
    """

    SPEC_TABLE = "SPEC_TABLE"
    SPEC_LINE = "SPEC_LINE"
    PROSE = "PROSE"
    MARKETING = "MARKETING"
    IMAGE_OCR = "IMAGE_OCR"
    STRUCTURED_API = "STRUCTURED_API"


class IdentityScope(StrEnum):
    """How tightly the evidence artifact binds to a commercial reference."""

    EXACT_SKU = "EXACT_SKU"
    FAMILY = "FAMILY"
    RANGE = "RANGE"  # a catalogue page covering many families


class EvidenceVerification(StrEnum):
    """Whether the quoted span was mechanically located in the ingested artifact.

    This is the mechanism behind the project's central claim. A model can fabricate
    a quote or a page number; only `EXACT_SPAN` and `FUZZY_OCR_SPAN` mean we found
    the text ourselves in a hashed artifact we ingested.
    """

    EXACT_SPAN = "EXACT_SPAN"  # normalized quote located verbatim on the stated page
    FUZZY_OCR_SPAN = "FUZZY_OCR_SPAN"  # located above similarity threshold; OCR noise
    UNVERIFIED = "UNVERIFIED"  # not located, or artifact never ingested

    @property
    def may_support_accepted_value(self) -> bool:
        return self is not EvidenceVerification.UNVERIFIED


class DiscoveryMethod(StrEnum):
    """How a candidate artifact was found.

    Search grounding and URL Context are discovery signals. They never establish
    page-level provenance on their own; the artifact must still be ingested.
    """

    CURATED_CORPUS = "CURATED_CORPUS"
    GOOGLE_SEARCH_GROUNDING = "GOOGLE_SEARCH_GROUNDING"
    URL_CONTEXT = "URL_CONTEXT"
    DIRECT_URL = "DIRECT_URL"
    OPERATOR_SUPPLIED = "OPERATOR_SUPPLIED"


class AttributeStatus(StrEnum):
    """Whether a value was accepted onto the record.

    Support *strength* is `SupportGrade`; the *reason* for withholding is
    `WithheldReason`. Keeping the three separate stops "how sure are we" from being
    conflated with "did we commit" and with "why not".
    """

    ACCEPTED = "ACCEPTED"
    WITHHELD = "WITHHELD"


class WithheldReason(StrEnum):
    """Why no value was accepted. The user must be able to tell these apart."""

    NOT_FOUND = "NOT_FOUND"  # searched, nothing said it
    NOT_APPLICABLE = "NOT_APPLICABLE"  # the feature does not apply to this product
    VARIANT_DEPENDENT = "VARIANT_DEPENDENT"  # varies across the unresolved family
    CONFLICTED = "CONFLICTED"  # genuine disagreement, same identity and conditions
    UNSUPPORTED_SPAN = "UNSUPPORTED_SPAN"  # value proposed, span would not verify
    OUT_OF_IDENTITY_SCOPE = "OUT_OF_IDENTITY_SCOPE"  # family invariance not proven


class SupportGrade(StrEnum):
    """Coarse, rule-derived strength of support for an accepted value.

    Deliberately not a probability. With a 50-SKU corpus whose attribute rows are
    correlated within families, documents, and manufacturers, a decimal would be
    statistical theatre. The derivation rule is in `support.py` and is enforced by
    the `ProductAttribute` validator, so a grade cannot be hand-set.
    """

    A = "A"  # exact-scope, manufacturer, verified span, conditions complete
    B = "B"  # verified span, but secondary source, proven-family scope, or partial conditions
    C = "C"  # supported but weak on several axes; review recommended


class ConditionKind(StrEnum):
    """Qualifiers that bind a value to an operating point.

    Without these, `18 A` and `32 A` for one contactor look like a contradiction. They
    are not: they are AC-3 and AC-1 ratings of the same device.
    """

    UTILIZATION_CATEGORY = "UTILIZATION_CATEGORY"  # AC-1, AC-3, DC-13
    VOLTAGE = "VOLTAGE"
    FREQUENCY = "FREQUENCY"
    TEMPERATURE = "TEMPERATURE"
    PHASE = "PHASE"
    MEASUREMENT_BASIS = "MEASUREMENT_BASIS"  # nominal, minimum, maximum, typical
    REGION = "REGION"
    STANDARD = "STANDARD"  # IEC 60947-4-1, UL 508
    DUTY = "DUTY"
    OTHER = "OTHER"


class ConditionCompleteness(StrEnum):
    """Whether every qualifier the feature requires has been bound."""

    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    UNKNOWN = "UNKNOWN"


class FamilyInvariance(StrEnum):
    """Whether a value is safe to state when identity is family-level.

    Observing one child does not prove invariance across the family. `PROVEN`
    requires an explicit family/variant table or agreement across multiple exact
    child references.
    """

    NOT_REQUIRED = "NOT_REQUIRED"  # identity is EXACT; the question does not arise
    PROVEN = "PROVEN"
    UNPROVEN = "UNPROVEN"


class ConflictCause(StrEnum):
    """Why two observations differ. Only FACTUAL is a genuine source disagreement."""

    UNIT_FORMAT = "UNIT_FORMAT"  # same value, different representation
    QUALIFIER = "QUALIFIER"  # different operating point (AC-1 vs AC-3)
    VARIANT = "VARIANT"  # different children of one family
    ENTITY_SCOPE = "ENTITY_SCOPE"  # kit vs component, pack vs each, accessory
    REGION_STANDARD = "REGION_STANDARD"  # legitimate market/certification difference
    SCHEMA_MAPPING = "SCHEMA_MAPPING"  # correct value bound to the wrong ETIM feature
    EXTRACTION = "EXTRACTION"  # OCR or table-alignment error, not source disagreement
    STALENESS = "STALENESS"  # superseded artifact revision
    APPLICABILITY = "APPLICABILITY"  # applies to one variant, absent from another
    FACTUAL = "FACTUAL"  # same identity, same conditions, genuinely different


class ResolvedBy(StrEnum):
    DETERMINISTIC = "deterministic"
    ESCALATED_MODEL = "escalated_model"
    HUMAN = "human"
    UNRESOLVED = "unresolved"


class DerivationKind(StrEnum):
    """How a normalized value was produced from the raw source text.

    Every kind other than VERBATIM is a deterministic, versioned transform. None
    involves a language model.
    """

    VERBATIM = "VERBATIM"
    UNIT_CONVERSION = "UNIT_CONVERSION"  # 18000 mA -> 18 A
    RANGE_PARSE = "RANGE_PARSE"  # "24...230 V" -> min 24, max 230
    ENUM_MAP = "ENUM_MAP"  # source wording -> ETIM allowed value
    BOOLEAN_MAP = "BOOLEAN_MAP"  # "yes"/"x"/"included" -> true
    NUMERIC_PARSE = "NUMERIC_PARSE"  # decimal separators, thousands separators


class RunMode(StrEnum):
    """Provenance of the network and model interactions behind a run.

    Surfaced verbatim wherever a run is displayed. MIXED exists so that a
    partially-recorded run can be represented honestly rather than mislabelled; it
    is forbidden in published evaluation and in the public demo.
    """

    LIVE = "live"
    REPLAY = "replay"
    MIXED = "mixed"

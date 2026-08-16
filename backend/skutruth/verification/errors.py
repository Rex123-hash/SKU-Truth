"""Typed verification failures.

A claim that fails verification is a *result*, not an error — it comes back as an
`UNVERIFIED` outcome carrying a reason. These exceptions cover the cases where the
verifier cannot even begin: the artifact it was handed is not the artifact the claim
names, or the stored bytes no longer agree with their hashes.

Those fail closed on purpose. Verification whose input provenance is uncertain is not
weaker evidence; it is no evidence at all.
"""

from __future__ import annotations


class VerificationError(Exception):
    """Base class for every refusal in this package."""


class ArtifactBindingError(VerificationError):
    """The artifact supplied is not the one the claim's provenance names.

    Refused rather than verified against whatever was passed in. Checking a quote
    against a different document than the extraction read would produce a citation
    pointing at the wrong file.
    """

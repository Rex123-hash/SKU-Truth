"""The human domain-review workflow: what it prepares, and what it refuses to decide.

A `DomainReview` is the single thing that turns a locator into a publisher, so the tests
here are mostly about the tool *not* doing things. The repository has already had a
review attributed to a person who never performed one, inferred from git authorship, and
these tests exist so that cannot happen again by accident.
"""

from __future__ import annotations

import ast
import tomllib
from pathlib import Path

import pytest
from skutruth.discovery.domains import (
    DomainRegistry,
    RegistryAuthority,
    load_registry,
    parse_registry,
)
from skutruth.discovery.models import SearchResult
from skutruth.discovery.review import (
    HumanDomainReview,
    ReviewError,
    apply_review,
    build_packet,
    check_review_applies,
    render_review_block,
)
from skutruth.unilog.input import RawProductRow

REGISTRY_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "discovery" / "manufacturer_domains.demo.toml"
)

REGISTRY_TOML = """
name = "test-registry"
authority = "REVIEWED"

[[manufacturer]]
key = "kichler-lighting"
authority_hints = ["Kichler Lighting", "Kichler"]
domains = ["kichler.com"]
note = "Unverified."

[[manufacturer]]
key = "signify-philips-lighting"
authority_hints = ["Philips Lighting"]
locator_hints = ["Phillips Lighting"]
domains = ["lighting.philips.com", "signify.com"]
note = \"\"\"
A multi-line note. It contains text that looks like TOML structure:
[[manufacturer]]
key = "not-a-real-entry"
and it must never be mistaken for the start of a block.
\"\"\"

[[manufacturer]]
key = "makita"
authority_hints = ["Makita", "Makita Usa Inc"]
domains = ["makitatools.com", "makita.com"]

[hosts]
distributors = ["grainger.com"]
"""


def registry_from(text: str = REGISTRY_TOML) -> DomainRegistry:
    return parse_registry(tomllib.loads(text), source="test-registry")


def row(number: int, part_manuf: str, mpn: str) -> RawProductRow:
    return RawProductRow(row_number=number, raw={"Part_Manuf": part_manuf, "Mfg_Part_Num": mpn})


ROWS = [
    row(1, "Kichler Lighting (KICLI)", "45297BK"),
    row(2, "Kichler Lighting (KICLI)", "45573BK"),
    row(3, "Phillips Lighting (5831)", "603571"),
    row(4, "Makita Usa Inc (5142)", "XLC10ZW"),
    row(5, "Some Buying Group (9999)", "ABC123"),
]


def a_review(**overrides) -> HumanDomainReview:
    fields = {
        "manufacturer_key": "kichler-lighting",
        "confirmed_domains": ("kichler.com",),
        "reviewed_by": "A Real Person",
        "basis": "Opened kichler.com and confirmed it is operated by Kichler Lighting.",
        "reviewed_at": "2026-08-17",
    }
    fields.update(overrides)
    return HumanDomainReview(**fields)  # type: ignore[arg-type]


class TestPacketDecidesNothing:
    def test_every_candidate_comes_out_unreviewed(self):
        packet = build_packet(ROWS, registry_from())
        assert packet.candidates
        assert all(not c.already_reviewed for c in packet.candidates)
        assert packet.pending == packet.candidates

    def test_the_packet_has_no_field_that_can_express_a_confirmation(self):
        """Structural, not behavioural: there is nowhere to put a forged decision."""
        candidate = build_packet(ROWS, registry_from()).candidates[0]
        fields = set(candidate.__dataclass_fields__)
        assert not (fields & {"confirmed", "approved", "reviewed_by", "decision", "sign"})

    def test_building_a_packet_does_not_change_the_registry(self):
        registry = registry_from()
        build_packet(ROWS, registry)
        assert registry.licensing_entries == ()

    def test_a_packet_never_licenses_anything_however_much_evidence_it_gathers(self):
        """Search results are reading material, not a threshold that promotes an entry."""
        results = {
            "kichler-lighting": tuple(
                SearchResult(
                    url=f"https://kichler.com/p/{i}",
                    title="Kichler official",
                    rank=i,
                    query="q",
                    provider="test",
                )
                for i in range(1, 11)
            )
        }
        registry = registry_from()
        packet = build_packet(ROWS, registry, search_results=results, searched=True)
        kichler = next(c for c in packet.candidates if c.key == "kichler-lighting")
        assert len(kichler.search_results) == 10
        assert kichler.needs_review
        assert registry.licensing_entries == ()


class TestPacketContents:
    def test_rows_are_counted_per_manufacturer(self):
        packet = build_packet(ROWS, registry_from())
        by_key = {c.key: c for c in packet.candidates}
        assert by_key["kichler-lighting"].row_count == 2
        assert by_key["signify-philips-lighting"].row_count == 1

    def test_the_raw_spelling_is_preserved_not_corrected(self):
        packet = build_packet(ROWS, registry_from())
        philips = next(c for c in packet.candidates if c.key == "signify-philips-lighting")
        assert philips.spellings[0].raw == "Phillips Lighting (5831)"
        assert philips.spellings[0].display_name == "Phillips Lighting"

    def test_locator_only_spellings_are_marked_as_granting_nothing(self):
        packet = build_packet(ROWS, registry_from())
        philips = next(c for c in packet.candidates if c.key == "signify-philips-lighting")
        kichler = next(c for c in packet.candidates if c.key == "kichler-lighting")
        assert philips.spellings[0].grants_authority is False
        assert kichler.spellings[0].grants_authority is True

    def test_supplier_code_is_reported(self):
        packet = build_packet(ROWS, registry_from())
        kichler = next(c for c in packet.candidates if c.key == "kichler-lighting")
        assert kichler.spellings[0].supplier_code == "KICLI"

    def test_sample_mpns_are_collected(self):
        packet = build_packet(ROWS, registry_from())
        kichler = next(c for c in packet.candidates if c.key == "kichler-lighting")
        assert kichler.sample_mpns == ("45297BK", "45573BK")

    def test_a_manufacturer_the_input_never_mentions_is_omitted_by_default(self):
        packet = build_packet([row(1, "Kichler Lighting (KICLI)", "X")], registry_from())
        assert [c.key for c in packet.candidates] == ["kichler-lighting"]

    def test_include_unobserved_keeps_them(self):
        packet = build_packet(
            [row(1, "Kichler Lighting (KICLI)", "X")], registry_from(), include_unobserved=True
        )
        assert len(packet.candidates) == 3

    def test_an_unmatched_supplier_is_simply_absent(self):
        """`Some Buying Group` is in the input and in no registry entry. Not an error."""
        packet = build_packet(ROWS, registry_from())
        assert "Some Buying Group" not in str(packet.candidates)
        assert packet.rows_scanned == 5

    def test_hosts_named_by_search_are_reported_as_reading_material(self):
        results = {
            "kichler-lighting": (
                SearchResult(
                    url="https://www.kichler.com/a",
                    rank=1,
                    query="q",
                    provider="t",
                ),
                SearchResult(
                    url="https://grainger.com/b", rank=2, query="q", provider="t"
                ),
            )
        }
        packet = build_packet(ROWS, registry_from(), search_results=results, searched=True)
        kichler = next(c for c in packet.candidates if c.key == "kichler-lighting")
        assert kichler.observed_hosts == ("kichler.com", "grainger.com")

    def test_filtering_to_an_unknown_manufacturer_is_an_error(self):
        with pytest.raises(ReviewError):
            build_packet(ROWS, registry_from(), only=["not-a-manufacturer"])

    def test_candidates_are_ordered_stably(self):
        first = build_packet(ROWS, registry_from())
        second = build_packet(ROWS, registry_from())
        assert [c.key for c in first.candidates] == [c.key for c in second.candidates]


#: Modules that can answer "who is running this?". None may be imported by the workflow.
IDENTITY_MODULES = frozenset({"getpass", "subprocess", "pwd", "grp", "win32api", "socket"})

#: Calls that read an ambient identity, by the name they are invoked under.
IDENTITY_CALLS = frozenset({"getuser", "getlogin", "getpwuid", "getuid", "geteuid", "getfqdn"})

#: Environment variables that name a person. Reading one as a reviewer would be exactly
#: the inference this workflow exists to refuse.
IDENTITY_ENV_VARS = frozenset(
    {
        "USER",
        "USERNAME",
        "LOGNAME",
        "GIT_AUTHOR_NAME",
        "GIT_AUTHOR_EMAIL",
        "GIT_COMMITTER_NAME",
        "EMAIL",
    }
)

REVIEW_MODULE = (
    Path(__file__).resolve().parents[1] / "backend" / "skutruth" / "discovery" / "review.py"
)
REVIEW_SCRIPT = (
    Path(__file__).resolve().parents[1] / "scripts" / "review_manufacturer_domains.py"
)


def identity_surface(path: Path) -> dict[str, set[str]]:
    """What a module could use to discover who is running it.

    Parsed rather than grepped. Both files discuss git authorship at length in prose,
    explaining why it is never read, and a substring search cannot tell an explanation
    apart from an implementation.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    calls: set[str] = set()
    literals: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
            calls.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Attribute):
            calls.add(node.attr)
        elif isinstance(node, ast.Name):
            calls.add(node.id)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            literals.add(node.value)

    return {"imports": imports, "calls": calls, "literals": literals}


class TestReviewerIdentityIsNeverInferred:
    """Nothing may supply a reviewer's name except the reviewer."""

    @pytest.mark.parametrize("path", [REVIEW_MODULE, REVIEW_SCRIPT], ids=["module", "script"])
    def test_no_identity_reading_module_is_imported(self, path):
        assert not (identity_surface(path)["imports"] & IDENTITY_MODULES)

    @pytest.mark.parametrize("path", [REVIEW_MODULE, REVIEW_SCRIPT], ids=["module", "script"])
    def test_no_identity_reading_call_is_made(self, path):
        assert not (identity_surface(path)["calls"] & IDENTITY_CALLS)

    @pytest.mark.parametrize("path", [REVIEW_MODULE, REVIEW_SCRIPT], ids=["module", "script"])
    def test_no_identity_environment_variable_is_named(self, path):
        assert not (identity_surface(path)["literals"] & IDENTITY_ENV_VARS)

    def test_the_detector_would_catch_an_actual_lapse(self, tmp_path):
        """A test that can never fail protects nothing. Prove this one can."""
        lapse = tmp_path / "lapse.py"
        lapse.write_text("import getpass\nwho = getpass.getuser()\n", encoding="utf-8")
        surface = identity_surface(lapse)
        assert surface["imports"] & IDENTITY_MODULES
        assert surface["calls"] & IDENTITY_CALLS

    def test_prose_about_git_authorship_is_not_mistaken_for_reading_it(self, tmp_path):
        """The inverse: an explanation must not trip the detector."""
        prose = tmp_path / "prose.py"
        prose.write_text('"""Never read git config or getpass."""\n', encoding="utf-8")
        surface = identity_surface(prose)
        assert not (surface["imports"] & IDENTITY_MODULES)
        assert not (surface["calls"] & IDENTITY_CALLS)

    def test_a_review_without_a_reviewer_is_refused(self):
        with pytest.raises(ReviewError) as exc:
            a_review(reviewed_by="")
        assert "reviewed_by" in str(exc.value)

    def test_a_whitespace_reviewer_is_refused(self):
        with pytest.raises(ReviewError):
            a_review(reviewed_by="   ")

    def test_a_review_without_a_basis_is_refused(self):
        with pytest.raises(ReviewError) as exc:
            a_review(basis="")
        assert "basis" in str(exc.value)

    def test_a_review_with_no_confirmed_domain_is_refused(self):
        with pytest.raises(ReviewError):
            a_review(confirmed_domains=())

    def test_a_malformed_date_is_refused(self):
        with pytest.raises(ReviewError):
            a_review(reviewed_at="last Tuesday")


class TestApplyingAReview:
    def test_a_confirmed_review_promotes_exactly_one_entry(self):
        registry = registry_from()
        updated_text = apply_review(REGISTRY_TOML, a_review(), registry)
        updated = registry_from(updated_text)

        assert [e.key for e in updated.licensing_entries] == ["kichler-lighting"]

    def test_every_other_entry_stays_non_licensing(self):
        updated = registry_from(apply_review(REGISTRY_TOML, a_review(), registry_from()))
        others = {e.key for e in updated.unreviewed_entries}
        assert others == {"signify-philips-lighting", "makita"}

    def test_the_review_record_says_who_when_and_on_what_basis(self):
        updated = registry_from(apply_review(REGISTRY_TOML, a_review(), registry_from()))
        entry = next(e for e in updated.entries if e.key == "kichler-lighting")
        assert entry.review is not None
        assert entry.review.reviewed_by == "A Real Person"
        assert entry.review.reviewed_at == "2026-08-17"
        assert "kichler.com" in entry.review.basis

    def test_consulted_urls_are_recorded_in_the_basis(self):
        review = a_review(consulted_urls=("https://www.kichler.com/about",))
        updated = registry_from(apply_review(REGISTRY_TOML, review, registry_from()))
        entry = next(e for e in updated.entries if e.key == "kichler-lighting")
        assert "https://www.kichler.com/about" in entry.review.basis

    def test_the_rendered_block_is_valid_toml_naming_the_reviewer(self):
        block = render_review_block(a_review())
        assert block.startswith("[manufacturer.review]")
        assert 'reviewed_by = "A Real Person"' in block

    def test_a_quote_in_the_basis_cannot_break_out_of_the_string(self):
        review = a_review(basis='I checked "kichler.com" and it is theirs.')
        updated = registry_from(apply_review(REGISTRY_TOML, review, registry_from()))
        entry = next(e for e in updated.entries if e.key == "kichler-lighting")
        assert '"kichler.com"' in entry.review.basis

    def test_a_multi_line_note_is_not_mistaken_for_a_block_boundary(self):
        """The Philips entry's note contains a literal `[[manufacturer]]` line."""
        review = a_review(
            manufacturer_key="signify-philips-lighting",
            confirmed_domains=("lighting.philips.com", "signify.com"),
        )
        updated = registry_from(apply_review(REGISTRY_TOML, review, registry_from()))
        entry = next(e for e in updated.entries if e.key == "signify-philips-lighting")
        assert entry.review is not None
        assert "not-a-real-entry" not in {e.key for e in updated.entries}
        assert len(updated) == 3

    def test_applying_a_review_does_not_canonicalise_a_manufacturer_name(self):
        """Confirming Signify owns the domain says nothing about `Phillips Lighting`."""
        review = a_review(
            manufacturer_key="signify-philips-lighting",
            confirmed_domains=("lighting.philips.com", "signify.com"),
        )
        updated = registry_from(apply_review(REGISTRY_TOML, review, registry_from()))
        entry = next(e for e in updated.entries if e.key == "signify-philips-lighting")
        assert entry.locator_hints == ("Phillips Lighting",)
        assert entry.grants_authority("Phillips Lighting") is False
        assert entry.matches_for_locating("Phillips Lighting") is True


class TestApplyRefusals:
    def test_an_unknown_manufacturer_is_refused(self):
        with pytest.raises(ReviewError) as exc:
            check_review_applies(a_review(manufacturer_key="nobody"), registry_from())
        assert "no manufacturer entry" in str(exc.value)

    def test_confirming_only_some_domains_is_refused(self):
        """A review licenses every domain on the entry, so partial cannot be applied."""
        review = a_review(
            manufacturer_key="makita", confirmed_domains=("makitatools.com",)
        )
        with pytest.raises(ReviewError) as exc:
            check_review_applies(review, registry_from())
        assert "makita.com" in str(exc.value)

    def test_confirming_a_domain_not_on_the_entry_is_refused(self):
        review = a_review(confirmed_domains=("kichler.com", "kichler-outlet.example"))
        with pytest.raises(ReviewError) as exc:
            check_review_applies(review, registry_from())
        assert "not listed on the entry" in str(exc.value)

    def test_confirming_every_domain_is_accepted_in_any_order(self):
        review = a_review(
            manufacturer_key="makita", confirmed_domains=("makita.com", "makitatools.com")
        )
        assert check_review_applies(review, registry_from()).key == "makita"

    def test_a_www_prefix_is_normalised_rather_than_rejected(self):
        assert check_review_applies(
            a_review(confirmed_domains=("www.kichler.com",)), registry_from()
        )

    def test_overwriting_an_existing_review_is_refused(self):
        once = apply_review(REGISTRY_TOML, a_review(), registry_from())
        with pytest.raises(ReviewError) as exc:
            apply_review(once, a_review(reviewed_by="Someone Else"), registry_from(once))
        assert "already carries a review" in str(exc.value)


class TestShippedRegistryStaysUnreviewed:
    """The committed registry must not acquire a review as a side effect of anything."""

    def test_no_shipped_entry_licenses_evidence(self):
        registry = load_registry(REGISTRY_PATH)
        assert registry.licensing_entries == ()

    def test_the_shipped_registry_is_reviewed_grade_but_carries_no_review_records(self):
        registry = load_registry(REGISTRY_PATH)
        assert registry.authority is RegistryAuthority.REVIEWED
        assert all(e.review is None for e in registry.entries)

    def test_generating_a_packet_over_the_shipped_registry_licenses_nothing(self):
        registry = load_registry(REGISTRY_PATH)
        build_packet(ROWS, registry)
        assert load_registry(REGISTRY_PATH).licensing_entries == ()

"""Tests for the aggregator detection helper in scripts.common."""
from __future__ import annotations

import pytest

from scripts.common import is_aggregator, matched_aggregator


PLATFORMS = [
    "Free-Work",
    "Indeed",
    "Welcome to the Jungle",
    "LinkedIn",
    "Monster",
    "France Travail",
]


class TestMatchedAggregator:
    def test_exact_match(self):
        assert matched_aggregator("Free-Work", PLATFORMS) == "Free-Work"

    def test_case_insensitive(self):
        assert matched_aggregator("free-work", PLATFORMS) == "Free-Work"
        assert matched_aggregator("FREE-WORK", PLATFORMS) == "Free-Work"

    def test_suffix_tolerated(self):
        assert matched_aggregator("Free-Work SA", PLATFORMS) == "Free-Work"
        assert matched_aggregator("Indeed France", PLATFORMS) == "Indeed"

    def test_multiword_platform(self):
        assert matched_aggregator("Welcome to the Jungle", PLATFORMS) == "Welcome to the Jungle"
        assert matched_aggregator("France Travail", PLATFORMS) == "France Travail"

    def test_word_boundary_avoids_substring_collision(self):
        # "LinkedIn" should not match a company called "LinkedInSoft Corp".
        assert matched_aggregator("LinkedInSoft Corp", PLATFORMS) is None

    def test_direct_employer_not_matched(self):
        assert matched_aggregator("Omnitech SA", PLATFORMS) is None
        assert matched_aggregator("Acme Corp", PLATFORMS) is None

    def test_empty_and_none_inputs(self):
        assert matched_aggregator("", PLATFORMS) is None
        assert matched_aggregator("Acme Corp", []) is None

    def test_empty_platform_entry_skipped(self):
        # Defensive: config may ship with a stray blank entry.
        assert matched_aggregator("Acme Corp", ["", "Free-Work"]) is None
        assert matched_aggregator("Free-Work", ["", "Free-Work"]) == "Free-Work"


class TestIsAggregator:
    @pytest.mark.parametrize(
        "name,expected",
        [
            ("Free-Work", True),
            ("free-work", True),
            ("Indeed France", True),
            ("Omnitech SA", False),
            ("LinkedInSoft Corp", False),
            ("", False),
        ],
    )
    def test_boolean_wrapper(self, name: str, expected: bool):
        assert is_aggregator(name, PLATFORMS) is expected

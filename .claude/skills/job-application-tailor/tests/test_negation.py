"""Tests for scripts/_negation.py (shared by claims_guard and the grounding checks)."""
from __future__ import annotations

import pytest

from scripts._negation import (
    affirmative_clauses,
    affirmative_sentences,
    is_negated,
    split_clauses,
)


def test_clauses_split_on_punctuation_dashes_and_brackets():
    assert split_clauses("Données : PostgreSQL, SQLite (local) — Redis; Go. Rust") == [
        "Données", "PostgreSQL", "SQLite", "local", "Redis", "Go.", "Rust"]


@pytest.mark.parametrize("text", [
    "Outils no-code et low-code", "non-regression tests", "un pas-à-pas détaillé",
])
def test_negation_word_followed_by_hyphen_is_not_a_negation(text):
    assert not is_negated(text)


@pytest.mark.parametrize("text", [
    "Pas de Kubernetes", "jamais Hibernate", "ne pas reprendre", "n'utilise plus Java",
    "aucune expérience", "sans Docker", "no Go here", "never Ruby", "we don't use Rails",
    "Terraform reste à apprendre", "non utilisé",
])
def test_negation_words_are_detected(text):
    assert is_negated(text)


def test_only_negated_clauses_are_dropped():
    text = "Bases de données : surtout PostgreSQL ; SQLite en local. Pas de SQL Server ici."
    assert affirmative_clauses(text) == ["Bases de données", "surtout PostgreSQL", "SQLite en local."]


def test_contrast_keeps_the_affirmative_side():
    assert affirmative_clauses("Spring Boot, jamais Hibernate.") == ["Spring Boot"]
    assert affirmative_clauses("We use Podman, not Docker") == ["We use Podman"]


def test_negation_covers_the_subject_list_it_predicates():
    assert affirmative_clauses("Razor, Blazor ne sont pas utilisés.") == []
    assert affirmative_clauses("Context: Razor, Blazor are not used") == ["Context"]


def test_negation_after_a_label_covers_the_label():
    assert affirmative_clauses("Kubernetes : jamais utilisé") == []
    assert affirmative_clauses("Docker, Kubernetes — not in this role") == []
    # a long clause before the colon is a statement, not a label
    assert affirmative_clauses("Built the billing services in Java and Kotlin: never Scala") == [
        "Built the billing services in Java and Kotlin"]


def test_sentence_scope_drops_the_whole_rule_sentence():
    text = "**Kafka — évalué, pas retenu.** RabbitMQ est l'outil maîtrisé."
    assert affirmative_sentences(text) == ["RabbitMQ est l'outil maîtrisé."]
    assert "Kafka" in affirmative_clauses(text)[0]  # clause scope would keep it

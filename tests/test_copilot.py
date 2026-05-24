"""
Tests for app/copilot/ — chunker, embedder, retriever, classifier, copilot.
No external API calls — all network-dependent code is mocked.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.copilot.chunker import chunk_text, _split_sentences, _extract_heading
from app.copilot.classifier import classify_chunk, requires_professional_review, RiskClassifier
from app.copilot.retriever import cosine_similarity


# ---------------------------------------------------------------------------
# Chunker tests
# ---------------------------------------------------------------------------

class TestSplitSentences:
    def test_basic_split(self):
        text = "Hello world. This is a test. Final sentence."
        sentences = _split_sentences(text)
        assert len(sentences) >= 2

    def test_empty_string(self):
        assert _split_sentences("") == []

    def test_single_sentence(self):
        result = _split_sentences("Just one sentence.")
        assert len(result) >= 1


class TestExtractHeading:
    def test_markdown_heading(self):
        assert _extract_heading("# Section Title\nBody text") == "Section Title"

    def test_markdown_h2(self):
        assert _extract_heading("## Sub Section\nContent") == "Sub Section"

    def test_all_caps_heading(self):
        result = _extract_heading("RECO REGISTRATION REQUIREMENTS\nDetails here.")
        assert result is not None

    def test_normal_text_no_heading(self):
        assert _extract_heading("This is regular paragraph text.") is None

    def test_empty(self):
        assert _extract_heading("") is None


class TestChunkText:
    SAMPLE_TEXT = """
# RECO Registration Requirements

All real estate agents in Ontario must be registered with RECO under TRESA.
Registration requires completion of the Salesperson Registration Education Program.
Without valid registration, you cannot trade in real estate.

## Continuing Education

Registrants must complete 24 hours of continuing education every two years.
This includes mandatory modules on ethics and compliance.
Failure to complete CE results in registration suspension.

## Fees and Renewal

Registration fees are set annually by RECO.
Renewal is required every two years.
Late renewal may result in additional fees or lapse of registration.
"""

    def test_returns_list_of_dicts(self):
        chunks = chunk_text(self.SAMPLE_TEXT, doc_id="test-doc", source_path="test.txt")
        assert isinstance(chunks, list)
        assert len(chunks) > 0

    def test_chunk_has_required_fields(self):
        chunks = chunk_text(self.SAMPLE_TEXT, doc_id="test-doc", source_path="test.txt")
        required = {"doc_id", "source_path", "chunk_index", "heading", "body", "topic", "jurisdiction", "audience"}
        for chunk in chunks:
            assert required.issubset(set(chunk.keys()))

    def test_chunk_indices_are_sequential(self):
        chunks = chunk_text(self.SAMPLE_TEXT, doc_id="test-doc", source_path="test.txt")
        indices = [c["chunk_index"] for c in chunks]
        assert indices == list(range(len(indices)))

    def test_doc_id_preserved(self):
        chunks = chunk_text(self.SAMPLE_TEXT, doc_id="reco-guide", source_path="reco/guide.txt")
        assert all(c["doc_id"] == "reco-guide" for c in chunks)

    def test_jurisdiction_default(self):
        chunks = chunk_text(self.SAMPLE_TEXT, doc_id="test", source_path="test.txt")
        assert all(c["jurisdiction"] == "ontario" for c in chunks)

    def test_custom_jurisdiction(self):
        chunks = chunk_text(self.SAMPLE_TEXT, doc_id="test", source_path="test.txt", jurisdiction="bc")
        assert all(c["jurisdiction"] == "bc" for c in chunks)

    def test_body_not_empty(self):
        chunks = chunk_text(self.SAMPLE_TEXT, doc_id="test", source_path="test.txt")
        assert all(len(c["body"]) > 0 for c in chunks)

    def test_short_text_single_chunk(self):
        chunks = chunk_text("Short text.", doc_id="short", source_path="short.txt")
        assert len(chunks) == 1

    def test_heading_extracted(self):
        chunks = chunk_text(self.SAMPLE_TEXT, doc_id="test", source_path="test.txt")
        headings = [c["heading"] for c in chunks if c["heading"]]
        assert len(headings) > 0


# ---------------------------------------------------------------------------
# Classifier tests
# ---------------------------------------------------------------------------

class TestClassifier:
    def test_critical_dual_agency(self):
        assert classify_chunk("Dual agency creates a conflict of interest.") == "critical"

    def test_critical_legal_advice(self):
        assert classify_chunk("This constitutes legal advice.") == "critical"

    def test_high_reco(self):
        level = classify_chunk("RECO registration is mandatory for all agents.")
        assert level in ("high", "critical")

    def test_high_tresa(self):
        level = classify_chunk("Under TRESA, registrants must disclose all material facts.")
        assert level in ("high", "critical")

    def test_medium_mortgage(self):
        level = classify_chunk("The buyer obtained a mortgage pre-approval.")
        assert level in ("medium", "high")

    def test_medium_aps(self):
        level = classify_chunk("The APS contains the purchase price and deposit amount.")
        assert level == "medium"

    def test_low_neighbourhood(self):
        level = classify_chunk("Brampton is a growing city in Peel Region with many parks.")
        assert level == "low"

    def test_requires_review_high(self):
        assert requires_professional_review("high") is True

    def test_requires_review_critical(self):
        assert requires_professional_review("critical") is True

    def test_no_review_low(self):
        assert requires_professional_review("low") is False

    def test_no_review_medium(self):
        assert requires_professional_review("medium") is False

    def test_heading_affects_classification(self):
        classifier = RiskClassifier()
        # Neutral body but high-risk heading
        level = classifier.classify("The following rules apply.", heading="RECO Code of Ethics")
        assert level in ("high", "critical")


# ---------------------------------------------------------------------------
# Retriever — cosine similarity
# ---------------------------------------------------------------------------

class TestCosineSimilarity:
    def test_identical_vectors(self):
        v = [1.0, 0.0, 0.0]
        assert abs(cosine_similarity(v, v) - 1.0) < 1e-6

    def test_orthogonal_vectors(self):
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        assert abs(cosine_similarity(a, b)) < 1e-6

    def test_opposite_vectors(self):
        a = [1.0, 0.0]
        b = [-1.0, 0.0]
        assert abs(cosine_similarity(a, b) + 1.0) < 1e-6

    def test_zero_vector(self):
        assert cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0

    def test_mismatched_lengths(self):
        assert cosine_similarity([1.0, 2.0], [1.0]) == 0.0

    def test_similar_vectors_high_score(self):
        a = [1.0, 0.9, 0.8]
        b = [1.0, 0.85, 0.75]
        sim = cosine_similarity(a, b)
        assert sim > 0.99

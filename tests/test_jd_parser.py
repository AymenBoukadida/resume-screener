"""Tests for JD section splitting and requirement extraction."""

from extractors.keyword_extractor import KeywordExtractor
from parsers.jd_parser import JDParser


def make_parser():
    return JDParser(KeywordExtractor())


class TestSectionSplitting:
    def test_structured_sections(self):
        jd = "\n".join([
            "Required skills:",
            "- Python",
            "- Docker",
            "",
            "Preferred:",
            "- React",
        ])
        requirements = make_parser().parse(jd)
        assert requirements.required_skills == {"python", "docker"}
        assert requirements.preferred_skills == {"react"}
        assert requirements.has_explicit_sections

    def test_french_inline_header(self):
        jd = "Compétences requises : Python, Django"
        requirements = make_parser().parse(jd)
        assert requirements.required_skills == {"python", "django"}

    def test_unstructured_fallback_treats_everything_as_required(self):
        jd = "Looking for someone who knows Python and Docker"
        requirements = make_parser().parse(jd)
        assert requirements.required_skills == {"python", "docker"}
        assert not requirements.has_explicit_sections
        assert requirements.keywords == set()

    def test_sentence_with_period_is_not_a_header(self):
        sections = make_parser()._split_sections(
            "Required skills:\nPython\nWe value experience.\nDocker"
        )
        assert "Docker" in sections["required"]
        assert sections["experience"] == []

    def test_pronoun_opened_sentence_is_not_a_header(self):
        sections = make_parser()._split_sections(
            "Required skills:\nPython\nWe value experience\nDocker"
        )
        assert "Docker" in sections["required"]
        assert sections["experience"] == []

    def test_long_header_with_colon_is_a_header(self):
        sections = make_parser()._split_sections(
            "Required qualifications for this role:\nPython"
        )
        assert "Python" in sections["required"]


class TestExperienceThreshold:
    def test_jd_years_use_range_minimum(self):
        requirements = make_parser().parse(
            "Python developer role. 3-5 years experience required."
        )
        assert requirements.experience_years == 3

    def test_single_figure_passes_through(self):
        requirements = make_parser().parse("Senior role, 7+ years required.")
        assert requirements.experience_years == 7

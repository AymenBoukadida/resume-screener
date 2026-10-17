"""Tests for taxonomy skill matching and years-of-experience extraction."""

import pytest

from extractors.keyword_extractor import KeywordExtractor, normalize_text


@pytest.fixture()
def extractor():
    return KeywordExtractor()


class TestSkillMatching:
    def test_basic_skills_found(self, extractor):
        assert extractor.extract_skills(
            "Developed Python and JavaScript services"
        ) == {"python", "javascript"}

    def test_java_does_not_match_inside_javascript(self, extractor):
        assert extractor.extract_skills("JavaScript everywhere") == {"javascript"}

    def test_java_matches_standalone(self, extractor):
        assert extractor.extract_skills("Java and JavaScript") == {"java", "javascript"}

    def test_special_character_skills(self, extractor):
        assert extractor.extract_skills("Knows C++ and C#") == {"c++", "c#"}

    def test_french_accent_insensitive(self, extractor):
        assert extractor.extract_skills(
            "Développeur Python, expériences en API REST"
        ) == {"python", "rest api"}

    def test_normalize_text_strips_accents_and_case(self):
        assert normalize_text("DÉVELOPPEMENT Web") == "developpement web"


class TestExperienceYears:
    @pytest.mark.parametrize("mode, expected", [("max", 5), ("min", 3)])
    def test_range_uses_requested_bound(self, extractor, mode, expected):
        assert extractor.extract_experience_years("3-5 years of Python", mode) == expected

    def test_word_to_range_min(self, extractor):
        assert extractor.extract_experience_years("3 to 5 years", "min") == 3

    def test_plus_form(self, extractor):
        assert extractor.extract_experience_years("5+ years of experience") == 5

    def test_french_ans(self, extractor):
        assert extractor.extract_experience_years("5 ans d'expérience") == 5

    def test_french_spelled_number(self, extractor):
        assert extractor.extract_experience_years("cinq années d'expérience") == 5

    def test_decimal_point_is_not_two_numbers(self, extractor):
        # With the old pattern, the "5" in "1.5" matched on its own.
        assert extractor.extract_experience_years("1.5 years of Python") == 1

    def test_decimal_comma_french(self, extractor):
        assert extractor.extract_experience_years("1,5 an de stage") == 1

    @pytest.mark.parametrize("mode, expected", [("max", 10), ("min", 3)])
    def test_multiple_mentions(self, extractor, mode, expected):
        assert extractor.extract_experience_years(
            "10 years in Python, 3 years with Docker", mode
        ) == expected

    def test_no_mention(self, extractor):
        assert extractor.extract_experience_years("No time units here") == 0

    def test_invalid_mode_rejected(self, extractor):
        with pytest.raises(ValueError):
            extractor.extract_experience_years("5 years", mode="average")

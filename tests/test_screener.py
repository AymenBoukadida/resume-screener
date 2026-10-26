"""Extraction and scoring checks for arbitrary JDs and CVs."""

from datetime import date

from extractors.experience import extract_experience_years
from extractors.fields import extract_fields
from extractors.keyword_extractor import KeywordExtractor
from extractors.term_miner import match_terms
from matcher.feedback import generate_feedback
from matcher.scorer import ScoringEngine, active_weights
from parsers.jd_parser import JDParser
from parsers.resume_parser import ResumeParser, find_resume_files


def test_preferred_qualifications_not_stolen_by_required():
    jd = """
Minimum qualifications:
- Python
- Django

Preferred qualifications:
- AWS
- Docker
"""
    reqs = JDParser().parse(jd)
    assert "python" in reqs.required_skills
    assert "django" in reqs.required_skills
    assert "aws" in reqs.preferred_skills
    assert "docker" in reqs.preferred_skills
    assert "aws" not in reqs.required_skills


def test_markdown_and_numbered_lists():
    jd = """
## Required skills
1. Python
2. SQL

### Nice to have
- Kubernetes
"""
    reqs = JDParser().parse(jd)
    assert "python" in reqs.required_skills
    assert "sql" in reqs.required_skills
    assert "kubernetes" in reqs.preferred_skills


def test_empty_preferred_renormalizes_weights():
    reqs = JDParser().parse(
        "Required Skills:\n- Python\n- Django\n\nExperience:\n- 3 years"
    )
    engine = ScoringEngine()
    weights = active_weights(engine.weights, reqs)
    assert weights["preferred_skills"] == 0.0
    assert abs(sum(weights.values()) - 1.0) < 1e-9
    assert weights["required_skills"] > engine.weights["required_skills"]


def test_negation_skips_skill():
    extractor = KeywordExtractor()
    text = "Frontend developer. I have not worked with Java or backend systems. React, Vue."
    skills = extractor.extract_skills(text)
    assert "java" not in skills
    assert "react" in skills
    assert "vue" in skills


def test_node_version_alias():
    extractor = KeywordExtractor()
    assert "node.js" in extractor.extract_skills("Production services on Node 18")


def test_false_positive_years_ignored():
    text = "Acme is a 5 years old company founded 10 years ago. I have 3 years of Python."
    assert extract_experience_years(text, mode="max") == 3


def test_date_ranges_merged(monkeypatch):
    text = """
Engineer — Co A (Jan 2019 – Dec 2021)
Engineer — Co B (2021 – present)
"""
    years = extract_experience_years(text, mode="max", today=date(2024, 1, 1))
    assert years >= 4


NURSE_JD = """
Registered Nurse - Acute Care
We are hiring a compassionate Registered Nurse for our oncology unit.

Required Qualifications:
- Current RN license in good standing
- BLS and ACLS certification
- 2+ years of acute care nursing experience
- Strong patient assessment and care planning skills
- Experience with electronic health records (Epic or Meditech)
- IV therapy and wound care
Charge nurse or preceptor experience preferred.
Oncology and palliative care experience an asset.
PICC line insertion is a nice to have.
Bilingual French/English is required.
"""

WELDER_JD = """
Welder
Required:
- 5+ years of welding experience
- Flux core welding and MIG welding
- Ability to read blueprints
- Forklift certification an asset
- CWB certification preferred
Must be available for night shifts.
"""


def test_short_requirement_lines_are_not_section_headers():
    jd = """
Required:
- Charge nurse or preceptor experience
- 5+ years of welding experience
- BLS certification

Preferred:
- Oncology
"""
    reqs = JDParser().parse(jd)
    assert "charge nurse" in reqs.required_skills
    assert "preceptor" in reqs.required_skills
    assert "welding" in reqs.required_skills
    assert "bls" in reqs.required_skills
    assert "oncology" in reqs.preferred_skills


def test_preferred_cues_override_required_section():
    jd = """
Required:
- Python
- Forklift certification an asset
- CWB certification preferred
"""
    reqs = JDParser().parse(jd)
    assert "python" in reqs.required_skills
    assert "forklift operation" in reqs.preferred_skills
    assert "cwb" in reqs.preferred_skills
    assert "forklift operation" not in reqs.required_skills


def test_nurse_jd_extracts_clinical_skills():
    reqs = JDParser().parse(NURSE_JD)
    assert {
        "acls", "bls", "rn license", "patient assessment",
        "care planning", "electronic health records",
    } <= reqs.required_skills
    assert {
        "charge nurse", "oncology", "palliative care", "picc line insertion",
    } <= reqs.preferred_skills
    forbidden = reqs.required_skills | reqs.preferred_skills
    assert "french/english" not in forbidden
    assert "nice" not in forbidden
    assert "asset" not in forbidden


def test_welder_jd_does_not_duplicate_required_as_preferred():
    reqs = JDParser().parse(WELDER_JD)
    assert "welding" in reqs.required_skills
    assert "welding" not in reqs.preferred_skills
    assert "forklift operation" in reqs.preferred_skills
    assert "cwb" in reqs.preferred_skills


def test_finance_jd_extracts_domain_terms():
    jd = """
Financial Analyst
Required:
- CPA designation
- 5+ years of financial reporting experience
- Advanced Excel and financial modeling
Preferred:
- IFRS
- Power BI
- Experience with SAP an asset
"""
    reqs = JDParser().parse(jd)
    assert {"cpa", "financial reporting", "financial analysis"} <= reqs.required_skills
    assert {"ifrs", "power bi", "sap"} <= reqs.preferred_skills
    assert reqs.experience_years == 5


def test_mined_terms_match_common_inflections():
    assert match_terms("I worked as a welder for ten years", {"welding"}) == {"welding"}
    assert match_terms("monitored security alerts", {"monitoring"}) == {"monitoring"}


def test_fields_english_resume():
    text = """Marie Dubois, RN
marie.dubois@example.com | (514) 555-0199 | Montreal, QC
Registered Nurse | Acute Care

EDUCATION
Bachelor of Science in Nursing, McGill University, 2016

CERTIFICATIONS
- Registered Nurse (RN), OIIQ
- BLS, ACLS

LANGUAGES
- French (native), English (fluent)
"""
    fields = extract_fields(text)
    assert fields.name == "Marie Dubois"
    assert fields.email == "marie.dubois@example.com"
    assert fields.phone == "(514) 555-0199"
    assert fields.location == "Montreal, QC"
    assert fields.headline == "Registered Nurse"
    assert fields.education_level == "Bachelor"
    assert any("McGill" in item for item in fields.education)
    assert any("BLS" in item for item in fields.certifications)
    assert {"English", "French"} <= set(fields.languages)


def test_fields_markdown_resume():
    text = """# Alex Martin

**Python Developer**

alex.martin@example.com | Montreal, Canada

## Education

Bachelor of Computer Science, McGill University
"""
    fields = extract_fields(text)
    assert fields.name == "Alex Martin"
    assert fields.headline == "Python Developer"
    assert fields.email == "alex.martin@example.com"
    assert fields.location == "Montreal, Canada"
    assert fields.education_level == "Bachelor"


def test_fields_french_resume():
    text = """Julie Tremblay
julie.tremblay@example.com | +33 6 12 34 56 78 | Montréal, Canada
Développeuse Python

FORMATION
Master Informatique, Université de Montréal, 2018

LANGUES
- Français (langue maternelle), anglais (courant)
"""
    fields = extract_fields(text)
    assert fields.name == "Julie Tremblay"
    assert fields.email == "julie.tremblay@example.com"
    assert fields.phone == "+33 6 12 34 56 78"
    assert fields.location == "Montréal, Canada"
    assert fields.headline == "Développeuse Python"
    assert fields.education_level == "Master"
    assert {"French", "English"} <= set(fields.languages)


def test_experience_weight_dropped_when_jd_has_no_years():
    reqs = JDParser().parse("Required:\n- Python\n- SQL")
    engine = ScoringEngine()
    score = engine.score_candidate("cv.txt", {"python", "sql"}, 0, reqs)
    assert engine.default_expected_years == 0
    assert score.applied_weights["experience"] == 0.0
    assert "experience" in score.dropped_components
    assert score.total == 100.0


def test_feedback_reports_missing_contact_details():
    reqs = JDParser().parse("Required:\n- Python\n- SQL")
    engine = ScoringEngine()
    candidate = engine.score_candidate(
        "cv.txt", {"python", "sql"}, 0, reqs, fields={"name": "Jane Doe"}
    )
    tips = generate_feedback(
        candidate, reqs, engine.default_expected_years, fields=candidate.fields
    )
    text = " ".join(tips).lower()
    assert "email" in text
    assert "phone" in text
    assert "location" in text


def test_markdown_resume_and_pdf_dehyphenation(tmp_path):
    path = tmp_path / "cv.md"
    path.write_text(
        "Déve-\nloppement Python\njane@example.com\n", encoding="utf-8"
    )
    text = ResumeParser().parse(path)
    assert "Développement Python" in text
    assert path in find_resume_files(tmp_path)


def test_find_resume_files_recursive(tmp_path):
    nested = tmp_path / "nested"
    nested.mkdir()
    (tmp_path / "top.txt").write_text("Python", encoding="utf-8")
    (nested / "nested.docx").write_bytes(b"not a real docx")
    assert {p.name for p in find_resume_files(tmp_path)} == {"top.txt"}
    assert {
        p.name for p in find_resume_files(tmp_path, recursive=True)
    } == {"top.txt", "nested.docx"}


def test_parenthetical_advantage_header_and_required_overrides():
    jd = """
Job Requirements:
- Security operations
Certifications (Considered an Advantage)
- ITIL Foundation.
Bachelor's degree in Computer Science.
Minimum 3 years of experience in IT.
"""
    reqs = JDParser().parse(jd)
    assert "itil" in reqs.preferred_skills
    assert "bachelor's degree" in reqs.required_skills
    assert reqs.experience_years == 3
    assert "considered" not in reqs.preferred_skills


def test_generic_single_tokens_not_canonicalized():
    jd = """
Required skills:
- Security
- Activities
- Policies
- Group policies
"""
    reqs = JDParser().parse(jd)
    assert "security+" not in reqs.required_skills
    assert "adl assistance" not in reqs.required_skills
    assert "hr policies" not in reqs.required_skills
    assert "group policies" not in reqs.required_skills
    assert "active directory" in reqs.required_skills


def test_theme_subheadings_and_duty_words_not_mined():
    jd = """
Job Requirements:
Security Operations & Vulnerability Management
Monitor, track, and report security vulnerabilities.
Participate in audits.
Participate in reviews.
Participate in assessments.
Contribute to continuous improvement initiatives.
Contribute to technology refresh initiatives.
Participate in security awareness initiatives.
Reporting & Governance
Track remediation KPIs.
"""
    reqs = JDParser().parse(jd)
    assert "governance" not in reqs.required_skills
    assert "participate" not in reqs.required_skills
    assert "initiatives" not in reqs.required_skills


def test_inline_required_label_with_extra_words():
    jd = """
Job Requirements & Knowledge:
Security Operations & Vulnerability Management
Provide Level 2 support including access management.
"""
    reqs = JDParser().parse(jd)
    assert "access management" in reqs.required_skills

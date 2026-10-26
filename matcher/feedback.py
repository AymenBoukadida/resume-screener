"""CV-improvement feedback based on screening results."""

from typing import Dict, List, Optional

from matcher.scorer import CandidateScore
from parsers.jd_parser import JobRequirements


def generate_feedback(
    candidate: CandidateScore,
    requirements: JobRequirements,
    default_expected_years: int = 0,
    fields: Optional[Dict[str, object]] = None,
) -> List[str]:
    """Return improvement tips for one résumé."""
    tips: List[str] = []
    target_years = requirements.experience_years or default_expected_years

    if fields is not None:
        email = str(fields.get("email") or "").strip()
        phone = str(fields.get("phone") or "").strip()
        location = str(fields.get("location") or "").strip()
        name = str(fields.get("name") or "").strip()
        education = fields.get("education_level") or fields.get("education")
        certifications = fields.get("certifications")
        if not name:
            tips.append(
                "No candidate name was detected. Put your full name on its own "
                "line at the very top of the CV, in plain text."
            )
        if not email and not phone:
            tips.append(
                "No email address or phone number was detected. Add both in "
                "plain text near the top (not inside an image or text box) so "
                "a recruiter can contact you."
            )
        elif not email:
            tips.append(
                "No email address was detected. Add a professional email in "
                "plain text near the top of the CV."
            )
        elif not phone:
            tips.append(
                "No phone number was detected. Add one in plain text near the "
                "top of the CV, including the country code if relevant."
            )
        if not location:
            tips.append(
                "No location was detected. Add your city and country (or "
                'region) near your contact details, e.g. "Toronto, Canada".'
            )
        if not education and not certifications:
            tips.append(
                "No education or certification details were detected. Add a "
                "short Education section with the degree/diploma, institution "
                "and year, plus any licences or certifications."
            )

    for skill in sorted(candidate.missing_required):
        tips.append(
            f'Required skill "{skill}" was not detected. If you have used it, '
            f"name it explicitly with that standard wording, ideally in a "
            f"Skills section near the top."
        )

    missing_preferred = sorted(
        requirements.preferred_skills - candidate.matched_preferred
    )
    if missing_preferred:
        listed = ", ".join(f'"{skill}"' for skill in missing_preferred)
        tips.append(
            f"Preferred skills that would boost your score: {listed}. "
            f"Add them only if you genuinely have used them."
        )

    if candidate.experience_years < target_years:
        if candidate.experience_years:
            tips.append(
                f"We detected {candidate.experience_years} year(s) of "
                f"experience but the role asks for {target_years}+. State it "
                f'explicitly, e.g. "6+ years of professional Python '
                f'development" (EN) ou « 6 ans d\'expérience en développement '
                f'Python » (FR).'
            )
        else:
            tips.append(
                f"No years of experience were detected and the role asks for "
                f'{target_years}+. Add a line like "5+ years of ..." (EN) or '
                f'« 5 ans d\'expérience ... » (FR) so it is unambiguous.'
            )

    missing_keywords = sorted(requirements.keywords - candidate.matched_keywords)
    if missing_keywords:
        listed = ", ".join(f'"{skill}"' for skill in missing_keywords)
        tips.append(
            f"Domain terms from the job ad worth working naturally into your "
            f"descriptions: {listed}."
        )

    matched_any = (
        candidate.matched_required
        or candidate.matched_preferred
        or candidate.matched_keywords
    )
    if not matched_any:
        tips.append(
            "No skills were detected at all. If this file is a scanned image "
            "or photo of a résumé, re-export it as a text-based PDF or DOCX "
            "so the text can actually be read."
        )

    if not tips:
        tips.append("Strong match — no changes needed for this job description.")
    return tips

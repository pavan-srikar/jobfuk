import re
import logging
from typing import Dict, Any, List, Tuple, Optional
from app.resume.models import ResumeProfile
from app.matcher.analyzer import analyze_job_description, CLOUD_ALIASES
from app.matcher.ollama_client import get_ollama_client

logger = logging.getLogger(__name__)

def normalize_skill(s: str) -> str:
    return s.strip().lower()

def calculate_skills_score(resume_skills: List[str], job_skills: List[str]) -> Tuple[float, List[str], List[str]]:
    """
    Evaluates Technical Skills (35 points max).
    Returns (score, matched_skills, missing_skills).
    """
    if not job_skills:
        return 28.0, resume_skills[:6], []
        
    resume_set = {normalize_skill(s) for s in resume_skills}
    matched = []
    missing = []
    
    for js in job_skills:
        js_norm = normalize_skill(js)
        is_matched = False
        if js_norm in resume_set:
            is_matched = True
        else:
            for rs in resume_set:
                if (js_norm in rs or rs in js_norm) and len(rs) > 2 and len(js_norm) > 2:
                    is_matched = True
                    break
        if is_matched:
            matched.append(js)
        else:
            missing.append(js)
            
    match_ratio = len(matched) / max(1, len(job_skills))
    score = round(match_ratio * 35.0, 1)
    return score, matched, missing

def calculate_cloud_score(candidate_clouds: List[str], job_clouds: List[str]) -> float:
    """Evaluates Cloud Platform match (10 points max)."""
    if not job_clouds:
        return 7.0 if candidate_clouds else 4.0
        
    cand_norm = {c.lower() for c in candidate_clouds}
    matched_clouds = [jc for jc in job_clouds if jc.lower() in cand_norm]
    
    if matched_clouds:
        ratio = len(matched_clouds) / len(job_clouds)
        return round(ratio * 10.0, 1)
    else:
        return 0.0

def calculate_experience_score(
    candidate_years: float,
    min_required: Optional[float],
    max_required: Optional[float],
    seniority: str
) -> Tuple[float, float, List[str]]:
    """
    Evaluates Experience (20 points max) with STRICT Hard Requirement gating.
    Returns (score, penalty, concerns).
    """
    concerns = []
    penalty = 0.0
    
    # Check Seniority Mismatch (e.g. Lead, Architect, Principal)
    senior_roles = ["LEAD", "ARCHITECT", "PRINCIPAL", "MANAGER"]
    if seniority in senior_roles and candidate_years < 3.0:
        penalty += 25.0
        concerns.append(f"❌ SENIORITY MISMATCH: Role is {seniority.title()} level (Candidate has {candidate_years} yr experience)")

    if min_required is None:
        # If unspecified, default baseline based on seniority
        if seniority in senior_roles:
            return 4.0, penalty, concerns
        elif seniority == "SENIOR":
            return 8.0, penalty, concerns
        else:
            return 18.0, penalty, concerns

    # If candidate has enough experience
    if candidate_years >= min_required:
        return 20.0, penalty, concerns

    deficit = min_required - candidate_years
    fmt_min = int(min_required) if min_required.is_integer() else min_required
    fmt_max = int(max_required) if (max_required and max_required.is_integer()) else max_required
    fmt_cand = int(candidate_years) if candidate_years.is_integer() else candidate_years
    fmt_def = int(deficit) if deficit.is_integer() else deficit
    exp_display = f"{fmt_min}" + (f"-{fmt_max}" if fmt_max else "+") + " years"

    if deficit >= 4.0:
        # Severe deficit (e.g., job requires 6+ or 6-10 years, candidate has 1 year)
        score = 0.0
        penalty += 35.0
        concerns.append(f"❌ CRITICAL BLOCKER: JD requires {exp_display} experience (Candidate has {fmt_cand} yr, deficit: -{fmt_def} yrs)")
    elif deficit >= 2.0:
        # Significant deficit (e.g. job requires 3-5 years, candidate has 1 year)
        score = 4.0
        penalty += 20.0
        concerns.append(f"⚠ HARD REQ MISMATCH: JD requires {exp_display} experience (Candidate has {fmt_cand} yr, deficit: -{fmt_def} yrs)")
    elif deficit >= 1.0:
        # Moderate deficit (e.g. job requires 2+ years, candidate has 1 year)
        score = 10.0
        penalty += 10.0
        concerns.append(f"⚠ Experience Deficit: JD asks for {exp_display} (Candidate has {fmt_cand} yr)")
    else:
        score = 15.0
        penalty += 4.0
        concerns.append(f"ℹ Minor experience gap: JD asks for {exp_display}")

    return score, penalty, concerns

def calculate_fit_score(
    profile: ResumeProfile,
    title: str,
    domain: str,
    min_required_years: Optional[float],
    seniority: str,
    matched_skills: List[str],
    work_mode: str
) -> float:
    """
    Calculates FIT SCORE (0-100): "How good is this opportunity for the candidate?"
    """
    cand_exp = profile.years_experience
    
    # 1. Seniority Fit (35 pts)
    # For a 1-2 year candidate: Entry/Associate/Standard Engineer is HIGH fit.
    # Lead / Architect / Principal is extremely POOR fit.
    if seniority in ["LEAD", "ARCHITECT", "PRINCIPAL", "MANAGER"]:
        if cand_exp < 3.0:
            seniority_pts = 0.0 # 1-yr candidate applying to Lead role = 0 fit
        else:
            seniority_pts = 25.0
    elif seniority == "SENIOR":
        seniority_pts = 8.0 if cand_exp < 3.0 else 30.0
    elif seniority in ["ENTRY", "ASSOCIATE"]:
        seniority_pts = 35.0 # Perfect fit for 1 year exp!
    else:
        # Standard Engineer
        if min_required_years and min_required_years >= 5.0 and cand_exp < 2.0:
            seniority_pts = 5.0
        elif min_required_years and min_required_years >= 3.0 and cand_exp < 2.0:
            seniority_pts = 15.0
        else:
            seniority_pts = 30.0

    # 2. Domain Alignment (35 pts)
    if domain == "cloud_devops":
        domain_pts = 35.0
    elif domain == "data_ai":
        domain_pts = 15.0
    else: # Software engineering / Java / Spring etc.
        domain_pts = 5.0

    # 3. Core Stack Alignment (20 pts)
    core_stack = {"azure", "aws", "kubernetes", "terraform", "docker", "ci/cd", "linux", "python"}
    matched_core = [s for s in matched_skills if s.lower() in core_stack]
    stack_pts = min(20.0, round(len(matched_core) * 3.5, 1))

    # 4. Work Mode Fit (10 pts)
    wm = (work_mode or "").lower()
    if "remote" in wm:
        wm_pts = 10.0
    elif "hybrid" in wm:
        wm_pts = 8.0
    else:
        wm_pts = 6.0

    total_fit = min(100.0, max(0.0, round(seniority_pts + domain_pts + stack_pts + wm_pts, 1)))
    return total_fit

def score_job(job: Dict[str, Any], profile: ResumeProfile) -> Dict[str, Any]:
    """
    Performs full hybrid ATS and FIT evaluation against candidate profile
    with strict Hard Requirement enforcement.
    """
    title = job.get("title", "")
    description = job.get("description", "")
    location = job.get("location", "")
    work_mode = job.get("work_mode", "On-site")
    experience_level = job.get("experience_level", "")
    
    analysis = analyze_job_description(title, description, experience_level)
    
    # 1. Technical Skills (35 max)
    skills_score, matched_skills, missing_skills = calculate_skills_score(profile.skills, analysis["skills"])
    
    # 2. Cloud Platform (10 max)
    cloud_score = calculate_cloud_score(profile.cloud_platforms, analysis["clouds"])
    
    # Title cloud gate: e.g. title says "AWS Engineer", candidate has 0 AWS
    title_cloud_concerns = []
    title_cloud_penalty = 0.0
    title_lower = title.lower()
    for cl in ["azure", "aws", "gcp"]:
        if cl in title_lower:
            if not any(cl in c.lower() for c in profile.cloud_platforms):
                title_cloud_penalty = 20.0
                title_cloud_concerns.append(f"❌ Primary Platform Missing: Title requires {cl.upper()} (Not in candidate cloud stack)")
                break

    # 3. Experience & Seniority Gate (20 max)
    exp_score, exp_penalty, exp_concerns = calculate_experience_score(
        profile.years_experience,
        analysis["required_experience"],
        analysis["max_experience"],
        analysis["seniority"]
    )
    
    # 4. Responsibilities & Role Alignment (15 max)
    if analysis["domain"] == "cloud_devops":
        resp_score = 14.0
    elif analysis["domain"] == "data_ai":
        resp_score = 8.0
    else:
        resp_score = 4.0
        
    # 5. Education (5 max)
    edu_score = 5.0 if profile.education else 3.0
    edu_concerns = []
    edu_penalty = 0.0
    if analysis["degree_required"] and not profile.education:
        edu_penalty = 5.0
        edu_concerns.append("⚠ Job specifies a degree requirement")
        
    # 6. Certifications (5 max)
    cert_score = 5.0 if profile.certifications else 2.0
    
    # 7. ATS Keywords (5 max)
    kw_count = len(matched_skills)
    kw_score = min(5.0, round(kw_count * 0.8, 1))
    
    # 8. Location (5 max)
    loc_score = 5.0
    cand_loc_lower = profile.location.lower()
    job_loc_lower = location.lower()
    if cand_loc_lower and job_loc_lower:
        if cand_loc_lower in job_loc_lower or "india" in job_loc_lower or "remote" in job_loc_lower:
            loc_score = 5.0
        else:
            loc_score = 2.0

    # Raw ATS sum (before hard requirement penalties)
    raw_ats = round(skills_score + exp_score + resp_score + cloud_score + edu_score + cert_score + kw_score + loc_score, 1)
    
    # Aggregate Hard Requirement Penalties & Concerns
    all_concerns = exp_concerns + title_cloud_concerns + edu_concerns
    total_penalties = exp_penalty + title_cloud_penalty + edu_penalty
    
    final_ats = max(0.0, min(100.0, round(raw_ats - total_penalties, 1)))
    
    # FIT SCORE (0-100)
    fit_score = calculate_fit_score(
        profile=profile,
        title=title,
        domain=analysis["domain"],
        min_required_years=analysis["required_experience"],
        seniority=analysis["seniority"],
        matched_skills=matched_skills,
        work_mode=work_mode
    )
    
    # APPLICATION PRIORITY
    # Strict rule: If there is a severe blocker or deficit >= 2 yrs, PRIORITY IS STRICTLY LOW
    has_critical_blocker = any("CRITICAL" in c or "SENIORITY MISMATCH" in c or "HARD REQ MISMATCH" in c for c in all_concerns)
    
    if has_critical_blocker or final_ats < 60 or fit_score < 50:
        priority = "LOW"
    elif final_ats >= 78 and fit_score >= 75 and not exp_concerns:
        priority = "HIGH"
    elif final_ats >= 65 or fit_score >= 60:
        priority = "MEDIUM"
    else:
        priority = "LOW"
        
    breakdown = {
        "skills": {"score": skills_score, "max": 35},
        "experience": {"score": exp_score, "max": 20},
        "responsibilities": {"score": resp_score, "max": 15},
        "cloud_platform": {"score": cloud_score, "max": 10},
        "education": {"score": edu_score, "max": 5},
        "certifications": {"score": cert_score, "max": 5},
        "ats_keywords": {"score": kw_score, "max": 5},
        "location": {"score": loc_score, "max": 5},
        "raw_ats": raw_ats,
        "penalties": {
            "total": total_penalties,
            "reasons": all_concerns
        },
        "final_ats": final_ats,
        "fit_score": fit_score,
        "priority": priority
    }
    
    # Optional Deep Ollama Evaluation
    ai_analysis = ""
    ollama = get_ollama_client()
    if ollama.is_available() and len(description) > 100:
        try:
            ollama_eval = ollama.evaluate_job_fit(
                profile.model_dump(),
                title,
                job.get("company", ""),
                description
            )
            if ollama_eval and isinstance(ollama_eval, dict):
                tips = ollama_eval.get("interview_tips", "")
                strengths = ", ".join(ollama_eval.get("key_strengths", []))
                gaps = ", ".join(ollama_eval.get("critical_gaps", []))
                ai_parts = []
                if strengths:
                    ai_parts.append(f"**Strengths:** {strengths}")
                if gaps:
                    ai_parts.append(f"**Critical Gaps:** {gaps}")
                if tips:
                    ai_parts.append(f"**Action Tip:** {tips}")
                ai_analysis = "\n\n".join(ai_parts)
        except Exception as e:
            logger.debug(f"Ollama scoring refinement skipped: {e}")

    return {
        "ats_score": final_ats,
        "fit_score": fit_score,
        "priority": priority,
        "required_experience": analysis["required_experience"],
        "seniority": analysis["seniority"],
        "matched_skills": matched_skills,
        "missing_skills": missing_skills,
        "hard_req_concerns": all_concerns,
        "score_breakdown": breakdown,
        "ai_analysis": ai_analysis
    }

import re
from typing import Dict, List, Any, Optional, Tuple
from app.resume.structure import TECH_KEYWORDS

# Cloud aliases and synonyms
CLOUD_ALIASES = {
    "azure": ["azure", "microsoft azure", "aks", "azure devops", "avd", "azure monitor"],
    "aws": ["aws", "amazon web services", "ec2", "s3", "eks", "lambda", "cloudformation"],
    "gcp": ["gcp", "google cloud", "google cloud platform", "gke"]
}

def extract_job_skills(text: str) -> List[str]:
    """Extracts technical skills present in the job description."""
    found = []
    text_lower = f" {text.lower()} "
    for skill in TECH_KEYWORDS:
        pattern = r"(?<!\w)" + re.escape(skill.lower()) + r"(?!\w)"
        if re.search(pattern, text_lower):
            found.append(skill)
    return list(dict.fromkeys(found))

def extract_job_clouds(text: str) -> List[str]:
    """Extracts cloud platforms mentioned in the job description."""
    found = []
    text_lower = text.lower()
    for cloud, aliases in CLOUD_ALIASES.items():
        if any(alias in text_lower for alias in aliases):
            found.append(cloud.upper() if cloud != "gcp" else "GCP")
    return list(dict.fromkeys(found))

def extract_required_experience(text: str) -> Tuple[Optional[float], Optional[float], str]:
    """
    Rigorously extracts experience requirements from text.
    Handles:
      - 'Experience: 6-10 Yrs Years'
      - 'Experience: 6-10 Yrs'
      - '4+ years of work experience'
      - '3+ years of work experience with Azure'
      - 'Experience: 3 to 5 years'
      - 'Experience: 5+ years'
      - 'Minimum 4 years'
      - '3-5 years of experience'
      - '3+ years experience'
      - 'Relevant experience: 2+ yrs'
    Returns (min_years, max_years, raw_match_string).
    """
    cleaned_text = re.sub(r"\s+", " ", text)
    
    # Priority Pattern 1: Explicit "Experience:" or "Exp:" label
    label_patterns = [
        r"(?:experience|exp|total exp|relevant exp|industry exp)\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*(?:-|to|\+)?\s*(\d+(?:\.\d+)?)?\s*(?:years?|yrs?)",
        r"(?:minimum|at least|min\.?)\s*(\d+(?:\.\d+)?)\s*(?:-|to|\+)?\s*(\d+(?:\.\d+)?)?\s*(?:years?|yrs?)"
    ]
    for lp in label_patterns:
        match = re.search(lp, cleaned_text, re.IGNORECASE)
        if match:
            try:
                min_val = float(match.group(1))
                max_val = float(match.group(2)) if match.group(2) else None
                if 0.5 <= min_val <= 30:
                    raw_str = f"{min_val}" + (f"-{max_val}" if max_val else "+") + " years"
                    return min_val, max_val, raw_str
            except (ValueError, IndexError):
                pass

    # Pattern 2: "X+ years of work experience" or "X+ years of experience"
    exp_work_match = re.search(r"(\d+(?:\.\d+)?)\+?\s*(?:years?|yrs?)(?:\s+of)?\s+(?:work\s+experience|relevant\s+experience|industry\s+experience|hands-on\s+experience|experience|exp)", cleaned_text, re.IGNORECASE)
    if exp_work_match:
        try:
            min_val = float(exp_work_match.group(1))
            if 0.5 <= min_val <= 30:
                return min_val, None, f"{min_val}+ years"
        except ValueError:
            pass

    # Pattern 3: Range before years (e.g. '6-10 years', '3 to 5 years')
    range_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:-|to)\s*(\d+(?:\.\d+)?)\s*(?:years?|yrs?)", cleaned_text, re.IGNORECASE)
    if range_match:
        try:
            min_val = float(range_match.group(1))
            max_val = float(range_match.group(2))
            if 0.5 <= min_val <= 30:
                return min_val, max_val, f"{min_val}-{max_val} years"
        except ValueError:
            pass

    # Pattern 4: Plus before years (e.g. '3+ years', '5+ yrs')
    plus_match = re.search(r"(\d+(?:\.\d+)?)\+?\s*(?:years?|yrs?)", cleaned_text, re.IGNORECASE)
    if plus_match:
        try:
            min_val = float(plus_match.group(1))
            if 1.0 <= min_val <= 30:
                return min_val, None, f"{min_val}+ years"
        except ValueError:
            pass

    return None, None, ""

def extract_seniority_level(title: str, text: str = "", experience_level: str = "") -> str:
    """
    Extracts the seniority level of the role.
    Returns: 'LEAD', 'ARCHITECT', 'PRINCIPAL', 'MANAGER', 'SENIOR', 'ASSOCIATE', 'ENTRY', or 'STANDARD'.
    """
    t_lower = title.lower()
    el_lower = (experience_level or "").lower()
    
    if any(k in t_lower for k in ["architect", "architecture"]):
        return "ARCHITECT"
    if any(k in t_lower for k in ["lead", "tech lead", "team lead", "head"]):
        return "LEAD"
    if any(k in t_lower for k in ["principal", "staff", "distinguished"]):
        return "PRINCIPAL"
    if any(k in t_lower for k in ["director", "vp", "manager", "management"]):
        return "MANAGER"
    if any(k in t_lower for k in ["senior", "sr.", "sr ", "sr-", "l3", "level 3", "iii"]):
        return "SENIOR"
    if any(k in t_lower for k in ["junior", "jr.", "jr ", "entry", "intern", "trainee", "graduate"]):
        return "ENTRY"
    if any(k in t_lower for k in ["associate", "l1", "l2"]):
        return "ASSOCIATE"
    
    # Metadata fallback
    if "director" in el_lower or "executive" in el_lower:
        return "MANAGER"
    if "mid-senior" in el_lower:
        return "SENIOR"
    if "entry" in el_lower:
        return "ENTRY"
    if "associate" in el_lower:
        return "ASSOCIATE"
        
    return "STANDARD"

def infer_experience_from_seniority(seniority: str) -> Optional[float]:
    """Default baseline experience required if JD text omits explicit year numbers."""
    if seniority == "ARCHITECT":
        return 7.0
    elif seniority == "PRINCIPAL":
        return 8.0
    elif seniority == "LEAD":
        return 6.0
    elif seniority == "MANAGER":
        return 7.0
    elif seniority == "SENIOR":
        return 4.0
    elif seniority == "ASSOCIATE":
        return 1.5
    elif seniority == "ENTRY":
        return 0.5
    return None

def detect_job_domain(title: str, text: str) -> str:
    """
    Identifies the primary role domain.
    Distinguishes true Cloud/DevOps roles from pure Software Development roles.
    """
    title_lower = title.lower()
    text_lower = text.lower()
    
    if any(k in title_lower for k in ["cloud", "devops", "sre", "site reliability", "platform engineer", "infrastructure", "infra"]):
        return "cloud_devops"
        
    if any(k in title_lower for k in ["java", "spring", "c#", ".net", "backend", "full stack", "frontend", "react", "angular", "node"]):
        return "software_engineering"
        
    if any(k in title_lower for k in ["data engineer", "data scientist", "machine learning", "mlops", "ai engineer"]):
        return "data_ai"

    cloud_count = sum(text_lower.count(k) for k in ["devops", "kubernetes", "terraform", "ci/cd", "infrastructure", "cloud engineer"])
    swe_count = sum(text_lower.count(k) for k in ["java", "spring boot", "c#", "react", "frontend", "backend developer"])
    
    return "cloud_devops" if cloud_count >= swe_count else "software_engineering"

def analyze_job_description(title: str, description: str, experience_level: str = "") -> Dict[str, Any]:
    """Analyzes JD and returns structured requirements with inferred experience."""
    full_text = f"{title}\n\n{description}"
    
    skills = extract_job_skills(full_text)
    clouds = extract_job_clouds(full_text)
    min_exp, max_exp, exp_text = extract_required_experience(full_text)
    seniority = extract_seniority_level(title, full_text, experience_level)
    
    # If no explicit year number was detected in text, infer from seniority!
    is_inferred = False
    if min_exp is None:
        inferred = infer_experience_from_seniority(seniority)
        if inferred:
            min_exp = inferred
            exp_text = f"{inferred}+ years (inferred from {seniority})"
            is_inferred = True

    domain = detect_job_domain(title, full_text)
    degree_required = any(d in full_text.lower() for d in ["bachelor", "b.tech", "b.e.", "degree in computer science", "master"])
    
    return {
        "title": title,
        "skills": skills,
        "clouds": clouds,
        "required_experience": min_exp,
        "max_experience": max_exp,
        "experience_text": exp_text,
        "is_experience_inferred": is_inferred,
        "seniority": seniority,
        "domain": domain,
        "degree_required": degree_required
    }

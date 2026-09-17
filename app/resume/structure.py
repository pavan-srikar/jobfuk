import re
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from app.config import RESUME_PATH, DEFAULT_RESUME_PATH
from app.resume.models import ResumeProfile
from app.database import save_profile, get_profile

logger = logging.getLogger(__name__)

# Common tech skills dictionary for rule-based extraction
TECH_KEYWORDS = [
    # Cloud
    "Azure", "AWS", "Google Cloud", "GCP", "OpenStack",
    # Containers & Orchestration
    "Kubernetes", "Docker", "Containerd", "Podman", "Helm", "OpenShift", "K8s",
    # IaC & Configuration
    "Terraform", "Ansible", "CloudFormation", "Puppet", "Chef", "Pulumi", "Packer",
    # CI/CD
    "CI/CD", "Jenkins", "GitHub Actions", "GitLab CI", "ArgoCD", "CircleCI", "Bitbucket Pipelines",
    # Observability & Monitoring
    "Prometheus", "Grafana", "ELK", "Elasticsearch", "Datadog", "Splunk", "CloudWatch", "OpenTelemetry", "Nagios",
    # OS & Scripting
    "Linux", "Ubuntu", "CentOS", "RHEL", "Bash", "Shell", "Python", "Go", "Golang", "PowerShell", "Git",
    # Networking & Security
    "TCP/IP", "DNS", "VPN", "IAM", "VPC", "SSL/TLS", "Vault", "SonarQube", "Trivy",
    # Development / Frameworks / DBs
    "REST API", "Microservices", "PostgreSQL", "MySQL", "MongoDB", "Redis", "Kafka", "RabbitMQ",
    "Java", "Spring Boot", "Node.js", "C++", "Rust"
]

CLOUD_PLATFORMS = ["Azure", "AWS", "GCP", "Google Cloud", "Oracle Cloud", "IBM Cloud", "Alibaba Cloud"]

DEFAULT_SAMPLE_PROFILE = {
    "candidate_name": "Cloud / DevOps Engineer",
    "target_roles": ["Cloud Engineer", "DevOps Engineer", "Site Reliability Engineer", "Platform Engineer"],
    "years_experience": 1.0,
    "location": "India",
    "skills": [
        "Azure",
        "AWS",
        "Kubernetes",
        "Terraform",
        "Docker",
        "Linux",
        "Python",
        "CI/CD",
        "Git",
        "Bash",
        "Prometheus",
        "Grafana"
    ],
    "cloud_platforms": ["Azure", "AWS"],
    "certifications": ["AZ-104 Microsoft Azure Administrator"],
    "education": ["Bachelor of Technology in Computer Science"],
    "summary": "Cloud and DevOps Engineer with hands-on experience in Azure, AWS, Kubernetes, Terraform, Docker, and CI/CD pipelines."
}

def extract_skills_rule_based(text: str) -> List[str]:
    found = []
    text_lower = f" {text.lower()} "
    for skill in TECH_KEYWORDS:
        # Match word boundaries
        pattern = r"(?<!\w)" + re.escape(skill.lower()) + r"(?!\w)"
        if re.search(pattern, text_lower):
            found.append(skill)
    return list(dict.fromkeys(found))

def extract_cloud_platforms(text: str) -> List[str]:
    found = []
    text_lower = text.lower()
    for cp in CLOUD_PLATFORMS:
        if cp.lower() in text_lower:
            found.append(cp)
    return list(dict.fromkeys(found))

def extract_experience_years(text: str) -> float:
    patterns = [
        r"(\d+(?:\.\d+)?)\+?\s*(?:years?|yrs?)(?:\s+of)?\s+(?:experience|exp)",
        r"(?:experience|exp):\s*(\d+(?:\.\d+)?)\s*(?:years?|yrs?)",
        r"(\d+(?:\.\d+)?)\s*(?:years?|yrs?)"
    ]
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            try:
                val = float(m.group(1))
                if 0.5 <= val <= 35:
                    return val
            except ValueError:
                continue
    return 1.0

def extract_certifications_rule_based(text: str) -> List[str]:
    certs = []
    known_certs = [
        "AZ-104", "AZ-900", "AZ-305", "AZ-400", "AZ-500",
        "AWS Certified Solutions Architect", "AWS Certified Cloud Practitioner",
        "AWS Certified DevOps Engineer", "AWS Certified SysOps",
        "CKA", "CKAD", "CKS", "Certified Kubernetes Administrator",
        "HashiCorp Certified: Terraform Associate", "Terraform Associate",
        "RHCSA", "RHCE", "CompTIA Security+", "CompTIA Network+"
    ]
    for c in known_certs:
        pattern = r"(?<!\w)" + re.escape(c.lower()) + r"(?!\w)"
        if re.search(pattern, text.lower()):
            certs.append(c)
    return certs

def extract_education_rule_based(text: str) -> List[str]:
    edu = []
    degrees = [
        "B.Tech", "B.E.", "Bachelor of Technology", "Bachelor of Engineering",
        "Bachelor of Science", "B.Sc", "BCA", "MCA", "M.Tech", "M.S.", "Master of Science"
    ]
    for d in degrees:
        if d.lower() in text.lower():
            edu.append(d)
    return list(dict.fromkeys(edu))

def structure_resume_text(text: str, candidate_name: str = "Candidate") -> ResumeProfile:
    """
    Parses resume text into a structured ResumeProfile using rule-based extraction
    with optional Ollama enhancement.
    """
    from app.matcher.ollama_client import get_ollama_client
    
    ollama = get_ollama_client()
    if ollama.is_available():
        try:
            profile_data = ollama.extract_resume_profile(text)
            if profile_data and isinstance(profile_data, dict):
                profile_data["raw_text"] = text
                if not profile_data.get("skills"):
                    profile_data["skills"] = extract_skills_rule_based(text)
                if not profile_data.get("cloud_platforms"):
                    profile_data["cloud_platforms"] = extract_cloud_platforms(text)
                return ResumeProfile(**profile_data)
        except Exception as e:
            logger.warning(f"Ollama resume parsing failed, using rule-based fallback: {e}")
            
    # Rule-based fallback
    skills = extract_skills_rule_based(text)
    cloud_platforms = extract_cloud_platforms(text)
    exp = extract_experience_years(text)
    certs = extract_certifications_rule_based(text)
    education = extract_education_rule_based(text)
    
    # Simple summary extraction
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    summary = lines[0] if lines else "Cloud / DevOps Engineer"
    
    return ResumeProfile(
        candidate_name=candidate_name,
        target_roles=["Cloud Engineer", "DevOps Engineer", "SRE"],
        years_experience=exp,
        location="India",
        skills=skills,
        cloud_platforms=cloud_platforms,
        certifications=certs,
        education=education,
        summary=summary,
        raw_text=text
    )

def init_default_profile():
    """Initializes default profile if none exists in DB."""
    existing = get_profile()
    if not existing:
        save_profile(DEFAULT_SAMPLE_PROFILE)
        # Also write default_resume.json for user inspection
        with open(DEFAULT_RESUME_PATH, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_SAMPLE_PROFILE, f, indent=2)

def get_active_profile() -> ResumeProfile:
    existing = get_profile()
    if existing:
        return ResumeProfile(**existing)
    init_default_profile()
    return ResumeProfile(**DEFAULT_SAMPLE_PROFILE)

def update_active_profile(profile_dict: Dict[str, Any]) -> ResumeProfile:
    profile = ResumeProfile(**profile_dict)
    save_profile(profile.model_dump())
    # Save to disk as well
    with open(RESUME_PATH, "w", encoding="utf-8") as f:
        json.dump(profile.model_dump(), f, indent=2)
    return profile

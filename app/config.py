import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

DB_PATH = DATA_DIR / "jobs.db"
RESUME_PATH = DATA_DIR / "resume.json"
DEFAULT_RESUME_PATH = DATA_DIR / "default_resume.json"

# Ollama Settings
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "30"))

# LinkedIn Scraping Settings
LINKEDIN_GUEST_SEARCH_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
LINKEDIN_GUEST_JOB_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting"

USER_AGENTS = [
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:123.0) Gecko/20100101 Firefox/123.0",
]

# Scoring Weights
SCORING_WEIGHTS = {
    "technical_skills": 35,
    "experience": 20,
    "responsibilities": 15,
    "cloud_platform": 10,
    "education": 5,
    "certifications": 5,
    "ats_keywords": 5,
    "location": 5,
}

# Hard Requirement Penalties
HARD_REQ_PENALTIES = {
    "missing_experience": 15,    # Candidate lacks required years of experience
    "missing_core_tech": 15,     # Required core tech missing
    "missing_degree": 5,         # Required degree missing
    "missing_certification": 5,  # Mandatory certification missing
}

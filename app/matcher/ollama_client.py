import json
import logging
import requests
from typing import Dict, Any, Optional
from app.config import OLLAMA_BASE_URL, OLLAMA_MODEL, OLLAMA_TIMEOUT

logger = logging.getLogger(__name__)

class OllamaClient:
    def __init__(self, base_url: str = OLLAMA_BASE_URL, model: str = OLLAMA_MODEL):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = OLLAMA_TIMEOUT

    def is_available(self) -> bool:
        """Checks if Ollama server is responsive."""
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=3)
            return resp.status_code == 200
        except Exception:
            return False

    def get_model_status(self) -> Dict[str, Any]:
        """Returns details on Ollama connection and available models."""
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=3)
            if resp.status_code == 200:
                data = resp.json()
                models = [m.get("name") for m in data.get("models", [])]
                model_found = any(self.model in m for m in models)
                return {
                    "connected": True,
                    "target_model": self.model,
                    "target_model_installed": model_found,
                    "available_models": models
                }
        except Exception as e:
            return {
                "connected": False,
                "target_model": self.model,
                "target_model_installed": False,
                "available_models": [],
                "error": str(e)
            }
        return {"connected": False, "target_model": self.model, "target_model_installed": False}

    def generate_json(self, prompt: str, system: str = "") -> Optional[Dict[str, Any]]:
        """Invokes Ollama with JSON output enforcement."""
        if not self.is_available():
            return None
            
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "system": system or "You are an expert ATS & Technical Recruiter. Respond ONLY in valid, parseable JSON with no markdown backticks or commentary.",
            "format": "json",
            "stream": False,
            "options": {
                "temperature": 0.1,
                "num_predict": 1024
            }
        }
        
        try:
            resp = requests.post(url, json=payload, timeout=self.timeout)
            if resp.status_code == 200:
                result_text = resp.json().get("response", "").strip()
                # Clean up if markdown fences leaked
                if result_text.startswith("```"):
                    lines = result_text.splitlines()
                    if lines[0].startswith("```"):
                        lines = lines[1:]
                    if lines and lines[-1].startswith("```"):
                        lines = lines[:-1]
                    result_text = "\n".join(lines).strip()
                return json.loads(result_text)
            else:
                logger.warning(f"Ollama returned HTTP {resp.status_code}: {resp.text}")
        except Exception as e:
            logger.warning(f"Ollama JSON generation failed: {e}")
            
        return None

    def extract_resume_profile(self, resume_text: str) -> Optional[Dict[str, Any]]:
        """Uses Ollama to extract structured resume fields."""
        prompt = f"""
        Extract the candidate's professional profile from the resume below.
        Return a JSON object with this exact schema:
        {{
            "candidate_name": "Full Name",
            "target_roles": ["Role 1", "Role 2"],
            "years_experience": 2.5,
            "location": "City, Country",
            "skills": ["Skill 1", "Skill 2"],
            "cloud_platforms": ["Azure", "AWS"],
            "certifications": ["Cert 1", "Cert 2"],
            "education": ["Degree in Field"],
            "summary": "2-sentence summary of candidate background"
        }}

        Resume text:
        \"\"\"{resume_text[:4000]}\"\"\"
        """
        return self.generate_json(prompt)

    def evaluate_job_fit(
        self,
        resume_profile: Dict[str, Any],
        job_title: str,
        job_company: str,
        job_description: str
    ) -> Optional[Dict[str, Any]]:
        """
        Deep qualitative analysis from llama3.1:8b:
        Identifies hard requirement blockers, key gaps, strengths, and candidate advice.
        """
        prompt = f"""
        Evaluate candidate fit for this job.
        
        CANDIDATE:
        - Experience: {resume_profile.get('years_experience')} years
        - Core Skills: {', '.join(resume_profile.get('skills', [])[:25])}
        - Cloud: {', '.join(resume_profile.get('cloud_platforms', []))}
        - Certifications: {', '.join(resume_profile.get('certifications', []))}
        - Location: {resume_profile.get('location')}

        JOB:
        - Title: {job_title}
        - Company: {job_company}
        - Description excerpt:
        \"\"\"{job_description[:3000]}\"\"\"

        Return a JSON object with:
        {{
            "ats_score_adjustment": 0,
            "fit_score_adjustment": 0,
            "hard_req_verdict": "PASS or FAIL",
            "hard_req_reasons": ["List of strict requirements failed, if any"],
            "key_strengths": ["Top 2-3 matched strengths"],
            "critical_gaps": ["Top 2-3 missing critical requirements"],
            "interview_tips": "One actionable advice sentence for the applicant"
        }}
        """
        return self.generate_json(prompt)

# Singleton instance
_ollama_client = None

def get_ollama_client() -> OllamaClient:
    global _ollama_client
    if _ollama_client is None:
        _ollama_client = OllamaClient()
    return _ollama_client

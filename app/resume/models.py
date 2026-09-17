from pydantic import BaseModel, Field
from typing import List, Optional

class ResumeProfile(BaseModel):
    candidate_name: str = Field(default="Candidate", description="Full name")
    target_roles: List[str] = Field(default_factory=lambda: ["Cloud Engineer", "DevOps Engineer", "SRE"])
    years_experience: float = Field(default=1.0, description="Total years of technical experience")
    location: str = Field(default="India", description="Current or target location")
    skills: List[str] = Field(default_factory=list, description="All technical skills and tools")
    cloud_platforms: List[str] = Field(default_factory=list, description="Cloud platforms: Azure, AWS, GCP, etc.")
    certifications: List[str] = Field(default_factory=list, description="Certifications e.g. AZ-104, CKA")
    education: List[str] = Field(default_factory=list, description="Degrees and fields of study")
    summary: str = Field(default="", description="Professional summary / bio")
    raw_text: Optional[str] = Field(default="", description="Original resume text")

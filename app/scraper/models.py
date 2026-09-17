from pydantic import BaseModel, Field
from typing import Optional, List

class ScrapeRequest(BaseModel):
    keywords: Optional[str] = Field(default="Cloud Engineer", description="Job search keyword")
    roles: Optional[List[str]] = Field(default=None, description="Multiple role presets to scrape in batch")
    location: str = Field(default="India", description="Job location")
    posted_within: str = Field(default="r86400", description="LinkedIn f_TPR: r86400 (24h), r604800 (7d), '' (all)")
    work_type: str = Field(default="", description="LinkedIn f_WT: 1 (onsite), 2 (remote), 3 (hybrid), '' (any)")
    max_pages: int = Field(default=5, description="Number of pages to scrape per role (each page has ~25 jobs)")
    engine: str = Field(default="guest_api", description="'guest_api' or 'chromium'")

class JobCard(BaseModel):
    linkedin_id: str
    title: str
    company: str
    location: str
    url: str
    posted_at: Optional[str] = ""
    is_reposted: bool = False

class JobDetail(BaseModel):
    linkedin_id: str
    title: str
    company: str
    location: str
    url: str
    posted_at: Optional[str] = ""
    employment_type: Optional[str] = ""
    experience_level: Optional[str] = ""
    work_mode: Optional[str] = ""
    salary: Optional[str] = ""
    description: str = ""
    is_reposted: bool = False

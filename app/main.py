import asyncio
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Query, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from app.config import BASE_DIR
from app.database import (
    init_db, get_jobs, get_job_by_id, set_job_status, get_stats,
    get_all_jobs_for_scoring, update_job_scores, deduplicate_database
)
from app.scraper.models import ScrapeRequest
from app.scraper.linkedin import LinkedInScraper
from app.resume.models import ResumeProfile
from app.resume.parser import extract_text_from_file_bytes
from app.resume.structure import (
    get_active_profile, update_active_profile, structure_resume_text
)
from app.matcher.scoring import score_job
from app.matcher.ollama_client import get_ollama_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("jobfuk")

app = FastAPI(title="JobFuk - LinkedIn ATS Radar", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory scraper task status
scraper_state = {
    "is_running": False,
    "status": "Idle",
    "progress": 0,
    "total": 0,
    "last_result": None
}

# Terminal color constants
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"

# Silence high-frequency UI status polling from flooding terminal
class PollingLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        return not any(p in msg for p in ["/api/scrape/status", "/api/ollama/status"])

logging.getLogger("uvicorn.access").addFilter(PollingLogFilter())

def rescore_all_jobs_sync():
    """Recalculates ATS and FIT scores for all jobs in database."""
    profile = get_active_profile()
    jobs = get_all_jobs_for_scoring()
    print(f"\n{YELLOW}⚡ [MATCH ENGINE] Rescoring {len(jobs)} jobs against active candidate profile...{RESET}", flush=True)
    high_count = 0
    for j in jobs:
        scored = score_job(j, profile)
        update_job_scores(
            job_id=j["id"],
            ats_score=scored["ats_score"],
            fit_score=scored["fit_score"],
            priority=scored["priority"],
            matched_skills=scored["matched_skills"],
            missing_skills=scored["missing_skills"],
            hard_req_concerns=scored["hard_req_concerns"],
            score_breakdown=scored["score_breakdown"],
            ai_analysis=scored["ai_analysis"],
            required_experience=scored.get("required_experience"),
            seniority=scored.get("seniority", "")
        )
        if scored["priority"] == "HIGH":
            high_count += 1
            print(f"  {GREEN}🔥 HIGH MATCH:{RESET} {j['title']} @ {j['company']} (ATS: {scored['ats_score']:.1f}% | FIT: {scored['fit_score']:.1f}%)", flush=True)
    print(f"{GREEN}✔ [MATCH ENGINE] Rescoring complete ({high_count} High Priority matches on radar).{RESET}\n", flush=True)

@app.on_event("startup")
def on_startup():
    init_db()
    dedup_res = deduplicate_database()
    if dedup_res.get("duplicates_removed", 0) > 0:
        print(f"{GREEN}✔ [DB DEDUP] Removed {dedup_res['duplicates_removed']} duplicate job postings ({dedup_res['cleaned_count']} unique canonical jobs remaining).{RESET}", flush=True)
    rescore_all_jobs_sync()

def run_scraper_task(req: ScrapeRequest):
    global scraper_state
    scraper_state["is_running"] = True
    scraper_state["progress"] = 0
    scraper_state["total"] = 0

    roles_to_scrape = req.roles if (req.roles and len(req.roles) > 0) else [req.keywords or "Cloud Engineer"]
    total_found_all = 0
    total_new_all = 0
    all_saved = []

    def progress_callback(msg: str, done: int, total: int):
        scraper_state["status"] = msg
        scraper_state["progress"] = done
        scraper_state["total"] = total

    try:
        for idx, role in enumerate(roles_to_scrape, 1):
            scraper_state["status"] = f"[{idx}/{len(roles_to_scrape)}] Searching '{role}' in '{req.location}' (pages 1..{req.max_pages})..."
            print(f"\n{BOLD}{CYAN}═══════════════════════════════════════════════════════════════════{RESET}", flush=True)
            print(f"{BOLD}🚀 [SCRAPE TASK] Role {idx}/{len(roles_to_scrape)}: '{role}' in '{req.location}' (Engine: {req.engine.upper()}, Max Pages: {req.max_pages}){RESET}", flush=True)
            print(f"{BOLD}{CYAN}═══════════════════════════════════════════════════════════════════{RESET}\n", flush=True)

            if req.engine == "chromium":
                from app.scraper.browser_scraper import ChromiumLinkedInScraper
                scraper = ChromiumLinkedInScraper(headless=True)
                result = scraper.scrape_and_save(
                    keywords=role,
                    location=req.location,
                    posted_within=req.posted_within,
                    work_type=req.work_type,
                    max_pages=req.max_pages,
                    progress_callback=progress_callback
                )
            else:
                scraper = LinkedInScraper()
                result = scraper.scrape_and_save(
                    keywords=role,
                    location=req.location,
                    posted_within=req.posted_within,
                    work_type=req.work_type,
                    max_pages=req.max_pages,
                    progress_callback=progress_callback
                )
            total_found_all += result.get("total_found", 0)
            total_new_all += result.get("new_added", 0)
            all_saved.extend(result.get("jobs", []))
            print(f"\n{GREEN}✔ Completed '{role}': {result.get('total_found', 0)} found, +{result.get('new_added', 0)} new jobs saved.{RESET}", flush=True)

        # Now score all newly added/updated jobs
        scraper_state["status"] = "Evaluating match quality & rescoring against your resume..."
        rescore_all_jobs_sync()

        scraper_state["status"] = f"Done! Discovered {total_found_all} jobs ({total_new_all} new additions)."
        scraper_state["last_result"] = {
            "total_found": total_found_all,
            "new_added": total_new_all,
            "jobs": all_saved
        }
        print(f"\n{GREEN}{BOLD}✨ [SCRAPE RUN FINISHED] Discovered: {total_found_all} | New Saved: {total_new_all}{RESET}\n", flush=True)
    except Exception as e:
        logger.error(f"Scraper error: {e}", exc_info=True)
        print(f"\n{RED}✘ [SCRAPER ERROR] {e}{RESET}\n", flush=True)
        scraper_state["status"] = f"Error: {str(e)}"
    finally:
        scraper_state["is_running"] = False

# API Routes
@app.get("/api/stats")
def api_stats():
    return get_stats()

@app.get("/api/jobs")
def api_get_jobs(
    min_ats: Optional[float] = Query(None, description="Minimum ATS score"),
    min_fit: Optional[float] = Query(None, description="Minimum FIT score"),
    max_exp: Optional[float] = Query(3.0, description="Max required experience cap (e.g. 3.0 to hide senior/4+ yr jobs)"),
    priority: Optional[str] = Query(None, description="HIGH, MEDIUM, LOW, ALL"),
    work_mode: Optional[str] = Query(None, description="Remote, Hybrid, On-site, all"),
    experience_level: Optional[str] = Query(None, description="Experience level"),
    status: Optional[str] = Query(None, description="new, saved, applied, all"),
    keyword: Optional[str] = Query(None, description="Search keyword"),
    location: Optional[str] = Query(None, description="Location search"),
    sort_by: str = Query("priority_desc", description="priority_desc, ats_desc, fit_desc, date_desc"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0)
):
    return get_jobs(
        min_ats=min_ats,
        min_fit=min_fit,
        max_exp=max_exp,
        priority=priority,
        work_mode=work_mode,
        experience_level=experience_level,
        status=status,
        keyword=keyword,
        location=location,
        sort_by=sort_by,
        limit=limit,
        offset=offset
    )

@app.get("/api/jobs/{job_id}")
def api_get_job(job_id: int):
    job = get_job_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

@app.patch("/api/jobs/{job_id}/status")
def api_set_job_status(job_id: int, status: str = Query(..., description="new, saved, applied, ignored")):
    ok = set_job_status(job_id, status)
    if not ok:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"success": True, "job_id": job_id, "status": status}

@app.post("/api/scrape")
def api_scrape(req: ScrapeRequest, background_tasks: BackgroundTasks):
    global scraper_state
    if scraper_state["is_running"]:
        return JSONResponse(
            status_code=409,
            content={"message": "Scraper is already currently running", "state": scraper_state}
        )
    background_tasks.add_task(run_scraper_task, req)
    return {"message": "Scraping task started in background", "request": req.model_dump()}

@app.get("/api/scrape/status")
def api_scrape_status():
    return scraper_state

@app.get("/api/profile")
def api_get_profile():
    return get_active_profile().model_dump()

@app.put("/api/profile")
def api_update_profile(profile_data: Dict[str, Any]):
    updated = update_active_profile(profile_data)
    # Trigger rescore in background
    rescore_all_jobs_sync()
    return {"message": "Profile updated and jobs rescored", "profile": updated.model_dump()}

@app.post("/api/profile/upload")
async def api_upload_resume(file: UploadFile = File(...)):
    content = await file.read()
    raw_text = extract_text_from_file_bytes(file.filename, content)
    if not raw_text.strip():
        raise HTTPException(status_code=400, detail="Could not extract readable text from file")
        
    profile = structure_resume_text(raw_text, candidate_name=Path(file.filename).stem)
    updated = update_active_profile(profile.model_dump())
    rescore_all_jobs_sync()
    
    return {
        "message": f"Successfully parsed and saved {file.filename}",
        "profile": updated.model_dump()
    }

@app.post("/api/rescore")
def api_rescore(background_tasks: BackgroundTasks):
    background_tasks.add_task(rescore_all_jobs_sync)
    return {"message": "Rescoring all jobs in background"}

@app.post("/api/database/deduplicate")
def api_deduplicate_database():
    res = deduplicate_database()
    return res

@app.get("/api/ollama/status")
def api_ollama_status():
    ollama = get_ollama_client()
    return ollama.get_model_status()

# Mount static web UI assets
static_dir = BASE_DIR / "app" / "static"
static_dir.mkdir(exist_ok=True)

app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

@app.api_route("/", methods=["GET", "HEAD"])
def read_root():
    index_file = static_dir / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return {"message": "JobFuk API is running. Place index.html in app/static/"}

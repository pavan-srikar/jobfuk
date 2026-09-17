import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.scraper.linkedin import LinkedInScraper
from app.resume.structure import get_active_profile
from app.matcher.scoring import score_job
from app.database import update_job_scores, get_jobs

def main():
    print("Testing live LinkedIn guest search for 'Cloud Engineer' in 'India'...")
    scraper = LinkedInScraper()
    result = scraper.scrape_and_save(
        keywords="Cloud Engineer",
        location="India",
        posted_within="r86400",
        max_pages=1
    )
    print("Scrape completed:", result["total_found"], "found,", result["new_added"], "added.")

    profile = get_active_profile()
    for j in result["jobs"]:
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
            ai_analysis=scored["ai_analysis"]
        )

    top_jobs = get_jobs(limit=5, sort_by="priority_desc")
    print("\nTop 5 Scraped & Scored Jobs from LinkedIn:")
    for idx, j in enumerate(top_jobs["jobs"], 1):
        prio = j.get("priority", "MEDIUM")
        ats = j.get("ats_score", 0)
        fit = j.get("fit_score", 0)
        title = j.get("title", "")
        company = j.get("company", "")
        loc = j.get("location", "")
        print(f"{idx}. [{prio}] ATS: {ats}% | FIT: {fit}% - {title} @ {company} ({loc})")
        print(f"   Matched: {j.get('matched_skills', [])}")
        if j.get("hard_req_concerns"):
            print(f"   Concerns: {j.get('hard_req_concerns')}")

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Mass Scraper CLI with Clean Terminal Dashboard for LinkedIn Ingestion.
Supports multi-role preset selection, multi-page scraping (1, 2, 3, 4, 5...),
reposted job detection, and auto-scoring against the candidate resume.
"""

import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import time
import argparse
import logging
from typing import List, Dict, Any

from app.resume.structure import get_active_profile
from app.database import init_db, get_stats, get_all_jobs_for_scoring, update_job_scores
from app.matcher.scoring import score_job
from app.scraper.linkedin import LinkedInScraper
from app.scraper.browser_scraper import ChromiumLinkedInScraper

# Disable standard noisy logging to keep terminal clean
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("requests").setLevel(logging.WARNING)

ROLE_PRESETS = [
    "Azure Cloud Engineer",
    "DevOps Engineer",
    "Cloud Engineer",
    "Junior DevOps Engineer",
    "Site Reliability Engineer",
    "Platform Engineer",
    "AWS DevOps Engineer",
    "Kubernetes Specialist"
]

# ANSI Colors for clean terminal UI
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
MAGENTA = "\033[95m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"

def print_banner():
    banner = f"""{CYAN}{BOLD}
╔═══════════════════════════════════════════════════════════════════════╗
║                   MASS LINKEDIN INGESTION ENGINE                      ║
║         Multi-Page Pagination • Multi-Role Presets • Auto-Scoring     ║
╚═══════════════════════════════════════════════════════════════════════╝{RESET}
"""
    print(banner)

def render_progress_bar(current: int, total: int, width: int = 24) -> str:
    if total <= 0:
        return f"[{' ' * width}] 0%"
    fraction = min(1.0, current / total)
    filled = int(fraction * width)
    bar = f"{GREEN}{'█' * filled}{RESET}{DIM}{'░' * (width - filled)}{RESET}"
    percent = int(fraction * 100)
    return f"[{bar}] {percent:>3}%"

def run_mass_scrape(
    roles: List[str],
    location: str = "India",
    pages_per_role: int = 5,
    posted_within: str = "r86400",
    work_type: str = "",
    engine: str = "guest_api"
):
    init_db()
    profile = get_active_profile()
    candidate_name = getattr(profile, "candidate_name", "Candidate")
    exp_years = getattr(profile, "years_experience", 1.0)

    print(f"{BOLD}Active Candidate:{RESET} {GREEN}{candidate_name}{RESET} ({exp_years} yrs exp)")
    print(f"{BOLD}Location Target:{RESET}  {CYAN}{location}{RESET}")
    print(f"{BOLD}Pages Per Role:{RESET}   {YELLOW}{pages_per_role} pages{RESET} (~{pages_per_role * 25} jobs per role)")
    print(f"{BOLD}Scrape Engine:{RESET}    {MAGENTA}{engine.upper()}{RESET}")
    print(f"{BOLD}Selected Roles ({len(roles)}):{RESET}")
    for idx, r in enumerate(roles, 1):
        print(f"  {CYAN}▸ [{idx}]{RESET} {r}")
    print("─" * 71)

    total_scraped_all = 0
    total_new_all = 0
    total_reposted_all = 0

    scraper = ChromiumLinkedInScraper(headless=True) if engine == "chromium" else LinkedInScraper()

    start_time = time.time()

    for role_idx, role in enumerate(roles, 1):
        print(f"\n{BOLD}{CYAN}═══ [Role {role_idx}/{len(roles)}] Processing: {role} ═══{RESET}")
        
        def cli_progress(msg: str, done: int, total: int):
            bar = render_progress_bar(done, total if total > 0 else 1, width=20)
            clean_msg = msg[:42]
            line = f"\r{DIM}↳{RESET} {bar} {clean_msg:<42}"
            sys.stdout.write(line)
            sys.stdout.flush()

        try:
            if engine == "chromium":
                res = scraper.scrape_and_save(
                    keywords=role,
                    location=location,
                    posted_within=posted_within,
                    work_type=work_type,
                    max_pages=pages_per_role,
                    progress_callback=cli_progress
                )
            else:
                res = scraper.scrape_and_save(
                    keywords=role,
                    location=location,
                    posted_within=posted_within,
                    work_type=work_type,
                    max_pages=pages_per_role,
                    progress_callback=cli_progress
                )
            
            # Clear progress line
            sys.stdout.write("\r" + " " * 80 + "\r")
            
            found = res.get("total_found", 0)
            new_added = res.get("new_added", 0)
            reposted = sum(1 for j in res.get("jobs", []) if j.get("is_reposted"))

            total_scraped_all += found
            total_new_all += new_added
            total_reposted_all += reposted

            print(f"  {GREEN}✔ Completed '{role}'{RESET}: "
                  f"{found} found | {GREEN}+{new_added} new{RESET} | "
                  f"{RED}🚨 {reposted} reposted{RESET}")

        except Exception as e:
            print(f"\n  {RED}✘ Error scraping '{role}': {e}{RESET}")

    elapsed = round(time.time() - start_time, 1)

    print("\n" + "═" * 71)
    print(f"{BOLD}Rescoring and evaluating match quality against candidate resume...{RESET}")

    all_jobs = get_all_jobs_for_scoring()
    high_matches = []
    med_matches = []
    low_matches = []

    for j in all_jobs:
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
        prio = scored["priority"]
        if prio == "HIGH":
            high_matches.append((j, scored))
        elif prio == "MEDIUM":
            med_matches.append((j, scored))
        else:
            low_matches.append((j, scored))

    stats = get_stats()

    print("\n" + f"{CYAN}{BOLD}════════════════════════ INGESTION SUMMARY ════════════════════════{RESET}")
    print(f"  {BOLD}Total Discovered in Session:{RESET} {total_scraped_all} jobs")
    print(f"  {BOLD}New Jobs Upserted to DB:{RESET}    {GREEN}{total_new_all}{RESET}")
    print(f"  {BOLD}Total Reposted Detected:{RESET}    {RED}{total_reposted_all}{RESET}")
    print(f"  {BOLD}Total Jobs in Database:{RESET}     {stats['total']}")
    print(f"  {BOLD}High Priority Matches:{RESET}      {GREEN}{BOLD}{len(high_matches)}{RESET}")
    print(f"  {BOLD}Medium Priority Matches:{RESET}    {YELLOW}{len(med_matches)}{RESET}")
    print(f"  {BOLD}Low Priority / Filtered:{RESET}    {DIM}{len(low_matches)}{RESET}")
    print(f"  {BOLD}Elapsed Time:{RESET}               {elapsed}s")
    print("═" * 71)

    if high_matches:
        print(f"\n{GREEN}{BOLD}🔥 TOP HIGH PRIORITY OPPORTUNITIES ON RADAR:{RESET}")
        for idx, (job, scored) in enumerate(high_matches[:5], 1):
            is_rep = job.get("is_reposted") or ("repost" in str(job.get("posted_at", "")).lower())
            repost_badge = f" {RED}[REPOSTED]{RESET}" if is_rep else ""
            job_url = job.get("url") or f"https://www.linkedin.com/jobs/view/{job.get('linkedin_id')}/"
            print(f"  {idx}. {BOLD}{job['title']}{RESET} @ {job['company']}{repost_badge}")
            print(f"     ATS: {GREEN}{scored['ats_score']:.1f}%{RESET} | FIT: {CYAN}{scored['fit_score']:.1f}%{RESET} | URL: {DIM}{job_url}{RESET}")
            if scored.get("matched_skills"):
                print(f"     Skills: {GREEN}{', '.join(scored['matched_skills'][:6])}{RESET}")
            print()

    print(f"{CYAN}Dashboard is live at: {BOLD}http://127.0.0.1:8000{RESET}\n")

def interactive_picker() -> List[str]:
    print(f"\n{BOLD}Select Role Presets to Scrape (type comma-separated numbers, e.g. 1,2,4 or 'all'):{RESET}")
    for idx, r in enumerate(ROLE_PRESETS, 1):
        print(f"  [{CYAN}{idx}{RESET}] {r}")
    
    choice = input(f"\n{BOLD}Your Choice (default: 1,2,4): {RESET}").strip()
    if not choice:
        return [ROLE_PRESETS[0], ROLE_PRESETS[1], ROLE_PRESETS[3]]
    if choice.lower() == "all":
        return ROLE_PRESETS[:]
    
    selected = []
    for part in choice.split(","):
        part = part.strip()
        if part.isdigit():
            i = int(part) - 1
            if 0 <= i < len(ROLE_PRESETS):
                selected.append(ROLE_PRESETS[i])
    return selected if selected else [ROLE_PRESETS[0]]

def main():
    parser = argparse.ArgumentParser(description="Mass LinkedIn Job Scraper")
    parser.add_argument("--presets", nargs="+", help="Specific role presets to scrape")
    parser.add_argument("--all-presets", action="store_true", help="Scrape all available presets")
    parser.add_argument("--location", default="India", help="Target location (default: India)")
    parser.add_argument("--pages", type=int, default=5, help="Number of pages per role (default: 5)")
    parser.add_argument("--time", default="r86400", help="Posted within: r86400 (24h), r604800 (7d), or '' (anytime)")
    parser.add_argument("--worktype", default="", help="Work type: 1 (onsite), 2 (remote), 3 (hybrid), '' (any)")
    parser.add_argument("--engine", default="guest_api", choices=["guest_api", "chromium"], help="Scraper engine")

    args = parser.parse_args()
    print_banner()

    if args.all_presets:
        selected_roles = ROLE_PRESETS[:]
    elif args.presets:
        selected_roles = args.presets
    else:
        if sys.stdin.isatty():
            selected_roles = interactive_picker()
        else:
            selected_roles = ["Azure Cloud Engineer", "DevOps Engineer", "Junior DevOps Engineer"]

    run_mass_scrape(
        roles=selected_roles,
        location=args.location,
        pages_per_role=args.pages,
        posted_within=args.time,
        work_type=args.worktype,
        engine=args.engine
    )

if __name__ == "__main__":
    main()

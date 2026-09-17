import re
import time
import random
import logging
from typing import List, Dict, Any, Optional, Callable
from urllib.parse import quote_plus
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from app.config import USER_AGENTS
from app.scraper.models import JobCard, JobDetail
from app.database import upsert_job, record_scrape

logger = logging.getLogger(__name__)

# ANSI Colors for clean terminal logging
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"
DIM = "\033[2m"

JOB_ID_REGEX = re.compile(r"jobPosting:(\d+)")
VIEW_ID_REGEX = re.compile(r"/view/(\d+)")

class ChromiumLinkedInScraper:
    """
    Real Chromium browser scraper for LinkedIn using Playwright.
    Simulates human browsing to bypass scraping hurdles.
    """
    def __init__(self, headless: bool = True):
        self.headless = headless

    def scrape_and_save(
        self,
        keywords: str,
        location: str = "India",
        posted_within: str = "r86400",
        work_type: str = "",
        max_pages: int = 5,
        max_jobs: Optional[int] = None,
        progress_callback: Optional[Callable[[str, int, int], None]] = None
    ) -> Dict[str, Any]:
        if max_jobs is None:
            max_jobs = max_pages * 25

        params = [
            f"keywords={quote_plus(keywords)}",
            f"location={quote_plus(location)}"
        ]
        if posted_within:
            params.append(f"f_TPR={posted_within}")
        if work_type:
            params.append(f"f_WT={work_type}")

        saved_jobs = []
        new_count = 0
        job_cards: List[JobCard] = []
        seen_ids = set()

        if progress_callback:
            progress_callback("Launching Chromium browser...", 0, max_jobs)

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=self.headless,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage"
                ]
            )
            
            context = browser.new_context(
                user_agent=random.choice(USER_AGENTS),
                viewport={"width": 1440, "height": 900},
                locale="en-US"
            )
            page = context.new_page()

            try:
                for page_idx in range(max_pages):
                    start = page_idx * 25
                    page_num = page_idx + 1
                    page_url = f"https://www.linkedin.com/jobs/search?{'&'.join(params)}&start={start}"
                    
                    print(f"  📄 [PAGE {page_num}/{max_pages}] Scanning LinkedIn results for '{keywords}' (start={start})...", flush=True)
                    if progress_callback:
                        progress_callback(f"Chromium scanning page {page_num}/{max_pages} (start={start})...", len(job_cards), max_jobs)
                    logger.info(f"Chromium navigating to page {page_num}/{max_pages}: {page_url}")

                    try:
                        page.goto(page_url, wait_until="domcontentloaded", timeout=30000)
                        time.sleep(random.uniform(2.0, 3.5))

                        # Smooth scroll to bottom to trigger lazy-loading
                        for _ in range(4):
                            page.mouse.wheel(0, 800)
                            time.sleep(random.uniform(0.7, 1.2))

                        html = page.content()
                        soup = BeautifulSoup(html, "html.parser")
                        card_elements = soup.select("div.base-card, li.jobs-search__results-list li, div[data-entity-urn]")

                        page_added = 0
                        for el in card_elements:
                            urn = el.get("data-entity-urn", "")
                            job_id = None
                            m = JOB_ID_REGEX.search(urn)
                            if m:
                                job_id = m.group(1)
                            else:
                                link_el = el.select_one("a.base-card__full-link, a.job-search-card__title-link, a[href*='/jobs/view/']")
                                if link_el:
                                    href = link_el.get("href", "")
                                    m2 = VIEW_ID_REGEX.search(href)
                                    if m2:
                                        job_id = m2.group(1)

                            if not job_id or job_id in seen_ids:
                                continue
                            seen_ids.add(job_id)

                            title_el = el.select_one(".base-search-card__title, .job-search-card__title")
                            title = title_el.get_text(strip=True) if title_el else "Unknown Title"

                            comp_el = el.select_one(".base-search-card__subtitle, .job-search-card__company-name")
                            company = comp_el.get_text(strip=True) if comp_el else "Unknown Company"

                            loc_el = el.select_one(".job-search-card__location")
                            loc = loc_el.get_text(strip=True) if loc_el else location

                            link_el = el.select_one("a.base-card__full-link, a[href*='/jobs/view/']")
                            href = link_el.get("href", "").split("?")[0] if link_el else f"https://www.linkedin.com/jobs/view/{job_id}/"

                            time_el = el.select_one("time")
                            posted_at = time_el.get_text(strip=True) if time_el else ""

                            # Check if card has reposted label
                            card_text = el.get_text().lower()
                            is_reposted = bool(re.search(r"\brepost(ed)?\b", card_text)) or "reposted" in posted_at.lower()

                            job_cards.append(JobCard(
                                linkedin_id=job_id,
                                title=title,
                                company=company,
                                location=loc,
                                url=href,
                                posted_at=posted_at,
                                is_reposted=is_reposted
                            ))
                            page_added += 1

                            if len(job_cards) >= max_jobs:
                                break

                        if page_added == 0:
                            print(f"     ↳ No new job postings found on page {page_num}. Ending pagination.", flush=True)
                            logger.info(f"No new job cards found on page {page_num}. Ending pagination.")
                            break
                        else:
                            print(f"     ↳ Discovered {page_added} postings on page {page_num} (Total unique cards: {len(job_cards)})", flush=True)

                        if len(job_cards) >= max_jobs:
                            break

                    except Exception as pe:
                        logger.warning(f"Error loading Chromium page {page_num}: {pe}")
                        break

                total_found = len(job_cards)
                print(f"\n  📦 Found {total_found} unique job postings. Fetching job descriptions & details...", flush=True)
                if progress_callback:
                    progress_callback(f"Found {total_found} postings across pages. Fetching full job details...", 0, total_found)

                # Visit each job view page to get rich description and criteria
                for idx, card in enumerate(job_cards):
                    repost_marker = " [REPOSTED]" if card.is_reposted else ""
                    if progress_callback:
                        progress_callback(f"[{idx+1}/{total_found}] Chromium JD: {card.title} @ {card.company}{repost_marker}", idx + 1, total_found)

                    try:
                        view_url = f"https://www.linkedin.com/jobs/view/{card.linkedin_id}/"
                        page.goto(view_url, wait_until="domcontentloaded", timeout=20000)
                        time.sleep(random.uniform(1.2, 2.2))

                        detail_html = page.content()
                        detail_soup = BeautifulSoup(detail_html, "html.parser")

                        # Description
                        desc_el = detail_soup.select_one(".show-more-less-html__markup, .description__text, .jobs-description__content")
                        if desc_el:
                            for br in desc_el.find_all(["br", "p", "li"]):
                                br.insert_after("\n")
                            raw_desc = desc_el.get_text()
                            lines = [l.strip() for l in raw_desc.splitlines() if l.strip()]
                            description = "\n\n".join(lines)
                        else:
                            description = ""

                        # Seniority & Employment type
                        experience_level = ""
                        employment_type = ""
                        criteria_items = detail_soup.select(".description__job-criteria-item")
                        for item in criteria_items:
                            header = item.select_one(".description__job-criteria-subheader")
                            val = item.select_one(".description__job-criteria-text")
                            if header and val:
                                h_text = header.get_text(strip=True).lower()
                                v_text = val.get_text(strip=True)
                                if "seniority" in h_text:
                                    experience_level = v_text
                                elif "employment" in h_text:
                                    employment_type = v_text

                        # Work mode
                        full_text = f"{card.title} {card.location} {description}".lower()
                        if "remote" in full_text:
                            work_mode = "Remote"
                        elif "hybrid" in full_text:
                            work_mode = "Hybrid"
                        else:
                            work_mode = "On-site"

                        # Reposted check on full page
                        is_reposted = card.is_reposted or bool(re.search(r"\brepost(ed)?\b", detail_html[:4000], re.IGNORECASE))

                        job_dict = {
                            "linkedin_id": card.linkedin_id,
                            "title": card.title,
                            "company": card.company,
                            "location": card.location,
                            "url": card.url,
                            "posted_at": card.posted_at,
                            "employment_type": employment_type,
                            "experience_level": experience_level,
                            "work_mode": work_mode,
                            "salary": "",
                            "description": description,
                            "is_reposted": 1 if is_reposted else 0
                        }

                        # Evaluate match score against candidate resume immediately
                        from app.resume.structure import get_active_profile
                        from app.matcher.scoring import score_job
                        profile = get_active_profile()
                        scored = score_job(job_dict, profile)
                        job_dict.update({
                            "ats_score": scored["ats_score"],
                            "fit_score": scored["fit_score"],
                            "priority": scored["priority"],
                            "matched_skills": scored["matched_skills"],
                            "missing_skills": scored["missing_skills"],
                            "hard_req_concerns": scored["hard_req_concerns"],
                            "score_breakdown": scored["score_breakdown"],
                            "ai_analysis": scored.get("ai_analysis", ""),
                            "required_experience": scored.get("required_experience"),
                            "seniority": scored.get("seniority", "")
                        })

                        job_id, is_new = upsert_job(job_dict)
                        if is_new:
                            new_count += 1
                        job_dict["id"] = job_id
                        saved_jobs.append(job_dict)

                        repost_badge = f" {RED}{BOLD}🚨 [REPOSTED]{RESET}" if is_reposted else ""
                        save_status = f"{GREEN}+NEW{RESET}" if is_new else f"{DIM}EXISTING{RESET}"
                        prio = scored["priority"]
                        prio_tag = f"{GREEN}{BOLD}🔥 HIGH{RESET}" if prio == "HIGH" else (f"{YELLOW}⚡ MED{RESET}" if prio == "MEDIUM" else f"{DIM}LOW{RESET}")

                        print(f"  ▸ [{idx+1}/{total_found}] {BOLD}{card.title}{RESET} @ {card.company}{repost_badge}", flush=True)
                        print(f"     📊 Match: {BOLD}{scored['ats_score']:.0f}% ATS{RESET} | {BOLD}{scored['fit_score']:.0f}% FIT{RESET} | {prio_tag}", flush=True)
                        print(f"     📍 {card.location} | {work_mode} | {card.posted_at or 'Recently'} [{save_status}]", flush=True)
                        print(f"     🔗 {card.url}", flush=True)

                    except Exception as e:
                        print(f"  {RED}⚠ Failed to fetch detail for {card.linkedin_id}: {e}{RESET}", flush=True)
                        logger.warning(f"Failed to fetch detail for {card.linkedin_id} in Chromium: {e}")

                record_scrape(keywords, location, total_found, new_count)

            finally:
                browser.close()

        return {
            "total_found": len(saved_jobs),
            "new_added": new_count,
            "jobs": saved_jobs
        }

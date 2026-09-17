import re
import time
import random
import logging
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote_plus
from typing import List, Dict, Optional, Callable, Any
from app.config import LINKEDIN_GUEST_SEARCH_URL, LINKEDIN_GUEST_JOB_URL, USER_AGENTS
from app.scraper.models import JobCard, JobDetail

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

class LinkedInScraper:
    def __init__(self):
        self.session = requests.Session()
        
    def _get_headers(self) -> Dict[str, str]:
        return {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": "https://www.google.com/",
            "Sec-Ch-Ua": '"Chromium";v="122", "Not(A:Brand";v="24"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Linux"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "cross-site",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1"
        }

    def search_cards(
        self,
        keywords: str,
        location: str = "India",
        posted_within: str = "r86400",
        work_type: str = "",
        max_pages: int = 5,
        progress_callback: Optional[Callable[[str, int, int], None]] = None
    ) -> List[JobCard]:
        """
        Searches LinkedIn guest API across multiple pages (1, 2, 3, 4, 5...)
        LinkedIn serves ~25 results per page, indexed by start=0, 25, 50, 75...
        """
        cards: List[JobCard] = []
        seen_ids = set()
        
        for page in range(max_pages):
            start = page * 25
            page_num = page + 1
            print(f"  📄 [PAGE {page_num}/{max_pages}] Scanning LinkedIn results for '{keywords}' (start={start})...", flush=True)
            if progress_callback:
                progress_callback(f"Scanning search page {page_num}/{max_pages} for '{keywords}' (start={start})...", len(cards), max_pages * 25)
            logger.info(f"Scanning LinkedIn page {page_num}/{max_pages} for '{keywords}' (start={start})...")

            params = [
                f"keywords={quote_plus(keywords)}",
                f"location={quote_plus(location)}",
                f"start={start}"
            ]
            if posted_within:
                params.append(f"f_TPR={posted_within}")
            if work_type:
                params.append(f"f_WT={work_type}")
                
            url = f"{LINKEDIN_GUEST_SEARCH_URL}?{'&'.join(params)}"
            
            try:
                resp = self.session.get(url, headers=self._get_headers(), timeout=15)
                if resp.status_code != 200 or not resp.text.strip():
                    logger.warning(f"LinkedIn search page {page_num} returned status {resp.status_code}")
                    break
                    
                soup = BeautifulSoup(resp.text, "html.parser")
                card_elements = soup.select("div[data-entity-urn], li div.base-card")
                
                if not card_elements:
                    print(f"     ↳ No more cards found at page {page_num}. Ending pagination.", flush=True)
                    logger.info(f"No more cards found at page {page_num}. Ending search pagination.")
                    break
                    
                page_found = 0
                for el in card_elements:
                    urn = el.get("data-entity-urn", "")
                    match = JOB_ID_REGEX.search(urn)
                    job_id = None
                    if match:
                        job_id = match.group(1)
                    else:
                        link_el = el.select_one("a.base-card__full-link, a[href*='/jobs/view/']")
                        if link_el:
                            href = link_el.get("href", "")
                            m2 = re.search(r"/view/(\d+)", href)
                            if m2:
                                job_id = m2.group(1)

                    if not job_id or job_id in seen_ids:
                        continue
                    seen_ids.add(job_id)
                    
                    title_el = el.select_one(".base-search-card__title, .job-search-card__title")
                    title = title_el.get_text(strip=True) if title_el else "Unknown Title"
                    
                    comp_el = el.select_one(".base-search-card__subtitle a, .base-search-card__subtitle, .job-search-card__company-name")
                    company = comp_el.get_text(strip=True) if comp_el else "Unknown Company"
                    
                    loc_el = el.select_one(".job-search-card__location")
                    loc = loc_el.get_text(strip=True) if loc_el else location
                    
                    link_el = el.select_one("a.base-card__full-link, a[href*='/jobs/view/']")
                    job_url = link_el.get("href", "").split("?")[0] if link_el else f"https://www.linkedin.com/jobs/view/{job_id}/"
                    
                    time_el = el.select_one("time")
                    posted_at = time_el.get_text(strip=True) if time_el else ""

                    # Detect if job is reposted
                    card_raw_text = el.get_text().lower()
                    is_reposted = bool(re.search(r"\brepost(ed)?\b", card_raw_text)) or "reposted" in posted_at.lower()
                    
                    cards.append(JobCard(
                        linkedin_id=job_id,
                        title=title,
                        company=company,
                        location=loc,
                        url=job_url,
                        posted_at=posted_at,
                        is_reposted=is_reposted
                    ))
                    page_found += 1
                    
                if page_found == 0:
                    print(f"     ↳ No new unique cards found on page {page_num}. Ending pagination.", flush=True)
                    logger.info(f"Page {page_num} had 0 new unique cards. Ending pagination.")
                    break
                else:
                    print(f"     ↳ Discovered {page_found} postings on page {page_num} (Total unique cards: {len(cards)})", flush=True)
                    
                time.sleep(random.uniform(1.2, 2.2))
                
            except Exception as e:
                logger.error(f"Error fetching LinkedIn page {page_num}: {e}")
                break
                
        return cards

    def fetch_job_detail(self, card: JobCard) -> JobDetail:
        """
        Fetches full job posting details from LinkedIn guest job API.
        """
        detail_url = f"{LINKEDIN_GUEST_JOB_URL}/{card.linkedin_id}"
        
        detail = JobDetail(
            linkedin_id=card.linkedin_id,
            title=card.title,
            company=card.company,
            location=card.location,
            url=card.url,
            posted_at=card.posted_at,
            is_reposted=card.is_reposted
        )
        
        try:
            resp = self.session.get(detail_url, headers=self._get_headers(), timeout=15)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                
                # Check for reposted tags in topcard/sublines
                soup_subline = soup.select_one(".topcard__flavor--bullet, .top-card-layout__second-subline, .posted-time-ago__text")
                if soup_subline and re.search(r"\brepost(ed)?\b", soup_subline.get_text(), re.IGNORECASE):
                    detail.is_reposted = True
                elif re.search(r"\brepost(ed)?\b", resp.text[:4000], re.IGNORECASE):
                    detail.is_reposted = True
                
                # Title fallback
                t_el = soup.select_one(".topcard__title, .top-card-layout__title")
                if t_el and (not detail.title or detail.title == "Unknown Title"):
                    detail.title = t_el.get_text(strip=True)
                    
                # Company fallback
                c_el = soup.select_one(".topcard__flavor a, .topcard__flavor, .top-card-layout__first-subline")
                if c_el and (not detail.company or detail.company == "Unknown Company"):
                    detail.company = c_el.get_text(strip=True)
                    
                # Location fallback
                l_el = soup.select_one(".topcard__flavor--bullet, .top-card-layout__second-subline")
                if l_el:
                    loc_text = l_el.get_text(strip=True)
                    if loc_text and not re.search(r"applicant", loc_text, re.IGNORECASE):
                        detail.location = loc_text
                        
                # Description
                desc_el = soup.select_one(".show-more-less-html__markup, .description__text")
                if desc_el:
                    # Clean up HTML into readable text while keeping paragraphs
                    for br in desc_el.find_all(["br", "p", "li"]):
                        br.insert_after("\n")
                    raw_text = desc_el.get_text()
                    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
                    detail.description = "\n\n".join(lines)
                else:
                    detail.description = ""

                # Criteria list (Seniority, Employment Type, etc.)
                criteria_items = soup.select(".description__job-criteria-item")
                for item in criteria_items:
                    header = item.select_one(".description__job-criteria-subheader")
                    val = item.select_one(".description__job-criteria-text")
                    if header and val:
                        h_text = header.get_text(strip=True).lower()
                        v_text = val.get_text(strip=True)
                        if "seniority" in h_text:
                            detail.experience_level = v_text
                        elif "employment" in h_text:
                            detail.employment_type = v_text

                # Work mode detection
                full_text = f"{detail.title} {detail.location} {detail.description}".lower()
                if "remote" in full_text:
                    detail.work_mode = "Remote"
                elif "hybrid" in full_text:
                    detail.work_mode = "Hybrid"
                elif "on-site" in full_text or "onsite" in full_text:
                    detail.work_mode = "On-site"
                else:
                    detail.work_mode = "On-site"

                # Salary detection (badge or text)
                salary_el = soup.select_one(".main-job-card__salary-info, .topcard__flavor--salary")
                if salary_el:
                    detail.salary = salary_el.get_text(strip=True)
                else:
                    # Check text for salary pattern (e.g. ₹... or $...)
                    sal_match = re.search(r"(\$|₹|INR|USD)\s?[\d,]+(?:\s?-\s?(\$|₹|INR|USD)?\s?[\d,]+)?(?:\s?(?:k|lac|lpa|year|hr|month))?", detail.description, re.IGNORECASE)
                    if sal_match:
                        detail.salary = sal_match.group(0).strip()
            else:
                logger.warning(f"Could not fetch detail for job {card.linkedin_id}: HTTP {resp.status_code}")
                
        except Exception as e:
            logger.error(f"Error fetching job detail {card.linkedin_id}: {e}")
            
        return detail

    def scrape_and_save(
        self,
        keywords: str,
        location: str = "India",
        posted_within: str = "r86400",
        work_type: str = "",
        max_pages: int = 5,
        progress_callback: Optional[Callable[[str, int, int], None]] = None
    ) -> Dict[str, Any]:
        """
        Coordinates card search across multiple pages, detail fetching, and DB upsert.
        """
        from app.database import upsert_job, record_scrape
        
        if progress_callback:
            progress_callback(f"Scanning up to {max_pages} pages for '{keywords}'...", 0, 0)
            
        cards = self.search_cards(
            keywords=keywords,
            location=location,
            posted_within=posted_within,
            work_type=work_type,
            max_pages=max_pages,
            progress_callback=progress_callback
        )
        
        total = len(cards)
        new_count = 0
        saved_jobs = []
        
        print(f"\n  📦 Found {total} unique job postings. Fetching job descriptions & details...", flush=True)
        
        from app.resume.structure import get_active_profile
        from app.matcher.scoring import score_job
        profile = get_active_profile()

        for idx, card in enumerate(cards):
            repost_tag = " [REPOSTED]" if card.is_reposted else ""
            if progress_callback:
                progress_callback(f"[{idx+1}/{total}] Hydrating JD: {card.title} @ {card.company}{repost_tag}", idx + 1, total)
                
            detail = self.fetch_job_detail(card)
            
            job_dict = {
                "linkedin_id": detail.linkedin_id,
                "title": detail.title,
                "company": detail.company,
                "location": detail.location,
                "url": detail.url,
                "posted_at": detail.posted_at,
                "employment_type": detail.employment_type,
                "experience_level": detail.experience_level,
                "work_mode": detail.work_mode,
                "salary": detail.salary,
                "description": detail.description,
                "is_reposted": 1 if detail.is_reposted else 0,
            }

            # Evaluate match score against candidate resume immediately
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
            
            repost_badge = f" {RED}{BOLD}🚨 [REPOSTED]{RESET}" if detail.is_reposted else ""
            save_status = f"{GREEN}+NEW{RESET}" if is_new else f"{DIM}EXISTING{RESET}"
            prio = scored["priority"]
            prio_tag = f"{GREEN}{BOLD}🔥 HIGH{RESET}" if prio == "HIGH" else (f"{YELLOW}⚡ MED{RESET}" if prio == "MEDIUM" else f"{DIM}LOW{RESET}")
            
            print(f"  ▸ [{idx+1}/{total}] {BOLD}{detail.title}{RESET} @ {detail.company}{repost_badge}", flush=True)
            print(f"     📊 Match: {BOLD}{scored['ats_score']:.0f}% ATS{RESET} | {BOLD}{scored['fit_score']:.0f}% FIT{RESET} | {prio_tag}", flush=True)
            print(f"     📍 {detail.location} | {detail.work_mode} | {detail.posted_at or 'Recently'} [{save_status}]", flush=True)
            print(f"     🔗 {detail.url}", flush=True)
            
            # Politeness jitter
            time.sleep(random.uniform(1.2, 2.2))
            
        record_scrape(keywords, location, total, new_count)
        
        return {
            "total_found": total,
            "new_added": new_count,
            "jobs": saved_jobs
        }

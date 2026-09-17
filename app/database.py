import sqlite3
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any
from app.config import DB_PATH

def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# Ensure tables exist at startup
def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        linkedin_id TEXT UNIQUE NOT NULL,
        title TEXT NOT NULL,
        company TEXT NOT NULL,
        location TEXT,
        url TEXT NOT NULL,
        posted_at TEXT,
        employment_type TEXT,
        experience_level TEXT,
        work_mode TEXT,
        salary TEXT,
        description TEXT,
        scraped_at TEXT,
        ats_score REAL DEFAULT 0.0,
        fit_score REAL DEFAULT 0.0,
        priority TEXT DEFAULT 'MEDIUM',
        matched_skills TEXT DEFAULT '[]',
        missing_skills TEXT DEFAULT '[]',
        hard_req_concerns TEXT DEFAULT '[]',
        score_breakdown TEXT DEFAULT '{}',
        ai_analysis TEXT DEFAULT '',
        status TEXT DEFAULT 'new'
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS candidate_profile (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        profile_json TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS scrape_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        keywords TEXT NOT NULL,
        location TEXT NOT NULL,
        jobs_found INTEGER DEFAULT 0,
        new_jobs INTEGER DEFAULT 0
    );
    """)

    # Ensure required_experience, seniority, is_reposted, and dedup_key columns exist
    cursor.execute("PRAGMA table_info(jobs)")
    existing_cols = [c["name"] for c in cursor.fetchall()]
    if "required_experience" not in existing_cols:
        cursor.execute("ALTER TABLE jobs ADD COLUMN required_experience REAL DEFAULT NULL")
    if "seniority" not in existing_cols:
        cursor.execute("ALTER TABLE jobs ADD COLUMN seniority TEXT DEFAULT ''")
    if "is_reposted" not in existing_cols:
        cursor.execute("ALTER TABLE jobs ADD COLUMN is_reposted INTEGER DEFAULT 0")
    if "dedup_key" not in existing_cols:
        cursor.execute("ALTER TABLE jobs ADD COLUMN dedup_key TEXT DEFAULT ''")

    # Indices for fast queries
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_linkedin_id ON jobs(linkedin_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_dedup_key ON jobs(dedup_key);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_ats_score ON jobs(ats_score);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_fit_score ON jobs(fit_score);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_priority ON jobs(priority);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_req_exp ON jobs(required_experience);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_is_reposted ON jobs(is_reposted);")

    conn.commit()
    conn.close()

import re
from difflib import SequenceMatcher

def normalize_company(c: str) -> str:
    if not c:
        return ""
    c = c.lower()
    # Remove common corporate suffixes & geography noise
    c = re.sub(r'\b(in india|india|pvt ltd|private limited|ltd|limited|llc|inc|corporation|corp|technologies|solutions|services|global capability center)\b', '', c)
    c = re.sub(r'[^a-z0-9]', '', c)
    return c.strip()

def normalize_title(t: str) -> str:
    if not t:
        return ""
    t = t.lower()
    # Remove parenthesis, brackets, and requisition codes (e.g. IRC12345, walk-in drive)
    t = re.sub(r'\(.*?\)', '', t)
    t = re.sub(r'\[.*?\]', '', t)
    t = re.sub(r'\b(irc\d+|walk-in drive|\d+th sep \d+)\b', '', t)
    t = re.sub(r'[^a-z0-9]', '', t)
    return t.strip()

def compute_dedup_key(company: str, title: str) -> str:
    c_norm = normalize_company(company)
    t_norm = normalize_title(title)
    if not c_norm or not t_norm:
        return ""
    return f"{c_norm}:{t_norm}"

def merge_locations(loc1: str, loc2: str) -> str:
    if not loc1:
        return loc2 or ""
    if not loc2:
        return loc1 or ""
    if loc1.lower().strip() == loc2.lower().strip():
        return loc1
    parts1 = [p.strip() for p in loc1.split(',') if p.strip()]
    parts2 = [p.strip() for p in loc2.split(',') if p.strip()]
    city1 = parts1[0] if parts1 else loc1
    city2 = parts2[0] if parts2 else loc2
    if city1.lower() == city2.lower():
        return loc1
    if city2.lower() in loc1.lower():
        return loc1
    return f"{loc1} / {city2}"

def upsert_job(job: Dict[str, Any]) -> tuple[int, bool]:
    """
    Inserts or updates a job with smart deduplication.
    Prevents duplicate multi-city or re-listed job postings from creating duplicate cards.
    Returns (job_id, is_new).
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    now = datetime.now(timezone.utc).isoformat()
    linkedin_id = str(job.get("linkedin_id", ""))
    company = job.get("company", "Unknown Company")
    title = job.get("title", "Unknown Title")
    dedup_key = compute_dedup_key(company, title)

    is_reposted_val = job.get("is_reposted")
    if is_reposted_val is None:
        posted_str = str(job.get("posted_at", "")).lower()
        desc_start = str(job.get("description", ""))[:300].lower()
        is_reposted_val = 1 if ("repost" in posted_str or "reposted" in desc_start) else 0
    else:
        is_reposted_val = 1 if is_reposted_val else 0

    # 1. Primary check by linkedin_id
    cursor.execute("SELECT id, location, description, is_reposted, status FROM jobs WHERE linkedin_id = ?", (linkedin_id,))
    existing = cursor.fetchone()
    
    # 2. Canonical check by dedup_key if linkedin_id is different (same role at same company)
    if not existing and dedup_key:
        cursor.execute("SELECT id, location, description, is_reposted, status FROM jobs WHERE dedup_key = ?", (dedup_key,))
        existing = cursor.fetchone()
        
        # 3. Fuzzy title check if exact key didn't match
        if not existing:
            comp_norm = normalize_company(company)
            if comp_norm:
                cursor.execute("SELECT id, title, location, description, is_reposted, status, dedup_key FROM jobs WHERE dedup_key LIKE ?", (f"{comp_norm}:%",))
                candidates = cursor.fetchall()
                t_norm = normalize_title(title)
                for cand in candidates:
                    cand_title_norm = cand["dedup_key"].split(":", 1)[1] if ":" in cand["dedup_key"] else normalize_title(cand["title"])
                    if cand_title_norm and t_norm and SequenceMatcher(None, cand_title_norm, t_norm).ratio() >= 0.88:
                        existing = cand
                        break

    if existing:
        job_id = existing["id"]
        merged_loc = merge_locations(existing["location"], job.get("location", ""))
        merged_reposted = 1 if (existing["is_reposted"] or is_reposted_val) else 0

        # Update description / fields if they weren't fetched before
        cursor.execute("""
            UPDATE jobs SET
                title = COALESCE(NULLIF(?, ''), title),
                company = COALESCE(NULLIF(?, ''), company),
                location = ?,
                url = COALESCE(NULLIF(?, ''), url),
                posted_at = COALESCE(NULLIF(?, ''), posted_at),
                employment_type = COALESCE(NULLIF(?, ''), employment_type),
                experience_level = COALESCE(NULLIF(?, ''), experience_level),
                work_mode = COALESCE(NULLIF(?, ''), work_mode),
                salary = COALESCE(NULLIF(?, ''), salary),
                description = CASE WHEN LENGTH(?) > LENGTH(COALESCE(description, '')) THEN ? ELSE description END,
                is_reposted = ?,
                dedup_key = COALESCE(NULLIF(?, ''), dedup_key),
                ats_score = COALESCE(?, ats_score),
                fit_score = COALESCE(?, fit_score),
                priority = COALESCE(?, priority),
                matched_skills = COALESCE(?, matched_skills),
                missing_skills = COALESCE(?, missing_skills),
                hard_req_concerns = COALESCE(?, hard_req_concerns),
                score_breakdown = COALESCE(?, score_breakdown),
                ai_analysis = COALESCE(?, ai_analysis),
                required_experience = COALESCE(?, required_experience),
                seniority = COALESCE(?, seniority)
            WHERE id = ?
        """, (
            job.get("title"),
            job.get("company"),
            merged_loc,
            job.get("url"),
            job.get("posted_at"),
            job.get("employment_type"),
            job.get("experience_level"),
            job.get("work_mode"),
            job.get("salary"),
            job.get("description", ""),
            job.get("description", ""),
            merged_reposted,
            dedup_key,
            job.get("ats_score"),
            job.get("fit_score"),
            job.get("priority"),
            json.dumps(job["matched_skills"]) if "matched_skills" in job else None,
            json.dumps(job["missing_skills"]) if "missing_skills" in job else None,
            json.dumps(job["hard_req_concerns"]) if "hard_req_concerns" in job else None,
            json.dumps(job["score_breakdown"]) if "score_breakdown" in job else None,
            job.get("ai_analysis"),
            job.get("required_experience"),
            job.get("seniority"),
            job_id
        ))
        conn.commit()
        conn.close()
        return job_id, False
    else:
        cursor.execute("""
            INSERT INTO jobs (
                linkedin_id, title, company, location, url, posted_at,
                employment_type, experience_level, work_mode, salary,
                description, scraped_at, is_reposted, status, dedup_key,
                ats_score, fit_score, priority, matched_skills, missing_skills,
                hard_req_concerns, score_breakdown, ai_analysis, required_experience, seniority
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            linkedin_id,
            job.get("title", "Unknown Title"),
            job.get("company", "Unknown Company"),
            job.get("location", ""),
            job.get("url", ""),
            job.get("posted_at", ""),
            job.get("employment_type", ""),
            job.get("experience_level", ""),
            job.get("work_mode", ""),
            job.get("salary", ""),
            job.get("description", ""),
            job.get("scraped_at", now),
            is_reposted_val,
            dedup_key,
            job.get("ats_score", 0.0),
            job.get("fit_score", 0.0),
            job.get("priority", "MEDIUM"),
            json.dumps(job.get("matched_skills", [])),
            json.dumps(job.get("missing_skills", [])),
            json.dumps(job.get("hard_req_concerns", [])),
            json.dumps(job.get("score_breakdown", {})),
            job.get("ai_analysis", ""),
            job.get("required_experience"),
            job.get("seniority", "")
        ))
        job_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return job_id, True

def deduplicate_database() -> Dict[str, Any]:
    """
    Scans all jobs in SQLite database and merges duplicate postings from the same company.
    Merges multi-city locations, retains applied/saved status, and removes redundant duplicate rows.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id, linkedin_id, title, company, location, work_mode, description, posted_at, is_reposted, status, ats_score, fit_score, priority, dedup_key FROM jobs ORDER BY id ASC")
    all_jobs = [dict(r) for r in cursor.fetchall()]

    primary_map: Dict[str, Dict[str, Any]] = {}
    duplicates_merged = 0

    for j in all_jobs:
        k = j.get("dedup_key") or compute_dedup_key(j["company"], j["title"])
        if not k:
            continue

        cursor.execute("UPDATE jobs SET dedup_key = ? WHERE id = ? AND (dedup_key IS NULL OR dedup_key = '')", (k, j["id"]))

        found_key = None
        if k in primary_map:
            found_key = k
        else:
            comp_prefix = normalize_company(j["company"]) + ":"
            for ex_key in primary_map.keys():
                if ex_key.startswith(comp_prefix):
                    ex_title = ex_key[len(comp_prefix):]
                    cur_title = k[len(comp_prefix):]
                    if ex_title and cur_title and SequenceMatcher(None, ex_title, cur_title).ratio() >= 0.88:
                        found_key = ex_key
                        break

        if found_key:
            primary = primary_map[found_key]
            merged_loc = merge_locations(primary["location"], j["location"])
            merged_reposted = 1 if (primary["is_reposted"] or j["is_reposted"]) else 0

            # Keep highest user status: applied > rejected > saved > ignored > new
            status_order = {"applied": 5, "rejected": 4, "saved": 3, "ignored": 2, "new": 1}
            p_status = primary.get("status") or "new"
            j_status = j.get("status") or "new"
            merged_status = j_status if status_order.get(j_status, 1) > status_order.get(p_status, 1) else p_status

            p_desc = primary.get("description") or ""
            j_desc = j.get("description") or ""
            merged_desc = j_desc if len(j_desc) > len(p_desc) else p_desc

            cursor.execute("""
                UPDATE jobs SET
                    location = ?,
                    is_reposted = ?,
                    status = ?,
                    description = ?
                WHERE id = ?
            """, (merged_loc, merged_reposted, merged_status, merged_desc, primary["id"]))

            cursor.execute("DELETE FROM jobs WHERE id = ?", (j["id"],))
            duplicates_merged += 1

            primary["location"] = merged_loc
            primary["is_reposted"] = merged_reposted
            primary["status"] = merged_status
            primary["description"] = merged_desc
        else:
            primary_map[k] = j

    conn.commit()
    cursor.execute("SELECT COUNT(*) as c FROM jobs")
    final_count = cursor.fetchone()["c"]
    conn.close()

    return {
        "initial_count": len(all_jobs),
        "cleaned_count": final_count,
        "duplicates_removed": duplicates_merged
    }

def update_job_scores(
    job_id: int,
    ats_score: float,
    fit_score: float,
    priority: str,
    matched_skills: List[str],
    missing_skills: List[str],
    hard_req_concerns: List[str],
    score_breakdown: Dict[str, Any],
    ai_analysis: str = "",
    required_experience: Optional[float] = None,
    seniority: str = ""
):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE jobs SET
            ats_score = ?,
            fit_score = ?,
            priority = ?,
            matched_skills = ?,
            missing_skills = ?,
            hard_req_concerns = ?,
            score_breakdown = ?,
            ai_analysis = ?,
            required_experience = ?,
            seniority = ?
        WHERE id = ?
    """, (
        ats_score,
        fit_score,
        priority,
        json.dumps(matched_skills),
        json.dumps(missing_skills),
        json.dumps(hard_req_concerns),
        json.dumps(score_breakdown),
        ai_analysis,
        required_experience,
        seniority,
        job_id
    ))
    conn.commit()
    conn.close()

def get_job_by_id(job_id: int) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    d["matched_skills"] = json.loads(d["matched_skills"] or "[]")
    d["missing_skills"] = json.loads(d["missing_skills"] or "[]")
    d["hard_req_concerns"] = json.loads(d["hard_req_concerns"] or "[]")
    d["score_breakdown"] = json.loads(d["score_breakdown"] or "{}")
    return d

def get_all_jobs_for_scoring() -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, linkedin_id, title, company, location, url, is_reposted, posted_at, experience_level, work_mode, description FROM jobs")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_jobs(
    min_ats: Optional[float] = None,
    min_fit: Optional[float] = None,
    max_exp: Optional[float] = 3.0,
    priority: Optional[str] = None,
    work_mode: Optional[str] = None,
    experience_level: Optional[str] = None,
    status: Optional[str] = None,
    keyword: Optional[str] = None,
    location: Optional[str] = None,
    sort_by: str = "priority_desc",
    limit: int = 100,
    offset: int = 0
) -> Dict[str, Any]:
    conn = get_db_connection()
    cursor = conn.cursor()
    
    conditions = []
    params = []
    
    # Strict Experience Cap (e.g. max 3.0 years filters out 4+ yr / Senior / Lead roles)
    if max_exp is not None and max_exp > 0:
        if max_exp <= 3.0:
            conditions.append("""(
                (required_experience IS NULL OR required_experience <= ?)
                AND LOWER(title) NOT LIKE '%senior%'
                AND LOWER(title) NOT LIKE '%sr.%'
                AND LOWER(title) NOT LIKE '%sr %'
                AND LOWER(title) NOT LIKE '%sr-%'
                AND LOWER(title) NOT LIKE '%lead%'
                AND LOWER(title) NOT LIKE '%principal%'
                AND LOWER(title) NOT LIKE '%staff%'
                AND LOWER(title) NOT LIKE '%architect%'
                AND LOWER(title) NOT LIKE '%director%'
                AND LOWER(title) NOT LIKE '%manager%'
                AND (experience_level IS NULL OR LOWER(experience_level) NOT LIKE '%mid-senior%')
                AND (experience_level IS NULL OR LOWER(experience_level) NOT LIKE '%director%')
            )""")
            params.append(max_exp)
        else:
            conditions.append("(required_experience IS NULL OR required_experience <= ?)")
            params.append(max_exp)
    
    if min_ats is not None and min_ats > 0:
        conditions.append("ats_score >= ?")
        params.append(min_ats)
        
    if min_fit is not None and min_fit > 0:
        conditions.append("fit_score >= ?")
        params.append(min_fit)
        
    if priority and priority.upper() != "ALL":
        conditions.append("priority = ?")
        params.append(priority.upper())
        
    if work_mode and work_mode.lower() != "all":
        conditions.append("LOWER(work_mode) LIKE ?")
        params.append(f"%{work_mode.lower()}%")
        
    if experience_level and experience_level.lower() != "all":
        conditions.append("LOWER(experience_level) LIKE ?")
        params.append(f"%{experience_level.lower()}%")
        
    if status and status.lower() != "all":
        if status.lower() == "new":
            conditions.append("(status = 'new' OR status IS NULL)")
        else:
            conditions.append("status = ?")
            params.append(status.lower())
        
    if keyword:
        conditions.append("(LOWER(title) LIKE ? OR LOWER(company) LIKE ? OR LOWER(description) LIKE ?)")
        wildcard = f"%{keyword.lower()}%"
        params.extend([wildcard, wildcard, wildcard])
        
    if location and location.lower() != "all":
        conditions.append("LOWER(location) LIKE ?")
        params.append(f"%{location.lower()}%")

    where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""
    
    # Sorting
    sort_orders = {
        "priority_desc": """
            CASE priority 
                WHEN 'HIGH' THEN 1 
                WHEN 'MEDIUM' THEN 2 
                WHEN 'LOW' THEN 3 
                ELSE 4 
            END ASC, ats_score DESC, fit_score DESC
        """,
        "ats_desc": "ats_score DESC, fit_score DESC",
        "fit_desc": "fit_score DESC, ats_score DESC",
        "date_desc": "scraped_at DESC, id DESC"
    }
    order_clause = sort_orders.get(sort_by, sort_orders["priority_desc"])
    
    # Total count
    cursor.execute(f"SELECT COUNT(*) as cnt FROM jobs {where_clause}", params)
    total_count = cursor.fetchone()["cnt"]
    
    query = f"""
        SELECT * FROM jobs
        {where_clause}
        ORDER BY {order_clause}
        LIMIT ? OFFSET ?
    """
    params.extend([limit, offset])
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    
    jobs_list = []
    for r in rows:
        d = dict(r)
        d["matched_skills"] = json.loads(d["matched_skills"] or "[]")
        d["missing_skills"] = json.loads(d["missing_skills"] or "[]")
        d["hard_req_concerns"] = json.loads(d["hard_req_concerns"] or "[]")
        d["score_breakdown"] = json.loads(d["score_breakdown"] or "{}")
        jobs_list.append(d)
        
    return {
        "total": total_count,
        "limit": limit,
        "offset": offset,
        "jobs": jobs_list
    }

def set_job_status(job_id: int, status: str) -> bool:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE jobs SET status = ? WHERE id = ?", (status.lower(), job_id))
    affected = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return affected

def save_profile(profile_dict: Dict[str, Any]):
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    profile_json = json.dumps(profile_dict, indent=2)
    cursor.execute("""
        INSERT INTO candidate_profile (id, profile_json, updated_at)
        VALUES (1, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            profile_json = excluded.profile_json,
            updated_at = excluded.updated_at
    """, (profile_json, now))
    conn.commit()
    conn.close()

def get_profile() -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT profile_json FROM candidate_profile WHERE id = 1")
    row = cursor.fetchone()
    conn.close()
    if row and row["profile_json"]:
        return json.loads(row["profile_json"])
    return None

def get_stats() -> Dict[str, Any]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as total FROM jobs")
    total = cursor.fetchone()["total"]
    
    cursor.execute("SELECT COUNT(DISTINCT linkedin_id) as unique_jobs FROM jobs")
    unique_jobs = cursor.fetchone()["unique_jobs"]
    
    cursor.execute("SELECT COUNT(*) as scored FROM jobs WHERE ats_score > 0")
    scored = cursor.fetchone()["scored"]
    
    cursor.execute("SELECT COUNT(*) as high_priority FROM jobs WHERE priority = 'HIGH'")
    high_priority = cursor.fetchone()["high_priority"]

    cursor.execute("SELECT AVG(ats_score) as avg_ats, AVG(fit_score) as avg_fit FROM jobs WHERE ats_score > 0")
    avg_row = cursor.fetchone()
    avg_ats = round(avg_row["avg_ats"] or 0, 1)
    avg_fit = round(avg_row["avg_fit"] or 0, 1)

    cursor.execute("SELECT COUNT(*) as cnt FROM jobs WHERE (status = 'new' OR status IS NULL)")
    count_new = cursor.fetchone()["cnt"]

    cursor.execute("SELECT COUNT(*) as cnt FROM jobs WHERE status = 'saved'")
    count_saved = cursor.fetchone()["cnt"]

    cursor.execute("SELECT COUNT(*) as cnt FROM jobs WHERE status = 'applied'")
    count_applied = cursor.fetchone()["cnt"]

    cursor.execute("SELECT COUNT(*) as cnt FROM jobs WHERE status = 'rejected'")
    count_rejected = cursor.fetchone()["cnt"]

    cursor.execute("SELECT COUNT(*) as cnt FROM jobs WHERE status = 'ignored'")
    count_ignored = cursor.fetchone()["cnt"]

    conn.close()
    return {
        "total": total,
        "unique": unique_jobs,
        "scored": scored,
        "high_priority": high_priority,
        "avg_ats": avg_ats,
        "avg_fit": avg_fit,
        "count_new": count_new,
        "count_saved": count_saved,
        "count_applied": count_applied,
        "count_rejected": count_rejected,
        "count_ignored": count_ignored
    }

def record_scrape(keywords: str, location: str, found: int, new_jobs: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    cursor.execute("""
        INSERT INTO scrape_history (timestamp, keywords, location, jobs_found, new_jobs)
        VALUES (?, ?, ?, ?, ?)
    """, (now, keywords, location, found, new_jobs))
    conn.commit()
    conn.close()

# Auto-initialize database on import
init_db()

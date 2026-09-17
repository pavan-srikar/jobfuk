import sys
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.database import init_db, upsert_job, get_jobs, get_stats, get_job_by_id
from app.resume.structure import get_active_profile, update_active_profile
from app.matcher.scoring import score_job
from app.matcher.analyzer import analyze_job_description

def test_all():
    print("1. Testing Database & Schema Initialization...")
    init_db()
    stats = get_stats()
    print(f"   Database initialized. Current jobs count: {stats['total']}")

    print("\n2. Testing Resume Profile Loading & Updating...")
    profile = get_active_profile()
    print(f"   Active candidate: {profile.candidate_name}")
    print(f"   Years exp: {profile.years_experience}, Skills: {len(profile.skills)}, Clouds: {profile.cloud_platforms}")
    assert "Azure" in profile.skills
    assert "Kubernetes" in profile.skills

    print("\n3. Testing Job Ingestion & Upsert...")
    mock_jobs = [
        {
            "linkedin_id": "test_azure_001",
            "title": "Junior Azure Cloud Engineer",
            "company": "Microsoft Partners",
            "location": "Hyderabad, India",
            "url": "https://linkedin.com/jobs/view/test_azure_001",
            "posted_at": "3 hours ago",
            "employment_type": "Full-time",
            "experience_level": "Entry level",
            "work_mode": "Hybrid",
            "salary": "₹8,00,000 - ₹12,00,000",
            "description": "We are seeking an Azure Cloud Engineer with 1+ years experience in Microsoft Azure, Kubernetes, Terraform, Docker, Linux, and CI/CD pipelines."
        },
        {
            "linkedin_id": "test_java_002",
            "title": "Senior Backend Java Engineer",
            "company": "Enterprise Bank",
            "location": "Bengaluru, India",
            "url": "https://linkedin.com/jobs/view/test_java_002",
            "posted_at": "1 day ago",
            "employment_type": "Full-time",
            "experience_level": "Senior",
            "work_mode": "On-site",
            "salary": "₹25,00,000",
            "description": "Required 5+ years of Java, Spring Boot, Microservices, Kafka, PostgreSQL. Nice to have: AWS, Docker."
        },
        {
            "linkedin_id": "test_devops_003",
            "title": "DevOps Architect",
            "company": "ScaleOps",
            "location": "Remote",
            "url": "https://linkedin.com/jobs/view/test_devops_003",
            "posted_at": "5 hours ago",
            "employment_type": "Full-time",
            "experience_level": "Mid-Senior",
            "work_mode": "Remote",
            "salary": "Competitive",
            "description": "Must have 4+ years hands-on experience in AWS, Kubernetes, Terraform, Prometheus, Grafana, CI/CD, Python."
        },
        {
            "linkedin_id": "test_reposted_004",
            "title": "Cloud Operations Specialist",
            "company": "TechCorp",
            "location": "Noida, India",
            "url": "https://linkedin.com/jobs/view/test_reposted_004",
            "posted_at": "Reposted 18 hours ago",
            "employment_type": "Full-time",
            "experience_level": "Entry level",
            "work_mode": "On-site",
            "salary": "Competitive",
            "description": "We are seeking a Cloud Ops engineer with Azure and Linux experience."
        }
    ]

    for j in mock_jobs:
        job_id, is_new = upsert_job(j)
        scored = score_job(j, profile)
        from app.database import update_job_scores
        update_job_scores(
            job_id=job_id,
            ats_score=scored["ats_score"],
            fit_score=scored["fit_score"],
            priority=scored["priority"],
            matched_skills=scored["matched_skills"],
            missing_skills=scored["missing_skills"],
            hard_req_concerns=scored["hard_req_concerns"],
            score_breakdown=scored["score_breakdown"],
            ai_analysis=scored["ai_analysis"]
        )

    print("\n4. Testing Scoring Logic & Priority Rankings...")
    res = get_jobs(sort_by="priority_desc", max_exp=None, limit=500)
    jobs = res["jobs"]
    for j in jobs:
        print(f"\n   Job: {j['title']} @ {j['company']}")
        print(f"   -> ATS Score: {j['ats_score']}% | FIT Score: {j['fit_score']}% | PRIORITY: {j['priority']}")
        print(f"   -> Reposted: {j.get('is_reposted')}")
        print(f"   -> Matched: {j['matched_skills']}")
        print(f"   -> Missing: {j['missing_skills']}")
        print(f"   -> Concerns: {j['hard_req_concerns']}")

    # Validation asserts
    job_map = {j["linkedin_id"]: j for j in jobs}
    azure_job = job_map["test_azure_001"]
    java_job = job_map["test_java_002"]
    devops_job = job_map["test_devops_003"]
    repost_job = job_map["test_reposted_004"]

    assert repost_job["is_reposted"] == 1, f"Expected repost_job is_reposted=1, got {repost_job.get('is_reposted')}"

    # Azure Cloud Engineer should score highest in ATS and FIT
    assert azure_job["priority"] == "HIGH", f"Expected HIGH priority, got {azure_job['priority']}"
    assert azure_job["ats_score"] > 85, f"Expected ATS > 85, got {azure_job['ats_score']}"
    assert azure_job["fit_score"] > 85, f"Expected FIT > 85, got {azure_job['fit_score']}"

    # Java Backend job should have low FIT
    assert java_job["fit_score"] < 50, f"Expected Java job FIT < 50, got {java_job['fit_score']}"

    # DevOps Architect (asking for 4+ yrs) should trigger hard requirement penalty
    assert any("4+ years" in c for c in devops_job["hard_req_concerns"]), "Expected 4+ years concern flag"
    assert devops_job["score_breakdown"]["penalties"]["total"] > 0, "Expected penalty applied"

    print("\n5. Testing Filter & Query Functions...")
    high_prio = get_jobs(priority="HIGH", max_exp=3.0)
    assert high_prio["total"] >= 1, "Expected at least 1 high priority job"
    
    # Verify strict experience cap filters out 4+ yr jobs
    capped_jobs = get_jobs(max_exp=3.0)
    for j in capped_jobs["jobs"]:
        assert j["required_experience"] is None or j["required_experience"] <= 3.0, f"Found job exceeding cap: {j['title']}"
        assert "lead" not in j["title"].lower() and "architect" not in j["title"].lower(), f"Senior title slipped through: {j['title']}"

    remote_jobs = get_jobs(work_mode="remote", max_exp=None)
    assert remote_jobs["total"] >= 1, "Expected remote job filter to work"

    print("\n6. Testing Multi-City Duplicate Job Merging & Deduplication...")
    # Attempt to upsert the same role at same company with a new linkedin_id and different city
    duplicate_posting = {
        "linkedin_id": "test_azure_duplicate_999",
        "title": "Junior Azure Cloud Engineer",
        "company": "Microsoft Partners",
        "location": "Bengaluru, Karnataka, India",
        "url": "https://linkedin.com/jobs/view/test_azure_duplicate_999",
        "posted_at": "1 hour ago",
        "description": "We are seeking an Azure Cloud Engineer with 1+ years experience in Microsoft Azure and Kubernetes."
    }
    merged_id, is_new = upsert_job(duplicate_posting)
    assert is_new is False, f"Expected duplicate job to be merged (is_new=False), got {is_new}"
    assert merged_id == azure_job["id"], f"Expected merged_id to match original job #{azure_job['id']}, got #{merged_id}"

    # Verify location was merged
    updated_azure = get_job_by_id(azure_job["id"])
    assert "Bengaluru" in updated_azure["location"], f"Expected merged location to contain Bengaluru, got: {updated_azure['location']}"
    print(f"   Successfully merged duplicate posting into #{azure_job['id']} with location: {updated_azure['location']}")

    print("\n✅ All automated verification tests passed with 100% success!")

if __name__ == "__main__":
    test_all()

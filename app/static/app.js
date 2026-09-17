// Job Radar UI Application Logic

const state = {
  page: 1,
  limit: 25,
  total: 0,
  filters: {
    keyword: "",
    priority: "ALL",
    minAts: 0,
    minFit: 0,
    maxExp: "3",
    workMode: "all",
    experienceLevel: "all",
    sortBy: "priority_desc",
    status: "new"
  },
  activeProfile: null,
  scrapePollingInterval: null,
  activeModalJobId: null
};

// DOM Elements
const elements = {
  jobsContainer: document.getElementById("jobs-container"),
  visibleCount: document.getElementById("visible-count"),
  statTotalJobs: document.querySelector("#stat-total-jobs .stat-num"),
  statUniqueJobs: document.querySelector("#stat-unique-jobs .stat-num"),
  statHighPriority: document.querySelector("#stat-high-priority .stat-num"),
  statAvgAts: document.querySelector("#stat-avg-ats .stat-num"),
  ollamaStatusPill: document.getElementById("ollama-status-pill"),
  ollamaStatusText: document.getElementById("ollama-status-text"),
  
  // Profile Chip
  profileChip: document.getElementById("profile-chip"),
  chipCandidateName: document.getElementById("chip-candidate-name"),
  chipCandidateExp: document.getElementById("chip-candidate-exp"),

  // Scraper Banner
  scraperBanner: document.getElementById("scraper-banner"),
  scraperBannerTitle: document.getElementById("scraper-banner-title"),
  scraperBannerSub: document.getElementById("scraper-banner-sub"),

  // Filters
  filterKeyword: document.getElementById("filter-keyword"),
  filterMinAts: document.getElementById("filter-min-ats"),
  valMinAts: document.getElementById("val-min-ats"),
  filterMinFit: document.getElementById("filter-min-fit"),
  valMinFit: document.getElementById("val-min-fit"),
  filterMaxExp: document.getElementById("filter-max-exp"),
  filterWorkMode: document.getElementById("filter-work-mode"),
  filterExperience: document.getElementById("filter-experience"),
  filterSortBy: document.getElementById("filter-sort-by"),
  filterStatus: document.getElementById("filter-status"),
  btnResetFilters: document.getElementById("btn-reset-filters"),

  // Modals
  scrapeModal: document.getElementById("scrape-modal"),
  btnOpenScrapeModal: document.getElementById("btn-open-scrape-modal"),
  btnCloseScrapeModal: document.getElementById("btn-close-scrape-modal"),
  btnCancelScrape: document.getElementById("btn-cancel-scrape"),
  btnStartScrape: document.getElementById("btn-start-scrape"),
  scrapeKeywords: document.getElementById("scrape-keywords"),
  scrapeLocation: document.getElementById("scrape-location"),
  scrapePosted: document.getElementById("scrape-posted"),
  scrapeWorktype: document.getElementById("scrape-worktype"),
  scrapePages: document.getElementById("scrape-pages"),
  scrapeEngine: document.getElementById("scrape-engine"),
  scrapeModalStatusBox: document.getElementById("scrape-modal-status-box"),
  scrapeModalStatusText: document.getElementById("scrape-modal-status-text"),

  resumeModal: document.getElementById("resume-modal"),
  btnOpenResumeModal: document.getElementById("btn-open-resume-modal"),
  btnCloseResumeModal: document.getElementById("btn-close-resume-modal"),
  btnCancelResume: document.getElementById("btn-cancel-resume"),
  btnSaveProfile: document.getElementById("btn-save-profile"),
  btnRescoreAll: document.getElementById("btn-rescore-all"),
  resumeUploadZone: document.getElementById("resume-upload-zone"),
  resumeFileInput: document.getElementById("resume-file-input"),
  uploadPrompt: document.getElementById("upload-prompt"),
  uploadLoading: document.getElementById("upload-loading"),

  // Profile Form Fields
  profileName: document.getElementById("profile-name"),
  profileExperience: document.getElementById("profile-experience"),
  profileLocation: document.getElementById("profile-location"),
  profileClouds: document.getElementById("profile-clouds"),
  profileSkills: document.getElementById("profile-skills"),
  profileCerts: document.getElementById("profile-certs"),
  profileEducation: document.getElementById("profile-education"),
  profileSummary: document.getElementById("profile-summary"),

  // Job Details Modal
  jobDetailModal: document.getElementById("job-detail-modal"),
  btnCloseJobModal: document.getElementById("btn-close-job-modal"),
  modalPriorityBadge: document.getElementById("modal-priority-badge"),
  modalAtsBadge: document.getElementById("modal-ats-badge"),
  modalFitBadge: document.getElementById("modal-fit-badge"),
  modalJobTitle: document.getElementById("modal-job-title"),
  modalJobSubtitle: document.getElementById("modal-job-subtitle"),
  modalBreakdownGrid: document.getElementById("modal-breakdown-grid"),
  modalConcernsBox: document.getElementById("modal-concerns-box"),
  modalConcernsList: document.getElementById("modal-concerns-list"),
  modalAiSection: document.getElementById("modal-ai-section"),
  modalAiContent: document.getElementById("modal-ai-content"),
  modalJdContent: document.getElementById("modal-jd-content"),
  modalBtnLinkedin: document.getElementById("modal-btn-linkedin"),
  modalBtnSave: document.getElementById("modal-btn-save"),
  modalBtnApplied: document.getElementById("modal-btn-applied"),
  modalBtnRejected: document.getElementById("modal-btn-rejected"),
  modalBtnIgnore: document.getElementById("modal-btn-ignore"),

  // Pagination
  btnPrevPage: document.getElementById("btn-prev-page"),
  btnNextPage: document.getElementById("btn-next-page"),
  pageIndicator: document.getElementById("page-indicator")
};

// Initialize Application
async function init() {
  bindEventListeners();
  await loadProfile();
  await checkOllamaStatus();
  await loadStats();
  await loadJobs();
  pollScraperState(); // check if scraper was already running
}

function bindEventListeners() {
  // Filters
  let debounceTimeout;
  elements.filterKeyword.addEventListener("input", (e) => {
    clearTimeout(debounceTimeout);
    debounceTimeout = setTimeout(() => {
      state.filters.keyword = e.target.value.trim();
      state.page = 1;
      loadJobs();
    }, 300);
  });

  elements.filterMinAts.addEventListener("input", (e) => {
    state.filters.minAts = parseFloat(e.target.value);
    elements.valMinAts.textContent = `${state.filters.minAts}%`;
    state.page = 1;
    loadJobs();
  });

  elements.filterMinFit.addEventListener("input", (e) => {
    state.filters.minFit = parseFloat(e.target.value);
    elements.valMinFit.textContent = `${state.filters.minFit}%`;
    state.page = 1;
    loadJobs();
  });

  // Priority buttons
  document.querySelectorAll(".priority-group .btn-pill").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".priority-group .btn-pill").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      state.filters.priority = btn.dataset.priority;
      state.page = 1;
      loadJobs();
    });
  });

  elements.filterMaxExp.addEventListener("change", (e) => {
    state.filters.maxExp = e.target.value;
    state.page = 1;
    loadJobs();
  });

  elements.filterWorkMode.addEventListener("change", (e) => {
    state.filters.workMode = e.target.value;
    state.page = 1;
    loadJobs();
  });

  elements.filterExperience.addEventListener("change", (e) => {
    state.filters.experienceLevel = e.target.value;
    state.page = 1;
    loadJobs();
  });

  elements.filterSortBy.addEventListener("change", (e) => {
    state.filters.sortBy = e.target.value;
    state.page = 1;
    loadJobs();
  });

  elements.filterStatus.addEventListener("change", (e) => {
    state.filters.status = e.target.value;
    document.querySelectorAll("#feed-status-tabs .feed-tab").forEach(t => {
      t.classList.toggle("active", t.dataset.status === state.filters.status);
    });
    state.page = 1;
    loadJobs();
  });

  // Feed Status Navigation Tabs
  document.querySelectorAll("#feed-status-tabs .feed-tab").forEach(tab => {
    tab.addEventListener("click", () => {
      document.querySelectorAll("#feed-status-tabs .feed-tab").forEach(t => t.classList.remove("active"));
      tab.classList.add("active");
      state.filters.status = tab.dataset.status;
      if (elements.filterStatus) elements.filterStatus.value = tab.dataset.status;
      state.page = 1;
      loadJobs();
    });
  });

  elements.btnResetFilters.addEventListener("click", () => {
    elements.filterKeyword.value = "";
    elements.filterMinAts.value = 0;
    elements.valMinAts.textContent = "0%";
    elements.filterMinFit.value = 0;
    elements.valMinFit.textContent = "0%";
    elements.filterMaxExp.value = "3";
    elements.filterWorkMode.value = "all";
    elements.filterExperience.value = "all";
    elements.filterSortBy.value = "priority_desc";
    elements.filterStatus.value = "new";

    document.querySelectorAll("#feed-status-tabs .feed-tab").forEach(t => {
      t.classList.toggle("active", t.dataset.status === "new");
    });

    document.querySelectorAll(".priority-group .btn-pill").forEach(b => b.classList.remove("active"));
    document.querySelector(".priority-group .btn-pill[data-priority='ALL']").classList.add("active");

    state.filters = {
      keyword: "",
      priority: "ALL",
      minAts: 0,
      minFit: 0,
      maxExp: "3",
      workMode: "all",
      experienceLevel: "all",
      sortBy: "priority_desc",
      status: "new"
    };
    state.page = 1;
    loadJobs();
  });

  // Modals Open/Close
  elements.btnOpenScrapeModal.addEventListener("click", () => elements.scrapeModal.classList.remove("hidden"));
  elements.btnCloseScrapeModal.addEventListener("click", () => elements.scrapeModal.classList.add("hidden"));
  elements.btnCancelScrape.addEventListener("click", () => elements.scrapeModal.classList.add("hidden"));

  elements.btnOpenResumeModal.addEventListener("click", () => {
    populateResumeForm();
    elements.resumeModal.classList.remove("hidden");
  });
  elements.profileChip.addEventListener("click", () => {
    populateResumeForm();
    elements.resumeModal.classList.remove("hidden");
  });
  elements.btnCloseResumeModal.addEventListener("click", () => elements.resumeModal.classList.add("hidden"));
  elements.btnCancelResume.addEventListener("click", () => elements.resumeModal.classList.add("hidden"));

  elements.btnCloseJobModal.addEventListener("click", () => elements.jobDetailModal.classList.add("hidden"));

  // Scraper Multi-Role Presets
  function updateSelectedRolesHint() {
    const activeBtns = document.querySelectorAll("#multi-role-presets .btn-preset.active");
    const roles = Array.from(activeBtns).map(b => b.dataset.role);
    const hintEl = document.getElementById("selected-roles-hint");
    if (hintEl) {
      if (roles.length === 0) {
        hintEl.textContent = "No presets selected (will use custom keywords below)";
        hintEl.style.color = "var(--text-muted)";
      } else {
        hintEl.textContent = `Selected: ${roles.join(", ")} (${roles.length} role${roles.length > 1 ? 's' : ''})`;
        hintEl.style.color = "var(--accent-cyan)";
      }
    }
  }

  document.querySelectorAll("#multi-role-presets .btn-preset").forEach(btn => {
    btn.addEventListener("click", () => {
      btn.classList.toggle("active");
      updateSelectedRolesHint();
    });
  });

  const btnSelectAll = document.getElementById("btn-select-all-presets");
  if (btnSelectAll) {
    btnSelectAll.addEventListener("click", () => {
      document.querySelectorAll("#multi-role-presets .btn-preset").forEach(b => b.classList.add("active"));
      updateSelectedRolesHint();
    });
  }

  const btnClearAll = document.getElementById("btn-clear-presets");
  if (btnClearAll) {
    btnClearAll.addEventListener("click", () => {
      document.querySelectorAll("#multi-role-presets .btn-preset").forEach(b => b.classList.remove("active"));
      updateSelectedRolesHint();
    });
  }

  elements.btnStartScrape.addEventListener("click", startScraper);
  elements.btnRescoreAll.addEventListener("click", triggerRescore);
  elements.btnSaveProfile.addEventListener("click", saveProfileFromForm);

  // Resume File Upload
  elements.resumeUploadZone.addEventListener("click", () => elements.resumeFileInput.click());
  elements.resumeFileInput.addEventListener("change", handleResumeFileUpload);

  // Pagination
  elements.btnPrevPage.addEventListener("click", () => {
    if (state.page > 1) {
      state.page--;
      loadJobs();
    }
  });

  elements.btnNextPage.addEventListener("click", () => {
    if (state.page * state.limit < state.total) {
      state.page++;
      loadJobs();
    }
  });

  // Modal Status Actions
  elements.modalBtnSave?.addEventListener("click", () => updateJobStatus(state.activeModalJobId, "saved"));
  elements.modalBtnApplied?.addEventListener("click", () => updateJobStatus(state.activeModalJobId, "applied"));
  elements.modalBtnRejected?.addEventListener("click", () => updateJobStatus(state.activeModalJobId, "rejected"));
  elements.modalBtnIgnore?.addEventListener("click", () => updateJobStatus(state.activeModalJobId, "ignored"));
}

// API Calls
async function loadStats() {
  try {
    const res = await fetch("/api/stats");
    const data = await res.json();
    elements.statTotalJobs.textContent = data.total;
    elements.statUniqueJobs.textContent = data.unique;
    elements.statHighPriority.textContent = data.high_priority;
    elements.statAvgAts.textContent = `${data.avg_ats}%`;

    // Update Feed Tab Badges
    const elNew = document.getElementById("count-tab-new");
    if (elNew) elNew.textContent = data.count_new ?? 0;
    const elSaved = document.getElementById("count-tab-saved");
    if (elSaved) elSaved.textContent = data.count_saved ?? 0;
    const elApplied = document.getElementById("count-tab-applied");
    if (elApplied) elApplied.textContent = data.count_applied ?? 0;
    const elRejected = document.getElementById("count-tab-rejected");
    if (elRejected) elRejected.textContent = data.count_rejected ?? 0;
    const elIgnored = document.getElementById("count-tab-ignored");
    if (elIgnored) elIgnored.textContent = data.count_ignored ?? 0;
  } catch (err) {
    console.error("Error loading stats:", err);
  }
}

async function checkOllamaStatus() {
  try {
    const res = await fetch("/api/ollama/status");
    const data = await res.json();
    const dot = elements.ollamaStatusPill.querySelector(".status-dot");
    if (data.connected) {
      dot.className = "status-dot online";
      if (data.target_model_installed) {
        elements.ollamaStatusText.textContent = `Ollama: ${data.target_model}`;
        elements.ollamaStatusPill.title = `Connected to Ollama with ${data.target_model}`;
      } else {
        elements.ollamaStatusText.textContent = "Ollama: Connected (Model missing)";
        elements.ollamaStatusPill.title = `Run 'ollama pull ${data.target_model}'`;
      }
    } else {
      dot.className = "status-dot offline";
      elements.ollamaStatusText.textContent = "Ollama: Standby (Rules active)";
      elements.ollamaStatusPill.title = "Local Ollama server is not running. Hybrid scoring is running in deterministic mode.";
    }
  } catch (err) {
    elements.ollamaStatusText.textContent = "Ollama: Standby";
  }
}

async function loadProfile() {
  try {
    const res = await fetch("/api/profile");
    const profile = await res.json();
    state.activeProfile = profile;
    elements.chipCandidateName.textContent = profile.candidate_name || "Active Resume";
    elements.chipCandidateExp.textContent = `${profile.years_experience} yrs`;
  } catch (err) {
    console.error("Error loading profile:", err);
  }
}

function populateResumeForm() {
  if (!state.activeProfile) return;
  const p = state.activeProfile;
  elements.profileName.value = p.candidate_name || "";
  elements.profileExperience.value = p.years_experience || 1.0;
  elements.profileLocation.value = p.location || "India";
  elements.profileClouds.value = (p.cloud_platforms || []).join(", ");
  elements.profileSkills.value = (p.skills || []).join(", ");
  elements.profileCerts.value = (p.certifications || []).join(", ");
  elements.profileEducation.value = (p.education || []).join(", ");
  elements.profileSummary.value = p.summary || "";
}

async function saveProfileFromForm() {
  const updated = {
    candidate_name: elements.profileName.value.trim(),
    years_experience: parseFloat(elements.profileExperience.value) || 1.0,
    location: elements.profileLocation.value.trim(),
    cloud_platforms: elements.profileClouds.value.split(",").map(s => s.trim()).filter(Boolean),
    skills: elements.profileSkills.value.split(",").map(s => s.trim()).filter(Boolean),
    certifications: elements.profileCerts.value.split(",").map(s => s.trim()).filter(Boolean),
    education: elements.profileEducation.value.split(",").map(s => s.trim()).filter(Boolean),
    summary: elements.profileSummary.value.trim()
  };

  elements.btnSaveProfile.disabled = true;
  elements.btnSaveProfile.innerHTML = `<span class="banner-spinner small"></span> Saving & Rescoring...`;

  try {
    const res = await fetch("/api/profile", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(updated)
    });
    if (res.ok) {
      await loadProfile();
      await loadStats();
      await loadJobs();
      elements.resumeModal.classList.add("hidden");
    }
  } catch (err) {
    alert("Failed to save profile: " + err);
  } finally {
    elements.btnSaveProfile.disabled = false;
    elements.btnSaveProfile.innerHTML = `<span class="btn-icon">💾</span> Save &amp; Re-Score All Jobs`;
  }
}

async function handleResumeFileUpload(e) {
  const file = e.target.files[0];
  if (!file) return;

  const formData = new FormData();
  formData.append("file", file);

  elements.uploadPrompt.classList.add("hidden");
  elements.uploadLoading.classList.remove("hidden");

  try {
    const res = await fetch("/api/profile/upload", {
      method: "POST",
      body: formData
    });
    if (res.ok) {
      const data = await res.json();
      state.activeProfile = data.profile;
      populateResumeForm();
      await loadProfile();
      await loadStats();
      await loadJobs();
      alert(`Resume parsed successfully! Extracted ${data.profile.skills?.length || 0} skills.`);
    } else {
      const err = await res.json();
      alert("Error: " + (err.detail || "Failed to parse file"));
    }
  } catch (err) {
    alert("Upload failed: " + err);
  } finally {
    elements.uploadPrompt.classList.remove("hidden");
    elements.uploadLoading.classList.add("hidden");
    elements.resumeFileInput.value = "";
  }
}

async function triggerRescore() {
  elements.btnRescoreAll.innerHTML = "⏳";
  try {
    await fetch("/api/rescore", { method: "POST" });
    setTimeout(async () => {
      await loadStats();
      await loadJobs();
      elements.btnRescoreAll.innerHTML = "🔄";
    }, 1500);
  } catch (err) {
    elements.btnRescoreAll.innerHTML = "🔄";
  }
}

// Scraper Logic
async function startScraper() {
  const activeBtns = document.querySelectorAll("#multi-role-presets .btn-preset.active");
  const selectedRoles = Array.from(activeBtns).map(b => b.dataset.role);
  const customKeyword = elements.scrapeKeywords.value.trim();

  const req = {
    roles: selectedRoles.length > 0 ? selectedRoles : (customKeyword ? [customKeyword] : null),
    keywords: customKeyword || (selectedRoles.length > 0 ? selectedRoles.join(", ") : "Cloud Engineer"),
    location: elements.scrapeLocation.value.trim() || "India",
    posted_within: elements.scrapePosted.value,
    work_type: elements.scrapeWorktype.value,
    max_pages: parseInt(elements.scrapePages.value, 10) || 5,
    engine: elements.scrapeEngine ? elements.scrapeEngine.value : "guest_api"
  };

  elements.btnStartScrape.disabled = true;
  elements.scrapeModalStatusBox.classList.remove("hidden");
  elements.scrapeModalStatusText.textContent = "Starting scraper...";

  try {
    const res = await fetch("/api/scrape", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req)
    });

    if (res.ok) {
      elements.scrapeModal.classList.add("hidden");
      elements.scraperBanner.classList.remove("hidden");
      pollScraperState();
    } else if (res.status === 409) {
      alert("A scraper run is already in progress!");
    }
  } catch (err) {
    alert("Could not trigger scraper: " + err);
  } finally {
    elements.btnStartScrape.disabled = false;
    elements.scrapeModalStatusBox.classList.add("hidden");
  }
}

function pollScraperState() {
  if (state.scrapePollingInterval) clearInterval(state.scrapePollingInterval);

  state.scrapePollingInterval = setInterval(async () => {
    try {
      const res = await fetch("/api/scrape/status");
      const data = await res.json();

      if (data.is_running) {
        elements.scraperBanner.classList.remove("hidden");
        elements.scraperBannerTitle.textContent = "Scraping in progress...";
        elements.scraperBannerSub.textContent = data.status;
      } else {
        clearInterval(state.scrapePollingInterval);
        state.scrapePollingInterval = null;
        elements.scraperBanner.classList.add("hidden");
        await loadStats();
        await loadJobs();
      }
    } catch (err) {
      console.error("Error polling scraper state:", err);
    }
  }, 1500);
}

// Jobs Loading & Rendering
async function loadJobs() {
  const offset = (state.page - 1) * state.limit;
  const params = new URLSearchParams({
    limit: state.limit,
    offset: offset,
    sort_by: state.filters.sortBy
  });

  if (state.filters.keyword) params.append("keyword", state.filters.keyword);
  if (state.filters.minAts > 0) params.append("min_ats", state.filters.minAts);
  if (state.filters.minFit > 0) params.append("min_fit", state.filters.minFit);
  if (state.filters.maxExp !== "all") {
    params.append("max_exp", state.filters.maxExp);
  } else {
    params.append("max_exp", "0");
  }
  if (state.filters.priority !== "ALL") params.append("priority", state.filters.priority);
  if (state.filters.workMode !== "all") params.append("work_mode", state.filters.workMode);
  if (state.filters.experienceLevel !== "all") params.append("experience_level", state.filters.experienceLevel);
  if (state.filters.status !== "all") params.append("status", state.filters.status);

  try {
    elements.jobsContainer.innerHTML = `<div class="banner-spinner" style="margin: 40px auto;"></div>`;
    const res = await fetch(`/api/jobs?${params.toString()}`);
    const data = await res.json();
    
    state.total = data.total;
    elements.visibleCount.textContent = data.total;

    renderJobCards(data.jobs, offset);
    renderPagination();
  } catch (err) {
    elements.jobsContainer.innerHTML = `<div class="empty-state"><p>Error loading jobs: ${err}</p></div>`;
  }
}

function renderProgressBar(percentage) {
  const totalBlocks = 20;
  const filledBlocks = Math.round((percentage / 100) * totalBlocks);
  const emptyBlocks = totalBlocks - filledBlocks;
  return "█".repeat(filledBlocks) + "░".repeat(emptyBlocks);
}

function renderJobCards(jobs, offset) {
  if (!jobs || jobs.length === 0) {
    elements.jobsContainer.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">📡</div>
        <h3 class="empty-title">No matching jobs on radar</h3>
        <p class="empty-desc">
          Try adjusting your search filters or click <strong>Run Scraper</strong> above to fetch fresh job postings directly from LinkedIn.
        </p>
        <button class="btn btn-primary" onclick="document.getElementById('btn-open-scrape-modal').click()">
          <span class="btn-icon">⚡</span> Run Scraper Now
        </button>
      </div>
    `;
    return;
  }

  const cardsHtml = jobs.map((job, index) => {
    const rankNum = offset + index + 1;
    let rankBadge = `#${rankNum}`;
    if (rankNum === 1) rankBadge = `🥇 1`;
    else if (rankNum === 2) rankBadge = `🥈 2`;
    else if (rankNum === 3) rankBadge = `🥉 3`;

    const ats = Math.round(job.ats_score || 0);
    const fit = Math.round(job.fit_score || 0);
    const priority = (job.priority || "MEDIUM").toUpperCase();

    // ATS badge color
    let atsColorClass = "red";
    if (ats >= 80) atsColorClass = "green";
    else if (ats >= 60) atsColorClass = "amber";

    // Priority badge class
    let prioClass = "low";
    let prioIcon = "";
    if (priority === "HIGH") {
      prioClass = "high";
      prioIcon = "🔥 ";
    } else if (priority === "MEDIUM") {
      prioClass = "med";
      prioIcon = "⚡ ";
    }

    const matchedPills = (job.matched_skills || []).slice(0, 10).map(s => `
      <span class="skill-pill matched">✓ ${escapeHtml(s)}</span>
    `).join("");

    const missingPills = (job.missing_skills || []).slice(0, 8).map(s => `
      <span class="skill-pill missing">⚠ ${escapeHtml(s)}</span>
    `).join("");

    const concernsList = (job.hard_req_concerns || []).map(c => `
      <div class="concern-item">${escapeHtml(c)}</div>
    `).join("");

    const b = job.score_breakdown || {};

    return `
      <div class="job-card ${prioClass}-priority" id="job-card-${job.id}">
        <!-- Top Row -->
        <div class="card-top-row">
          <div class="card-rank-badge">
            ${rankBadge}
          </div>
          <div class="card-scores-row">
            <span class="priority-badge ${prioClass}">${prioIcon}${priority} PRIORITY</span>
            <span class="ats-badge ${atsColorClass}">${ats}% ATS</span>
            <span class="fit-badge">${fit}% FIT</span>
          </div>
        </div>

        <!-- Title & Company -->
        <div>
          <h2 class="card-title">${escapeHtml(job.title)}</h2>
          <div class="card-company-line">
            <strong>${escapeHtml(job.company)}</strong>
            <span class="meta-bullet">•</span>
            <span>📍 ${escapeHtml(job.location || "Remote / Unspecified")}</span>
            <span class="meta-bullet">•</span>
            <span class="meta-pill">${escapeHtml(job.work_mode || "On-site")}</span>
            ${job.experience_level ? `<span class="meta-pill">${escapeHtml(job.experience_level)}</span>` : ""}
            ${job.salary ? `<span class="meta-pill highlight">${escapeHtml(job.salary)}</span>` : ""}
            ${job.posted_at ? `<span class="meta-bullet">•</span><span style="color: var(--text-muted);">${escapeHtml(job.posted_at)}</span>` : ""}
            ${(job.is_reposted || (job.posted_at && job.posted_at.toLowerCase().includes('repost'))) ? `<span class="meta-pill reposted-badge">🚨 Reposted</span>` : ""}
          </div>
        </div>

        <!-- Visual Progress Bar -->
        <div class="visual-progress-wrap">
          <span class="ascii-progress">${renderProgressBar(ats)}</span>
          <span>${ats}% Match</span>
        </div>

        <!-- Skills Section -->
        <div class="card-skills-section">
          ${matchedPills ? `
            <div class="skills-pills-row">
              <span class="skill-category-label">Matched:</span>
              ${matchedPills}
            </div>
          ` : ""}
          ${missingPills ? `
            <div class="skills-pills-row">
              <span class="skill-category-label">Missing:</span>
              ${missingPills}
            </div>
          ` : ""}
        </div>

        <!-- Hard Req Concerns -->
        ${concernsList ? `
          <div class="card-concerns-row">
            ${concernsList}
          </div>
        ` : ""}

        <!-- Collapsible Score Breakdown -->
        <div class="score-breakdown-details">
          <div class="breakdown-summary-toggle" onclick="toggleCardBreakdown(${job.id})">
            <span>📊 Why this score? (Score Breakdown)</span>
            <span id="breakdown-arrow-${job.id}">▾</span>
          </div>
          <div class="breakdown-table-wrap hidden" id="breakdown-table-${job.id}">
            <table class="breakdown-table">
              <tbody>
                <tr><td>Technical Skills</td><td style="text-align: right;">${b.skills?.score || 0} / 35</td></tr>
                <tr><td>Experience Match</td><td style="text-align: right;">${b.experience?.score || 0} / 20</td></tr>
                <tr><td>Responsibilities / Role</td><td style="text-align: right;">${b.responsibilities?.score || 0} / 15</td></tr>
                <tr><td>Cloud / Platform Fit</td><td style="text-align: right;">${b.cloud_platform?.score || 0} / 10</td></tr>
                <tr><td>Education</td><td style="text-align: right;">${b.education?.score || 0} / 5</td></tr>
                <tr><td>Certifications</td><td style="text-align: right;">${b.certifications?.score || 0} / 5</td></tr>
                <tr><td>ATS Keywords</td><td style="text-align: right;">${b.ats_keywords?.score || 0} / 5</td></tr>
                <tr><td>Location & Work Mode</td><td style="text-align: right;">${b.location?.score || 0} / 5</td></tr>
                ${b.penalties?.total > 0 ? `
                  <tr style="color: var(--accent-rose);">
                    <td>Hard Requirement Penalty</td>
                    <td style="text-align: right;">-${b.penalties.total}</td>
                  </tr>
                ` : ""}
                <tr class="total-row">
                  <td>TOTAL ATS SCORE</td>
                  <td style="text-align: right;">${job.ats_score} / 100</td>
                </tr>
                <tr class="total-row" style="color: var(--accent-cyan);">
                  <td>OPPORTUNITY FIT SCORE</td>
                  <td style="text-align: right;">${job.fit_score} / 100</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <!-- Actions Row -->
        <div class="card-actions-row">
          <div class="status-button-group">
            ${job.status === 'ignored' || job.status === 'rejected' ? `
              <button class="btn btn-sm btn-restore" onclick="updateJobStatus(${job.id}, 'new')" title="Restore to active Radar feed">
                ↩ Restore to Radar
              </button>
            ` : ""}
            <button class="btn btn-sm btn-outline ${job.status === 'saved' ? 'active' : ''}" onclick="updateJobStatus(${job.id}, '${job.status === 'saved' ? 'new' : 'saved'}')">
              ⭐ ${job.status === 'saved' ? 'Saved' : 'Save'}
            </button>
            ${job.status !== 'applied' ? `
              <button class="btn btn-sm btn-applied" onclick="updateJobStatus(${job.id}, 'applied')" title="Mark as Applied">
                ✓ Applied
              </button>
            ` : `
              <span class="meta-pill" style="color: #10b981; border-color: #10b981; font-weight: 700;">✓ Applied</span>
              <button class="btn btn-sm btn-rejected" onclick="updateJobStatus(${job.id}, 'rejected')" title="Mark as Rejected">
                🚫 Rejected
              </button>
            `}
            ${job.status === 'rejected' ? `
              <span class="meta-pill" style="color: #f87171; border-color: #ef4444; font-weight: 700;">🚫 Rejected</span>
            ` : ""}
            ${job.status !== 'ignored' ? `
              <button class="btn btn-sm btn-dismiss" onclick="updateJobStatus(${job.id}, 'ignored')" title="Dismiss / Remove from Radar">
                ✕ Dismiss
              </button>
            ` : `
              <span class="meta-pill" style="color: #f43f5e; border-color: #f43f5e; font-weight: 700;">✕ Dismissed</span>
            `}
          </div>
          <div style="display: flex; gap: 8px;">
            <button class="btn btn-secondary btn-sm" onclick="openJobDetailModal(${job.id})">
              🔍 View JD & AI Details
            </button>
            <a href="${job.url}" target="_blank" rel="noopener noreferrer" class="btn btn-primary btn-sm">
              Open on LinkedIn ↗
            </a>
          </div>
        </div>
      </div>
    `;
  }).join("");

  elements.jobsContainer.innerHTML = cardsHtml;
}

window.toggleCardBreakdown = function(jobId) {
  const table = document.getElementById(`breakdown-table-${jobId}`);
  const arrow = document.getElementById(`breakdown-arrow-${jobId}`);
  if (table) {
    const isHidden = table.classList.contains("hidden");
    if (isHidden) {
      table.classList.remove("hidden");
      arrow.textContent = "▴";
    } else {
      table.classList.add("hidden");
      arrow.textContent = "▾";
    }
  }
};

window.updateJobStatus = async function(jobId, status) {
  try {
    const cardEl = document.getElementById(`job-card-${jobId}`);
    const isRemovingFromCurrentFeed = (state.filters.status === "new" && (status === "applied" || status === "ignored" || status === "rejected" || status === "saved")) ||
                                     (state.filters.status === "saved" && status !== "saved") ||
                                     (state.filters.status === "applied" && status !== "applied") ||
                                     (state.filters.status === "rejected" && status !== "rejected") ||
                                     (state.filters.status === "ignored" && status !== "ignored");

    if (cardEl && isRemovingFromCurrentFeed) {
      cardEl.classList.add("dismissing");
    }

    const res = await fetch(`/api/jobs/${jobId}/status?status=${status}`, { method: "PATCH" });
    if (res.ok) {
      if (state.activeModalJobId === jobId) {
        elements.modalBtnSave?.classList.toggle("active", status === "saved");
        elements.modalBtnApplied?.classList.toggle("active", status === "applied");
        elements.modalBtnRejected?.classList.toggle("active", status === "rejected");
        elements.modalBtnRejected?.classList.toggle("hidden", status !== "applied" && status !== "rejected");
        elements.modalBtnIgnore?.classList.toggle("active", status === "ignored");
      }
      await loadStats();

      if (cardEl && isRemovingFromCurrentFeed) {
        setTimeout(() => {
          cardEl.remove();
          const remaining = document.querySelectorAll(".job-card").length;
          if (elements.visibleCount) elements.visibleCount.textContent = remaining;
          if (remaining === 0) {
            loadJobs();
          }
        }, 260);
      } else {
        loadJobs();
      }
    }
  } catch (err) {
    console.error("Error updating status:", err);
  }
};

window.openJobDetailModal = async function(jobId) {
  state.activeModalJobId = jobId;
  try {
    const res = await fetch(`/api/jobs/${jobId}`);
    const job = await res.json();

    const ats = Math.round(job.ats_score || 0);
    const fit = Math.round(job.fit_score || 0);
    const priority = (job.priority || "MEDIUM").toUpperCase();

    let prioClass = priority === "HIGH" ? "high" : (priority === "MEDIUM" ? "med" : "low");
    let atsClass = ats >= 80 ? "green" : (ats >= 60 ? "amber" : "red");

    elements.modalPriorityBadge.className = `priority-badge ${prioClass}`;
    elements.modalPriorityBadge.textContent = `${priority} PRIORITY`;

    elements.modalAtsBadge.className = `ats-badge ${atsClass}`;
    elements.modalAtsBadge.textContent = `${ats}% ATS MATCH`;

    elements.modalFitBadge.textContent = `${fit}% FIT SCORE`;

    elements.modalJobTitle.textContent = job.title;
    const isRep = job.is_reposted || (job.posted_at && job.posted_at.toLowerCase().includes('repost'));
    elements.modalJobSubtitle.textContent = `${job.company} • ${job.location || 'Location Unspecified'} • ${job.work_mode || 'On-site'} • ${job.experience_level || 'Experience Unspecified'}${isRep ? ' • 🚨 REPOSTED' : ''}`;
    elements.modalBtnLinkedin.href = job.url;

    // Status button states
    elements.modalBtnSave?.classList.toggle("active", job.status === "saved");
    elements.modalBtnApplied?.classList.toggle("active", job.status === "applied");
    elements.modalBtnRejected?.classList.toggle("active", job.status === "rejected");
    elements.modalBtnRejected?.classList.toggle("hidden", job.status !== "applied" && job.status !== "rejected");
    elements.modalBtnIgnore?.classList.toggle("active", job.status === "ignored");

    // Breakdown Grid
    const b = job.score_breakdown || {};
    elements.modalBreakdownGrid.innerHTML = `
      <div class="breakdown-card">
        <div class="b-label">Tech Skills</div>
        <div class="b-val">${b.skills?.score || 0}/35</div>
      </div>
      <div class="breakdown-card">
        <div class="b-label">Experience</div>
        <div class="b-val">${b.experience?.score || 0}/20</div>
      </div>
      <div class="breakdown-card">
        <div class="b-label">Role Alignment</div>
        <div class="b-val">${b.responsibilities?.score || 0}/15</div>
      </div>
      <div class="breakdown-card">
        <div class="b-label">Cloud Stack</div>
        <div class="b-val">${b.cloud_platform?.score || 0}/10</div>
      </div>
      <div class="breakdown-card">
        <div class="b-label">Education</div>
        <div class="b-val">${b.education?.score || 0}/5</div>
      </div>
      <div class="breakdown-card">
        <div class="b-label">Certifications</div>
        <div class="b-val">${b.certifications?.score || 0}/5</div>
      </div>
      <div class="breakdown-card">
        <div class="b-label">ATS Keywords</div>
        <div class="b-val">${b.ats_keywords?.score || 0}/5</div>
      </div>
      <div class="breakdown-card">
        <div class="b-label">Location Fit</div>
        <div class="b-val">${b.location?.score || 0}/5</div>
      </div>
    `;

    // Hard requirement concerns
    if (job.hard_req_concerns && job.hard_req_concerns.length > 0) {
      elements.modalConcernsBox.classList.remove("hidden");
      elements.modalConcernsList.innerHTML = job.hard_req_concerns.map(c => `<li>${escapeHtml(c)}</li>`).join("");
    } else {
      elements.modalConcernsBox.classList.add("hidden");
    }

    // AI Analysis (Ollama)
    if (job.ai_analysis && job.ai_analysis.trim()) {
      elements.modalAiSection.classList.remove("hidden");
      elements.modalAiContent.innerHTML = formatMarkdownText(job.ai_analysis);
    } else {
      elements.modalAiSection.classList.add("hidden");
    }

    // Job Description text
    elements.modalJdContent.textContent = job.description || "No description body available.";

    elements.jobDetailModal.classList.remove("hidden");
  } catch (err) {
    alert("Could not load job details: " + err);
  }
};

function renderPagination() {
  const totalPages = Math.ceil(state.total / state.limit) || 1;
  elements.pageIndicator.textContent = `Page ${state.page} of ${totalPages}`;
  elements.btnPrevPage.disabled = state.page <= 1;
  elements.btnNextPage.disabled = state.page >= totalPages;
}

function escapeHtml(str) {
  if (!str) return "";
  return str.replace(/[&<>"']/g, m => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#039;'
  })[m]);
}

function formatMarkdownText(text) {
  if (!text) return "";
  return text
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n\n/g, '<br><br>')
    .replace(/\n/g, '<br>');
}

// Kickoff
document.addEventListener("DOMContentLoaded", init);

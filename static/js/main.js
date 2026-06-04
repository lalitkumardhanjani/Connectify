// Tab Navigation Controller
const navItems = document.querySelectorAll('.nav-menu .nav-item');
const tabPanes = document.querySelectorAll('.main-content .tab-pane');

navItems.forEach(item => {
    item.addEventListener('click', () => {
        // Toggle Nav Items Active State
        navItems.forEach(i => i.classList.remove('active'));
        item.classList.add('active');

        // Toggle Tab Panes Display
        const targetTab = item.getAttribute('data-tab');
        tabPanes.forEach(pane => {
            pane.classList.remove('active');
            if (pane.id === `tab-${targetTab}`) {
                pane.classList.add('active');
            }
        });

        // Trigger loading data based on tab selected
        if (targetTab === 'db-scraper') {
            loadTableData('scraper');
        } else if (targetTab === 'db-referral') {
            loadTableData('referral');
        } else if (targetTab === 'dashboard') {
            loadStats();
            if (typeof loadDashboardAnalytics === 'function') loadDashboardAnalytics();
        }
    });
});

// ChartJS Configuration
let metricsChartInstance = null;
function updateChart(stats) {
    const ctx = document.getElementById('metricsChart').getContext('2d');
    
    if (metricsChartInstance) {
        metricsChartInstance.destroy();
    }

    metricsChartInstance = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['Emails Sent', 'Emails Pending', 'Done Referrals', 'Asked Referrals'],
            datasets: [{
                data: [
                    stats.emails_sent,
                    Math.max(0, stats.total_emails_scraped - stats.emails_sent),
                    stats.done_jobs_count,
                    Math.max(0, stats.total_jobs_scraped - stats.done_jobs_count)
                ],
                backgroundColor: [
                    '#00b0ff', // Cyan
                    'rgba(0, 176, 255, 0.15)', // Glass Cyan
                    '#2cb67d', // Teal
                    'rgba(44, 182, 125, 0.15)' // Glass Teal
                ],
                borderColor: [
                    '#00b0ff',
                    'rgba(255, 255, 255, 0.1)',
                    '#2cb67d',
                    'rgba(255, 255, 255, 0.1)'
                ],
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: {
                        color: '#9ea4c0',
                        font: {
                            family: 'Outfit',
                            size: 11
                        },
                        padding: 15
                    }
                }
            },
            cutout: '65%'
        }
    });
}

// Fetch stats and update Dashboard
async function loadStats() {
    try {
        const response = await fetch('/api/stats');
        const stats = await response.json();
        
        document.getElementById('stat-emails-scraped').innerText = stats.total_emails_scraped;
        document.getElementById('stat-emails-sent').innerText = stats.emails_sent;
        document.getElementById('stat-jobs-scraped').innerText = stats.total_jobs_scraped;
        document.getElementById('stat-referrals-sent').innerText = stats.referral_requests_sent;

        updateChart(stats);
    } catch (e) {
        console.error("Failed to load dashboard metrics:", e);
    }
}

// Global state for pipelines
let activeTaskId = null;
let logPollInterval = null;
let lastLogLength = 0;

// Poll task details & stdout logs
async function pollLogs() {
    if (!activeTaskId) return;

    try {
        const response = await fetch(`/api/task/${activeTaskId}/logs`);
        const data = await response.json();
        
        if (data.status === 'error') {
            stopPolling();
            return;
        }

        // Update logs console
        const consoleLogs = document.getElementById('console-logs');
        if (data.logs.length > lastLogLength) {
            const newLines = data.logs.slice(lastLogLength);
            newLines.forEach(line => {
                const div = document.createElement('div');
                div.className = 'log-line';
                
                // Color formatting logic
                if (line.includes('[ERROR]') || line.includes('Error starting') || line.includes('Fatal error') || line.includes('Traceback')) {
                    div.classList.add('error');
                } else if (line.includes('--- Launching') || line.includes('completed successfully')) {
                    div.classList.add('system');
                } else if (line.includes('- INFO -') || line.includes('Processing:') || line.includes('Searching for')) {
                    div.classList.add('info');
                }
                
                div.innerText = line;
                consoleLogs.appendChild(div);
            });
            lastLogLength = data.logs.length;
            consoleLogs.scrollTop = consoleLogs.scrollHeight;
        }

        // Highlight step numbers in sequence
        if (activeTaskId === 'referral_pipeline') {
            updateReferralPipelineSteps(data);
        } else if (activeTaskId === 'scraper_pipeline') {
            updateScraperPipelineSteps(data);
        }

        // Update badges
        const badge = document.getElementById(`badge-${activeTaskId.split('_')[0]}`);
        badge.innerText = data.status;
        badge.className = `status-badge status-${data.status}`;

        // Toggle action buttons based on state
        const pipelinePrefix = activeTaskId.split('_')[0];
        const runBtn = document.getElementById(`btn-run-${pipelinePrefix}`);
        const killBtn = document.getElementById(`btn-kill-${pipelinePrefix}`);
        
        if (data.status === 'running') {
            runBtn.classList.add('hidden');
            killBtn.classList.remove('hidden');
        } else {
            runBtn.classList.remove('hidden');
            killBtn.classList.add('hidden');
            stopPolling();
            loadStats(); // Reload stats after completion
            if (typeof loadDashboardAnalytics === 'function') loadDashboardAnalytics();
            
            // Clear scraper steps visual active/completed state on stop/finish
            if (activeTaskId === 'scraper_pipeline') {
                const steps = document.querySelectorAll('#card-scraper .p-step-seq');
                steps.forEach(el => el.classList.remove('active', 'completed'));
            }
        }

        // Show/Hide Stdin interactive overlay
        const stdinOverlay = document.getElementById('stdin-overlay');
        if (data.waiting_for_input) {
            stdinOverlay.classList.remove('hidden');
        } else {
            stdinOverlay.classList.add('hidden');
        }

    } catch (e) {
        console.error("Error polling logs:", e);
    }
}

function updateReferralPipelineSteps(taskData) {
    const steps = document.querySelectorAll('#card-referral .p-step-seq');
    steps.forEach(el => el.classList.remove('active', 'completed'));

    const activeStepName = taskData.current_step_name;
    const isSingle = taskData.is_single_step;

    if (!activeStepName) return;

    let activeStepIdx = 0;
    if (activeStepName.includes("linkedin_find_job.py")) activeStepIdx = 1;
    else if (activeStepName.includes("review_for_referral.py")) activeStepIdx = 2;
    else if (activeStepName.includes("shorten_urls.py")) activeStepIdx = 3;
    else if (activeStepName.includes("linkdin_connect.py")) activeStepIdx = 4;

    if (activeStepIdx > 0) {
        if (isSingle) {
            const stepEl = document.querySelector(`.p-step-seq[data-step="${activeStepIdx}"]`);
            if (stepEl) {
                if (taskData.status === 'success') {
                    stepEl.classList.add('completed');
                } else {
                    stepEl.classList.add('active');
                }
            }
        } else {
            for (let i = 1; i <= 4; i++) {
                const stepEl = document.querySelector(`.p-step-seq[data-step="${i}"]`);
                if (i < activeStepIdx) {
                    stepEl.classList.add('completed');
                } else if (i === activeStepIdx) {
                    if (taskData.status === 'success') {
                        stepEl.classList.add('completed');
                    } else {
                        stepEl.classList.add('active');
                    }
                }
            }
        }
    }
}

function startPolling(taskId) {
    stopPolling();
    activeTaskId = taskId;
    lastLogLength = 0;
    
    // Clear console logs
    const consoleLogs = document.getElementById('console-logs');
    consoleLogs.innerHTML = '';
    
    logPollInterval = setInterval(pollLogs, 1500);
}

function stopPolling() {
    if (logPollInterval) {
        clearInterval(logPollInterval);
        logPollInterval = null;
    }
}

// Start Pipelines triggers
async function runPipeline(type) {
    try {
        const response = await fetch(`/api/run/${type}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({})
        });
        const data = await response.json();
        
        if (data.status === 'success') {
            startPolling(data.task_id);
            // Move to pipelines tab to monitor output
            document.querySelector('[data-tab="pipelines"]').click();
        } else {
            alert(`Error: ${data.message}`);
        }
    } catch (e) {
        console.error(`Failed to launch ${type} pipeline:`, e);
    }
}

// Start individual step in referral pipeline
async function runSingleStep(stepNum, event) {
    if (event) {
        event.stopPropagation();
    }
    
    // Check if any active task is running
    try {
        const checkRes = await fetch('/api/tasks');
        const tasks = await checkRes.json();
        for (let tid in tasks) {
            if (tasks[tid].status === 'running') {
                alert("A pipeline or step is already running. Please stop it or wait for it to finish first.");
                return;
            }
        }
        
        const response = await fetch('/api/run/referral', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ "step": stepNum })
        });
        const data = await response.json();
        
        if (data.status === 'success') {
            startPolling(data.task_id);
            // Move to pipelines tab to monitor output
            document.querySelector('[data-tab="pipelines"]').click();
        } else {
            alert(`Error: ${data.message}`);
        }
    } catch (e) {
        console.error(`Failed to launch step ${stepNum}:`, e);
    }
}

// Start individual step in scraper pipeline
async function runScraperStep(phase, event) {
    if (event) {
        event.stopPropagation();
    }
    
    // Check if any active task is running
    try {
        const checkRes = await fetch('/api/tasks');
        const tasks = await checkRes.json();
        for (let tid in tasks) {
            if (tasks[tid].status === 'running') {
                alert("A pipeline or step is already running. Please stop it or wait for it to finish first.");
                return;
            }
        }
        
        const response = await fetch('/api/run/scraper', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ "phase": phase })
        });
        const data = await response.json();
        
        if (data.status === 'success') {
            startPolling(data.task_id);
            // Move to pipelines tab to monitor output
            document.querySelector('[data-tab="pipelines"]').click();
        } else {
            alert(`Error: ${data.message}`);
        }
    } catch (e) {
        console.error(`Failed to launch scraper phase ${phase}:`, e);
    }
}

function updateScraperPipelineSteps(taskData) {
    const steps = document.querySelectorAll('#card-scraper .p-step-seq');
    steps.forEach(el => el.classList.remove('active', 'completed'));

    const args = taskData.args || [];
    const hasPhase1 = args.includes('phase1');
    const hasPhase2 = args.includes('phase2');
    const isFull = !hasPhase1 && !hasPhase2;

    const step1El = document.querySelector('#card-scraper .p-step-seq[data-step="1"]');
    const step2El = document.querySelector('#card-scraper .p-step-seq[data-step="2"]');

    if (hasPhase1) {
        if (taskData.status === 'success') {
            if (step1El) step1El.classList.add('completed');
        } else if (taskData.status === 'running') {
            if (step1El) step1El.classList.add('active');
        }
    } else if (hasPhase2) {
        if (taskData.status === 'success') {
            if (step2El) step2El.classList.add('completed');
        } else if (taskData.status === 'running') {
            if (step2El) step2El.classList.add('active');
        }
    } else if (isFull) {
        // Check logs to see if we reached phase 2 (emails sending)
        let reachedPhase2 = false;
        if (taskData.logs) {
            for (let i = 0; i < taskData.logs.length; i++) {
                const line = taskData.logs[i];
                if (line.includes('Sending email to') || line.includes('sending email') || line.includes('Phase 2') || line.includes('phase2')) {
                    reachedPhase2 = true;
                    break;
                }
            }
        }

        if (taskData.status === 'success') {
            if (step1El) step1El.classList.add('completed');
            if (step2El) step2El.classList.add('completed');
        } else if (taskData.status === 'running') {
            if (reachedPhase2) {
                if (step1El) step1El.classList.add('completed');
                if (step2El) step2El.classList.add('active');
            } else {
                if (step1El) step1El.classList.add('active');
            }
        }
    }
}

// Kill running pipeline tasks
async function killPipeline(type) {
    const taskId = `${type}_pipeline`;
    try {
        await fetch(`/api/task/${taskId}/kill`, { method: 'POST' });
    } catch (e) {
        console.error("Failed to terminate task:", e);
    }
}

// Send interactive inputs
async function sendStdin(choice) {
    if (!activeTaskId) return;
    
    try {
        const response = await fetch(`/api/task/${activeTaskId}/input`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ "input": choice })
        });
        const data = await response.json();
        if (data.status === 'success') {
            document.getElementById('stdin-overlay').classList.add('hidden');
        }
    } catch (e) {
        console.error("Failed to pipe stdin:", e);
    }
}

// Send custom input entered in text field
async function sendCustomStdin() {
    const inputEl = document.getElementById('stdin-custom-text');
    const val = inputEl.value;
    inputEl.value = '';
    await sendStdin(val);
}

// Add click listeners to pipeline buttons
document.getElementById('btn-run-scraper').addEventListener('click', () => runPipeline('scraper'));
document.getElementById('btn-run-referral').addEventListener('click', () => runPipeline('referral'));
document.getElementById('btn-kill-scraper').addEventListener('click', () => killPipeline('scraper'));
document.getElementById('btn-kill-referral').addEventListener('click', () => killPipeline('referral'));

document.querySelectorAll('.start-pipeline-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        const type = btn.getAttribute('data-pipeline');
        runPipeline(type);
    });
});

// Database Table Loaders (Search, Sort, Paginate)
let dbData = { scraper: [], referral: [] };

// Scraper Pagination State
let scraperCurrentPage = 1;
const scraperRecordsPerPage = 10;

async function loadTableData(type) {
    const url = type === 'scraper' ? '/api/data/job_tracker' : '/api/data/job_leads';
    try {
        const response = await fetch(url);
        const data = await response.json();
        dbData[type] = data;
        
        if (type === 'scraper') {
            populateKeywordDropdown();
            applyScraperFiltersAndRender();
        } else {
            renderTable(type, data);
        }
    } catch (e) {
        console.error(`Failed to load ${type} data:`, e);
    }
}

function renderTable(type, data) {
    const tbody = document.querySelector(`#table-${type} tbody`);
    tbody.innerHTML = '';

    if (data.length === 0) {
        const cols = type === 'scraper' ? 6 : 9;
        tbody.innerHTML = `<tr><td colspan="${cols}" class="table-empty">No records found.</td></tr>`;
        return;
    }

    if (type === 'scraper') {
        applyScraperFiltersAndRender();
        return;
    }

    data.forEach(row => {
        const tr = document.createElement('tr');
        const companyUrl = row.CompanyURL || "";
        const companyLinkHtml = companyUrl.startsWith("http") ? `<a href="${companyUrl}" target="_blank" title="${companyUrl}">Open Link</a>` : companyUrl;
        
        const shortenUrl = row.ShortenURL || "";
        const shortenLinkHtml = shortenUrl.startsWith("http") ? `<a href="${shortenUrl}" target="_blank">${shortenUrl}</a>` : shortenUrl;
        
        const statusOptions = ['new', 'ask for referral', 'not interested', 'done'];
        let statusOptionsHtml = '';
        statusOptions.forEach(opt => {
            const selected = (row.Status || 'new').toLowerCase().trim() === opt ? 'selected' : '';
            statusOptionsHtml += `<option value="${opt}" ${selected}>${opt.toUpperCase()}</option>`;
        });
        const cleanStatus = (row.Status || 'new').toLowerCase().replace(/\s+/g, '_');

        tr.innerHTML = `
            <td>${row.JobID || ""}</td>
            <td><strong>${row.CompanyName || ""}</strong></td>
            <td>${companyLinkHtml}</td>
            <td>${shortenLinkHtml}</td>
            <td>${row.SearchKeyword || ""}</td>
            <td>
                <div class="status-select-wrapper ${cleanStatus}">
                    <select class="status-inline-select" onchange="updateStatus('referral', ${row.JobID}, this.value)">
                        ${statusOptionsHtml}
                    </select>
                </div>
            </td>
            <td>${row.ReferralPerson || ""}</td>
            <td>${row.CreatedDateTime || ""}</td>
            <td style="text-align: center;">
                <button class="table-action-btn btn-delete" onclick="deleteRow('referral', ${row.JobID})" title="Delete job">
                    <i class="fa-solid fa-trash-can"></i>
                </button>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

function formatDisplayDate(ts) {
    if (!ts) return "";
    try {
        const cleanTs = ts.split('.')[0].replace('T', ' ');
        return cleanTs;
    } catch(e) {
        return ts;
    }
}

function applyScraperFiltersAndRender() {
    const idFilter = document.getElementById('filter-col-id') ? document.getElementById('filter-col-id').value.toLowerCase().trim() : '';
    const emailFilter = document.getElementById('filter-col-email') ? document.getElementById('filter-col-email').value.toLowerCase().trim() : '';
    const statusFilter = document.getElementById('filter-col-status') ? document.getElementById('filter-col-status').value.toLowerCase().trim() : '';
    const keywordFilter = document.getElementById('filter-col-keyword') ? document.getElementById('filter-col-keyword').value.toLowerCase().trim() : '';
    const timestampFilter = document.getElementById('filter-col-timestamp') ? document.getElementById('filter-col-timestamp').value.toLowerCase().trim() : '';
    
    const allData = dbData['scraper'] || [];
    
    // 1. Filter
    const filtered = allData.filter(row => {
        const matchesId = !idFilter || String(row.ID || '').toLowerCase().includes(idFilter);
        const matchesEmail = !emailFilter || String(row.Email || '').toLowerCase().includes(emailFilter);
        const matchesStatus = !statusFilter || String(row.Status || '').toLowerCase().trim() === statusFilter;
        const matchesKeyword = !keywordFilter || String(row.Keyword || '').toLowerCase().trim() === keywordFilter;
        
        let matchesTimestamp = true;
        if (timestampFilter) {
            matchesTimestamp = String(row.Timestamp || '').toLowerCase().includes(timestampFilter);
        }
        
        return matchesId && matchesEmail && matchesStatus && matchesKeyword && matchesTimestamp;
    });
    
    // 2. Sort (Newest first by Timestamp descending)
    filtered.sort((a, b) => {
        const dateA = a.Timestamp ? new Date(a.Timestamp) : 0;
        const dateB = b.Timestamp ? new Date(b.Timestamp) : 0;
        return dateB - dateA;
    });
    
    // 3. Render page chunk
    const totalPages = Math.ceil(filtered.length / scraperRecordsPerPage) || 1;
    if (scraperCurrentPage > totalPages) {
        scraperCurrentPage = totalPages;
    }
    if (scraperCurrentPage < 1) {
        scraperCurrentPage = 1;
    }
    
    const startIndex = (scraperCurrentPage - 1) * scraperRecordsPerPage;
    const pageData = filtered.slice(startIndex, startIndex + scraperRecordsPerPage);
    
    const tbody = document.querySelector('#table-scraper tbody');
    if (tbody) {
        tbody.innerHTML = '';
        
        if (pageData.length === 0) {
            tbody.innerHTML = `<tr><td colspan="6" class="table-empty">No matching records found.</td></tr>`;
            renderScraperPaginationControls(filtered.length);
            return;
        }
        
        pageData.forEach(row => {
            const tr = document.createElement('tr');
            
            const statusClean = String(row.Status || 'New').toLowerCase().trim();
            const badgeClass = statusClean === 'sent' ? 'badge-green' : 'badge-yellow';
            const statusHtml = `<span class="badge ${badgeClass}">${statusClean.toUpperCase()}</span>`;
            
            const escapedEmail = String(row.Email || '').replace(/'/g, "\\'");
            const escapedStatus = String(row.Status || '').replace(/'/g, "\\'");
            const escapedKeyword = String(row.Keyword || '').replace(/'/g, "\\'");
            
            tr.innerHTML = `
                <td>${row.ID || ""}</td>
                <td><strong>${row.Email || ""}</strong></td>
                <td>${statusHtml}</td>
                <td>${row.Keyword || ""}</td>
                <td>${row.Timestamp ? formatDisplayDate(row.Timestamp) : ""}</td>
                <td style="text-align: center;">
                    <div style="display: flex; gap: 8px; justify-content: center;">
                        <button class="table-action-btn btn-edit" onclick="showEditScraperModal(${row.ID}, '${escapedEmail}', '${escapedStatus}', '${escapedKeyword}')" title="Edit record">
                            <i class="fa-solid fa-pen-to-square"></i>
                        </button>
                        <button class="table-action-btn btn-delete" onclick="deleteRow('scraper', ${row.ID})" title="Delete record">
                            <i class="fa-solid fa-trash-can"></i>
                        </button>
                    </div>
                </td>
            `;
            tbody.appendChild(tr);
        });
    }
    
    renderScraperPaginationControls(filtered.length);
}

function renderScraperPaginationControls(totalRecords) {
    const container = document.getElementById('scraper-pagination');
    if (!container) return;
    
    const totalPages = Math.ceil(totalRecords / scraperRecordsPerPage) || 1;
    
    const startRecord = totalRecords === 0 ? 0 : (scraperCurrentPage - 1) * scraperRecordsPerPage + 1;
    const endRecord = Math.min(scraperCurrentPage * scraperRecordsPerPage, totalRecords);
    
    let infoHtml = `<div class="pagination-info">Showing <strong>${startRecord}</strong> to <strong>${endRecord}</strong> of <strong>${totalRecords}</strong> records</div>`;
    
    let controlsHtml = `<div class="pagination-controls">`;
    const prevDisabled = scraperCurrentPage === 1 ? 'disabled' : '';
    controlsHtml += `
        <button class="pagination-btn" onclick="changeScraperPage(${scraperCurrentPage - 1})" ${prevDisabled}>
            <i class="fa-solid fa-chevron-left"></i> Prev
        </button>
    `;
    
    controlsHtml += `<div class="pagination-pages">`;
    for (let i = 1; i <= totalPages; i++) {
        if (totalPages <= 6 || i === 1 || i === totalPages || (i >= scraperCurrentPage - 1 && i <= scraperCurrentPage + 1)) {
            const activeClass = i === scraperCurrentPage ? 'active' : '';
            controlsHtml += `<button class="pagination-page-btn ${activeClass}" onclick="changeScraperPage(${i})">${i}</button>`;
        } else if (i === 2 && scraperCurrentPage > 3) {
            controlsHtml += `<span style="color: var(--text-secondary); padding: 0 4px;">...</span>`;
            i = scraperCurrentPage - 2;
        } else if (i === scraperCurrentPage + 2 && scraperCurrentPage < totalPages - 2) {
            controlsHtml += `<span style="color: var(--text-secondary); padding: 0 4px;">...</span>`;
            i = totalPages - 1;
        }
    }
    controlsHtml += `</div>`;
    
    const nextDisabled = scraperCurrentPage === totalPages ? 'disabled' : '';
    controlsHtml += `
        <button class="pagination-btn" onclick="changeScraperPage(${scraperCurrentPage + 1})" ${nextDisabled}>
            Next <i class="fa-solid fa-chevron-right"></i>
        </button>
    `;
    controlsHtml += `</div>`;
    
    container.innerHTML = infoHtml + controlsHtml;
}

function changeScraperPage(page) {
    scraperCurrentPage = page;
    applyScraperFiltersAndRender();
}

// In-place edits & deletions
async function updateStatus(type, id, newStatus) {
    try {
        const response = await fetch('/api/data/update_status', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                "db_type": type,
                "id": id,
                "status": newStatus
            })
        });
        const data = await response.json();
        if (data.status === 'success') {
            await loadTableData(type);
            await loadStats();
        } else {
            alert(`Error updating status: ${data.message}`);
        }
    } catch (e) {
        console.error("Failed to update status:", e);
    }
}

async function deleteRow(type, id) {
    if (!confirm("Are you sure you want to delete this row from the database?")) return;
    try {
        const response = await fetch('/api/data/delete_row', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                "db_type": type,
                "id": id
            })
        });
        const data = await response.json();
        if (data.status === 'success') {
            await loadTableData(type);
            await loadStats();
        } else {
            alert(`Error deleting row: ${data.message}`);
        }
    } catch (e) {
        console.error("Failed to delete row:", e);
    }
}

// Dynamic Multi-User & Settings Controllers
let activeUser = "";
let allUsers = [];
let scraperKeywords = [];
let connectKeywords = [];
let cachedConfig = {};

// Searchable user dropdown triggers
function toggleUserDropdown(event) {
    if (event) event.stopPropagation();
    const dropdown = document.getElementById('user-select-dropdown');
    dropdown.classList.toggle('hidden');
    if (!dropdown.classList.contains('hidden')) {
        document.getElementById('user-search-input').value = '';
        document.getElementById('user-search-input').focus();
        filterUserOptions();
    }
}

function filterUserOptions() {
    const query = document.getElementById('user-search-input').value.toLowerCase().trim();
    const optionsContainer = document.getElementById('user-select-options-list');
    optionsContainer.innerHTML = '';
    
    const filtered = allUsers.filter(u => u.toLowerCase().includes(query));
    if (filtered.length === 0) {
        optionsContainer.innerHTML = '<div style="padding: 10px 12px; font-size: 0.85rem; color: var(--text-secondary); text-align: center;">No profiles found</div>';
        return;
    }
    
    filtered.forEach(user => {
        const option = document.createElement('div');
        option.className = `searchable-select-option ${user === activeUser ? 'selected' : ''}`;
        option.innerHTML = `<i class="fa-solid fa-user-circle"></i> <span>${user}</span>`;
        option.addEventListener('click', () => {
            selectUser(user);
        });
        optionsContainer.appendChild(option);
    });
}

// Select a user profile
async function selectUser(username) {
    try {
        const response = await fetch('/api/users/select', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ "user": username })
        });
        const data = await response.json();
        if (data.status === 'success') {
            document.getElementById('user-select-dropdown').classList.add('hidden');
            await loadUsers();
        } else {
            alert(`Error selecting profile: ${data.message}`);
        }
    } catch (e) {
        console.error("Failed to select user:", e);
    }
}

// Create new user profile modal
function showCreateUserModal() {
    document.getElementById('user-select-dropdown').classList.add('hidden');
    document.getElementById('new-username-input').value = '';
    document.getElementById('create-user-modal').classList.remove('hidden');
}

function hideCreateUserModal() {
    document.getElementById('create-user-modal').classList.add('hidden');
}

async function confirmCreateUser() {
    const input = document.getElementById('new-username-input');
    const username = input.value.trim();
    if (!username) {
        alert("Please enter a profile name");
        return;
    }
    try {
        const response = await fetch('/api/users/create', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ "username": username })
        });
        const data = await response.json();
        if (data.status === 'success') {
            hideCreateUserModal();
            await loadUsers();
        } else {
            alert(`Error creating profile: ${data.message}`);
        }
    } catch (e) {
        console.error("Failed to create profile:", e);
    }
}

// Fetch all profiles and selected user
async function loadUsers() {
    try {
        const response = await fetch('/api/users');
        const data = await response.json();
        allUsers = data.users || [];
        activeUser = data.selected_user || "";
        
        document.getElementById('selected-user-display').innerText = activeUser || 'Select Profile';
        
        // Populate options in dropdown
        filterUserOptions();
        
        // Handle onboarding: if there are no users, force profile creation
        const cancelBtn = document.getElementById('btn-cancel-create-user');
        if (allUsers.length === 0) {
            if (cancelBtn) cancelBtn.style.display = 'none';
            showCreateUserModal();
        } else {
            if (cancelBtn) cancelBtn.style.display = 'inline-block';
            // Load configurations for active user
            await loadSettings();
        }
    } catch (e) {
        console.error("Failed to load profiles list:", e);
    }
}

// Subtab navigation in Settings form
document.querySelectorAll('.settings-tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.settings-tab-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.settings-tab-pane').forEach(p => p.classList.remove('active'));
        
        btn.classList.add('active');
        const paneId = `subtab-${btn.getAttribute('data-settings-tab')}`;
        const pane = document.getElementById(paneId);
        if (pane) {
            pane.classList.add('active');
        }
    });
});

// Keywords tags rendering
function renderKeywords(type) {
    const container = document.getElementById(`${type}-keywords-container`);
    const inputField = document.getElementById(`${type}-tag-input`);
    const keywordsList = type === 'scraper' ? scraperKeywords : connectKeywords;
    
    // Clear old tags
    const oldTags = container.querySelectorAll('.tag-badge');
    oldTags.forEach(el => el.remove());
    
    // Render current tags
    keywordsList.forEach((kw, index) => {
        const badge = document.createElement('div');
        badge.className = 'tag-badge';
        badge.innerHTML = `
            <span>${kw}</span>
            <i class="fa-solid fa-xmark btn-remove-tag" onclick="removeKeyword('${type}', ${index})"></i>
        `;
        container.insertBefore(badge, inputField);
    });
}

function addKeyword(type) {
    const inputField = document.getElementById(`${type}-tag-input`);
    const value = inputField.value.trim();
    if (!value) return;
    
    const keywordsList = type === 'scraper' ? scraperKeywords : connectKeywords;
    if (!keywordsList.includes(value)) {
        keywordsList.push(value);
        renderKeywords(type);
    }
    inputField.value = '';
}

function removeKeyword(type, index) {
    const keywordsList = type === 'scraper' ? scraperKeywords : connectKeywords;
    keywordsList.splice(index, 1);
    renderKeywords(type);
}

// Inline Bulk paste keywords
function toggleBulkPaste(type) {
    const box = document.getElementById(`${type}-bulk-paste-box`);
    box.classList.toggle('hidden');
    if (!box.classList.contains('hidden')) {
        const keywordsList = type === 'scraper' ? scraperKeywords : connectKeywords;
        document.getElementById(`${type}-bulk-paste-text`).value = keywordsList.join(', ');
        document.getElementById(`${type}-bulk-paste-text`).focus();
    }
}

function applyBulkKeywords(type) {
    const text = document.getElementById(`${type}-bulk-paste-text`).value;
    const splitKws = text.split(/,|\n/).map(k => k.trim()).filter(k => k.length > 0);
    
    if (type === 'scraper') {
        scraperKeywords = splitKws;
    } else {
        connectKeywords = splitKws;
    }
    renderKeywords(type);
    toggleBulkPaste(type);
}

// Switch email/connect templates between preview and edit mode
function switchTemplateMode(type, mode) {
    const editBtn = document.getElementById(`btn-mode-edit-${type}`);
    const previewBtn = document.getElementById(`btn-mode-preview-${type}`);
    const textarea = document.getElementById(`${type}-${type === 'scraper' ? 'email' : 'message'}-template`);
    const previewBox = document.getElementById(`${type}-template-preview`);
    
    if (mode === 'edit') {
        editBtn.classList.add('active');
        previewBtn.classList.remove('active');
        textarea.classList.remove('hidden');
        previewBox.classList.add('hidden');
    } else {
        editBtn.classList.remove('active');
        previewBtn.classList.add('active');
        textarea.classList.add('hidden');
        previewBox.classList.remove('hidden');
        
        // Render Preview with resolved placeholder strings
        const rawTemplate = textarea.value;
        const firstName = document.getElementById('profile-first-name').value || 'First';
        const lastName = document.getElementById('profile-last-name').value || 'Last';
        const email = document.getElementById('profile-email').value || 'email@example.com';
        const phone = document.getElementById('profile-phone').value || '0000000000';
        const experience = document.getElementById('profile-experience').value || '7+ years';
        const linkedinUrl = document.getElementById('profile-linkedin-url').value || 'https://linkedin.com/in/username';
        const currentLocation = document.getElementById('profile-current-location').value || 'Current City, India';
        const preferredLocations = document.getElementById('profile-locations').value || 'Preferred Cities';
        const currentCtc = document.getElementById('profile-current-ctc').value || '15 LPA';
        const expectedCtc = document.getElementById('profile-expected-ctc').value || '22 LPA';
        const resumeUrl = document.getElementById('profile-resume-url').value || 'https://resume-link.com';
        
        let previewHtml = rawTemplate
            .replace(/{FIRST_NAME}/g, firstName)
            .replace(/{LAST_NAME}/g, lastName)
            .replace(/{EMAIL}/g, email)
            .replace(/{PHONE_NUMBER}/g, phone)
            .replace(/{EXPERIENCE}/g, experience)
            .replace(/{LINKEDIN_PROFILE_URL}/g, linkedinUrl)
            .replace(/{CURRENT_LOCATION}/g, currentLocation)
            .replace(/{PREFERRED_LOCATIONS}/g, preferredLocations)
            .replace(/{CURRENT_CTC}/g, currentCtc)
            .replace(/{EXPECTED_CTC}/g, expectedCtc)
            .replace(/{resume}/g, resumeUrl)
            .replace(/{company}/g, "Sample Company")
            .replace(/{job_url}/g, "https://linkedin.com/jobs/view/12345");
            
        previewBox.innerText = previewHtml;
    }
}

// Upload resume PDF
async function uploadResumeFile() {
    const fileInput = document.getElementById('resume-file-input');
    if (fileInput.files.length === 0) return;
    
    const file = fileInput.files[0];
    const label = document.getElementById('resume-filename-label');
    label.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Uploading ${file.name}...`;
    
    const formData = new FormData();
    formData.append('resume', file);
    
    try {
        const response = await fetch('/api/users/resume/upload', {
            method: 'POST',
            body: formData
        });
        const data = await response.json();
        if (data.status === 'success') {
            label.innerHTML = `<i class="fa-solid fa-file-pdf" style="color: var(--accent-red);"></i> ${data.resume_name}`;
            
            // Add download/view button
            const downloadContainer = document.getElementById('resume-download-link-container');
            downloadContainer.innerHTML = `
                <a href="/api/users/resume/download/${activeUser}" target="_blank" class="btn btn-secondary" style="padding: 8px 12px;" title="View resume">
                    <i class="fa-solid fa-eye"></i>
                </a>
            `;
        } else {
            label.innerHTML = `<i class="fa-solid fa-triangle-exclamation" style="color: var(--accent-red);"></i> Upload failed: ${data.message}`;
        }
    } catch (e) {
        console.error("Failed to upload resume file:", e);
        label.innerHTML = `<i class="fa-solid fa-triangle-exclamation" style="color: var(--accent-red);"></i> Error uploading file`;
    }
}

// Config page controllers
function togglePasswordVisibility(id) {
    const input = document.getElementById(id);
    if (!input) return;
    input.type = input.type === 'password' ? 'text' : 'password';
}

// Load configurations for selected user
async function loadSettings() {
    try {
        const response = await fetch('/api/users/config');
        const data = await response.json();
        
        cachedConfig = data;
        
        const username = data.username;
        const config = data.config || {};
        const globalSettings = data.global_settings || {};
        
        const profile = config.profile || {};
        const scraper = config.email_scraper || {};
        const connect = config.linkedin_connect || {};
        
        const setVal = (id, val) => {
            const el = document.getElementById(id);
            if (el) el.value = val || '';
        };
        const setChecked = (id, checked) => {
            const el = document.getElementById(id);
            if (el) el.checked = checked;
        };

        // 1. User Profile fields
        setVal('profile-first-name', profile.first_name);
        setVal('profile-last-name', profile.last_name);
        setVal('profile-email', profile.email);
        setVal('profile-phone', profile.phone);
        setVal('profile-experience', profile.experience);
        setVal('profile-current-location', profile.current_location);
        setVal('profile-locations', profile.preferred_locations);
        setVal('profile-linkedin-url', profile.linkedin_url);
        setVal('profile-resume-url', profile.resume_url);
        setVal('profile-current-ctc', profile.current_ctc);
        setVal('profile-expected-ctc', profile.expected_ctc);
        
        // Resume file details
        const resumeFilename = profile.resume_name || '';
        const label = document.getElementById('resume-filename-label');
        const downloadContainer = document.getElementById('resume-download-link-container');
        if (resumeFilename && label && downloadContainer) {
            label.innerHTML = `<i class="fa-solid fa-file-pdf" style="color: var(--accent-red);"></i> ${resumeFilename}`;
            downloadContainer.innerHTML = `
                <a href="/api/users/resume/download/${username}" target="_blank" class="btn btn-secondary" style="padding: 8px 12px;" title="View resume">
                    <i class="fa-solid fa-eye"></i>
                </a>
            `;
        } else if (label && downloadContainer) {
            label.innerHTML = `<i class="fa-solid fa-paperclip"></i> No file uploaded`;
            downloadContainer.innerHTML = '';
        }
        
        // 2. Email Scraper fields
        setVal('scraper-interval', scraper.interval || '60');
        setChecked('scraper-review-mode', scraper.review_mode === true);
        setVal('scraper-email-template', scraper.email_template);
        
        scraperKeywords = scraper.keywords || [];
        renderKeywords('scraper');
        
        // 3. LinkedIn Connect fields
        setVal('connect-interval', connect.interval || '120');
        setChecked('connect-review-mode', connect.review_mode === true);
        setVal('connect-message-template', connect.message_template);
        
        connectKeywords = connect.keywords || [];
        renderKeywords('connect');

        // Reset Template mode displays to Edit
        switchTemplateMode('scraper', 'edit');
        switchTemplateMode('connect', 'edit');

        // Update character counter for connection template
        if (typeof updateConnectCharCount === 'function') updateConnectCharCount();

        // 4. Global settings
        setVal('setting-linkedin-email', globalSettings.linkedin_email);
        setVal('setting-linkedin-password', globalSettings.linkedin_password);
        setVal('setting-search-location', globalSettings.search_location);
        setVal('setting-search-time', globalSettings.search_time_range);
        setChecked('setting-dry-run', globalSettings.dry_run === '1');
        setVal('setting-smtp-password', globalSettings.smtp_password);
        
    } catch (e) {
        console.error("Failed to load settings:", e);
    }
}

// Save active profile configuration form
async function saveSettingsForm(event) {
    if (event) event.preventDefault();
    
    const saveStatus = document.getElementById('save-status');
    const profileSaveStatus = document.getElementById('profile-save-status');
    if (saveStatus) {
        saveStatus.innerText = 'Saving configurations...';
        saveStatus.className = 'save-status';
    }
    if (profileSaveStatus) {
        profileSaveStatus.innerText = 'Saving profile...';
        profileSaveStatus.className = 'save-status';
    }
    
    // Add any remaining tags entered in input fields
    addKeyword('scraper');
    addKeyword('connect');
    
    const profile = cachedConfig.config?.profile || {};
    const emailScraper = cachedConfig.config?.email_scraper || {};
    const linkedinConnect = cachedConfig.config?.linkedin_connect || {};
    const globalSettings = cachedConfig.global_settings || {};
    
    const getVal = (id, fallback) => {
        const el = document.getElementById(id);
        return el ? el.value : fallback;
    };
    const getChecked = (id, fallback) => {
        const el = document.getElementById(id);
        return el ? el.checked : fallback;
    };
    
    const body = {
        "profile": {
            "first_name": getVal('profile-first-name', profile.first_name),
            "last_name": getVal('profile-last-name', profile.last_name),
            "email": getVal('profile-email', profile.email),
            "phone": getVal('profile-phone', profile.phone),
            "experience": getVal('profile-experience', profile.experience),
            "current_location": getVal('profile-current-location', profile.current_location),
            "preferred_locations": getVal('profile-locations', profile.preferred_locations),
            "linkedin_url": getVal('profile-linkedin-url', profile.linkedin_url),
            "resume_url": getVal('profile-resume-url', profile.resume_url),
            "resume_name": document.getElementById('resume-filename-label') ? 
                document.getElementById('resume-filename-label').innerText.replace("No file uploaded", "").trim() : 
                profile.resume_name,
            "current_ctc": getVal('profile-current-ctc', profile.current_ctc),
            "expected_ctc": getVal('profile-expected-ctc', profile.expected_ctc)
        },
        "email_scraper": {
            "sender_email": emailScraper.sender_email || "",
            "interval": getVal('scraper-interval', emailScraper.interval || '60'),
            "review_mode": getChecked('scraper-review-mode', emailScraper.review_mode),
            "keywords": scraperKeywords,
            "email_template": getVal('scraper-email-template', emailScraper.email_template)
        },
        "linkedin_connect": {
            "interval": getVal('connect-interval', linkedinConnect.interval || '120'),
            "review_mode": getChecked('connect-review-mode', linkedinConnect.review_mode),
            "keywords": connectKeywords,
            "message_template": getVal('connect-message-template', linkedinConnect.message_template)
        },
        "global_settings": {
            "linkedin_email": getVal('setting-linkedin-email', globalSettings.linkedin_email || ""),
            "linkedin_password": getVal('setting-linkedin-password', globalSettings.linkedin_password || ""),
            "search_location": getVal('setting-search-location', globalSettings.search_location || "Bangalore, Karnataka, India"),
            "search_time_range": getVal('setting-search-time', globalSettings.search_time_range || "r604800"),
            "dry_run": document.getElementById('setting-dry-run') ? (document.getElementById('setting-dry-run').checked ? "1" : "0") : (globalSettings.dry_run || "0"),
            "max_apply": globalSettings.max_apply || "5",
            "max_run_duration_seconds": globalSettings.max_run_duration_seconds || "600",
            "smtp_server": globalSettings.smtp_server || "smtp.gmail.com",
            "smtp_port": globalSettings.smtp_port || "587",
            "smtp_email": globalSettings.smtp_email || "",
            "smtp_password": getVal('setting-smtp-password', globalSettings.smtp_password || "")
        }
    };
    
    try {
        const response = await fetch('/api/users/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        const data = await response.json();
        if (data.status === 'success') {
            if (saveStatus) {
                saveStatus.innerText = '✓ Settings successfully saved & applied!';
                saveStatus.className = 'save-status success';
                setTimeout(() => { saveStatus.innerText = ''; }, 3000);
            }
            if (profileSaveStatus) {
                profileSaveStatus.innerText = '✓ Profile successfully saved!';
                profileSaveStatus.className = 'save-status success';
                setTimeout(() => { profileSaveStatus.innerText = ''; }, 3000);
            }
            
            // Reload settings to refresh fields/labels
            await loadSettings();
        } else {
            if (saveStatus) {
                saveStatus.innerText = '✕ Error saving configurations.';
                saveStatus.className = 'save-status error';
            }
            if (profileSaveStatus) {
                profileSaveStatus.innerText = '✕ Error saving profile.';
                profileSaveStatus.className = 'save-status error';
            }
        }
    } catch (e) {
        console.error("Failed to save settings:", e);
        if (saveStatus) {
            saveStatus.innerText = '✕ Failed to save settings.';
            saveStatus.className = 'save-status error';
        }
        if (profileSaveStatus) {
            profileSaveStatus.innerText = '✕ Failed to save profile.';
            profileSaveStatus.className = 'save-status error';
        }
    }
}

// Multi-criteria filter controller
function applyFilters(type) {
    const searchVal = document.getElementById(`search-${type}`).value.toLowerCase().trim();
    const statusVal = document.getElementById(`filter-status-${type}`).value.toLowerCase();
    const dateVal = document.getElementById(`filter-date-${type}`).value;
    
    const originalData = dbData[type];
    
    const filtered = originalData.filter(row => {
        // 1. Text Search
        let textMatch = true;
        if (searchVal) {
            if (type === 'scraper') {
                textMatch = (row.Email && row.Email.toLowerCase().includes(searchVal)) ||
                            (row.Keyword && row.Keyword.toLowerCase().includes(searchVal)) ||
                            (row['Referral Person'] && row['Referral Person'].toLowerCase().includes(searchVal));
            } else {
                textMatch = (row.CompanyName && row.CompanyName.toLowerCase().includes(searchVal)) ||
                            (row.SearchKeyword && row.SearchKeyword.toLowerCase().includes(searchVal)) ||
                            (row.ReferralPerson && row.ReferralPerson.toLowerCase().includes(searchVal));
            }
        }
        
        // 2. Status Match
        let statusMatch = true;
        if (statusVal !== 'all') {
            const currentStatus = (row.Status || 'pending').toLowerCase().trim();
            statusMatch = currentStatus === statusVal;
        }
        
        // 3. Recency Match
        let dateMatch = true;
        if (dateVal !== 'all') {
            const dateStr = type === 'scraper' ? row.Timestamp : row.CreatedDateTime;
            if (dateStr) {
                let cleanDateStr = dateStr;
                if (dateStr.includes('T')) {
                     cleanDateStr = dateStr.split('.')[0];
                }
                const rowDate = new Date(cleanDateStr.replace(/-/g, '/'));
                const today = new Date();
                
                const diffTime = Math.abs(today - rowDate);
                const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
                
                if (dateVal === 'today') {
                    dateMatch = rowDate.toDateString() === today.toDateString();
                } else if (dateVal === 'week') {
                    dateMatch = diffDays <= 7;
                }
            } else {
                dateMatch = false;
            }
        }
        
        return textMatch && statusMatch && dateMatch;
    });
    
    renderTable(type, filtered);
}

// Bind listeners to Scraper column header filters
bindScraperColumnFilters();

// Bind listeners to Referral Database filters
document.getElementById('search-referral').addEventListener('input', () => applyFilters('referral'));
document.getElementById('filter-status-referral').addEventListener('change', () => applyFilters('referral'));
document.getElementById('filter-date-referral').addEventListener('change', () => applyFilters('referral'));

// Check if any pipeline is running on startup to restore log viewer state
async function checkActiveTasks() {
    try {
        const response = await fetch('/api/tasks');
        const tasks = await response.json();
        
        let foundRunning = false;
        for (let tid in tasks) {
            if (tasks[tid].status === 'running') {
                startPolling(tid);
                foundRunning = true;
                break;
            }
        }
        
        if (!foundRunning) {
            loadStats();
        }
    } catch (e) {
        console.error("Failed to check active processes:", e);
        loadStats();
    }
}

// Helpers
String.prototype.strip = function() {
    return this.trim();
};

// Initialize
const customTextInput = document.getElementById('stdin-custom-text');
if (customTextInput) {
    customTextInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            sendCustomStdin();
        }
    });
}

// Bind Tag keypress event
const scraperTagInput = document.getElementById('scraper-tag-input');
if (scraperTagInput) {
    scraperTagInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            addKeyword('scraper');
        }
    });
    scraperTagInput.addEventListener('blur', () => addKeyword('scraper'));
}

const connectTagInput = document.getElementById('connect-tag-input');
if (connectTagInput) {
    connectTagInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            addKeyword('connect');
        }
    });
    connectTagInput.addEventListener('blur', () => addKeyword('connect'));
}

// Dropdown click handlers
const dropdownTrigger = document.getElementById('user-select-trigger');
if (dropdownTrigger) {
    dropdownTrigger.addEventListener('click', (e) => toggleUserDropdown(e));
}

document.getElementById('btn-show-create-modal').addEventListener('click', () => showCreateUserModal());
document.getElementById('btn-cancel-create-user').addEventListener('click', () => hideCreateUserModal());
document.getElementById('btn-confirm-create-user').addEventListener('click', () => confirmCreateUser());

// Close dropdown on click outside
document.addEventListener('click', (e) => {
    const dropdown = document.getElementById('user-select-dropdown');
    const triggerEl = document.getElementById('user-select-trigger');
    if (dropdown && !dropdown.classList.contains('hidden') && triggerEl) {
        if (!dropdown.contains(e.target) && !triggerEl.contains(e.target)) {
            dropdown.classList.add('hidden');
        }
    }
});

// Load profiles list on start
loadUsers();

checkActiveTasks();
setInterval(loadStats, 10000); // refresh metrics every 10s

// ── Template Reset Helpers ───────────────────────────────────────────────────

// These defaults mirror DEFAULT_EMAIL_TEMPLATE / DEFAULT_CONNECTION_TEMPLATE
// in user_config_manager.py. If the user clears the textarea or wants a fresh
// start, clicking "Reset to Default" restores them here without a server call.

const DEFAULT_EMAIL_TEMPLATE = `Hi,

I came across your post regarding an opportunity.

My name is {FIRST_NAME}, and I have {EXPERIENCE} of experience.

I have attached my resume for your review. If my profile is a good fit for the role, I would be grateful if you could consider referring me or sharing it with the appropriate hiring team.

Email: {EMAIL}
Mobile: {PHONE_NUMBER}
Current Location: {CURRENT_LOCATION}
Preferred Locations: {PREFERRED_LOCATIONS}
LinkedIn: {LINKEDIN_PROFILE_URL}

Thank you for your time and support.

Regards,
{FIRST_NAME}`;

const DEFAULT_CONNECT_TEMPLATE = `Hi, I am {FIRST_NAME}. I am applying for the position at {company}. Would you kindly refer me?\nJob: {job_url}\nResume: {resume}\nThank you for your support.`;

function resetEmailTemplate() {
    if (!confirm('Reset to the default email template? Your current edits will be lost.')) return;
    const ta = document.getElementById('scraper-email-template');
    if (ta) {
        ta.value = DEFAULT_EMAIL_TEMPLATE;
        switchTemplateMode('scraper', 'edit');
    }
}

function resetConnectTemplate() {
    if (!confirm('Reset to the default connection message? Your current edits will be lost.')) return;
    const ta = document.getElementById('connect-message-template');
    if (ta) {
        ta.value = DEFAULT_CONNECT_TEMPLATE.replace(/\\n/g, '\n');
        updateConnectCharCount();
        switchTemplateMode('connect', 'edit');
    }
}

function insertToken(type, token) {
    const el = document.getElementById(`${type}-${type === 'scraper' ? 'email' : 'message'}-template`);
    if (!el) return;
    const start = el.selectionStart;
    const end = el.selectionEnd;
    const text = el.value;
    el.value = text.substring(0, start) + token + text.substring(end);
    el.focus();
    el.selectionStart = el.selectionEnd = start + token.length;
    if (type === 'connect' && typeof updateConnectCharCount === 'function') {
        updateConnectCharCount();
    }
}

function updateConnectCharCount() {
    const ta  = document.getElementById('connect-message-template');
    const ctr = document.getElementById('connect-char-count');
    if (!ta || !ctr) return;
    const len = ta.value.length;
    ctr.textContent = `${len} / 300`;
    ctr.style.color = len > 280 ? 'var(--accent-red)' : len > 240 ? 'var(--accent-yellow)' : 'var(--text-secondary)';
}

// Initialise character counter whenever settings are loaded
const _origSwitchTemplate = window.switchTemplateMode;
const _origLoadSettings   = window.loadSettings;

// Keep char count in sync when the connect template textarea is loaded
document.addEventListener('DOMContentLoaded', () => {
    const ta = document.getElementById('connect-message-template');
    if (ta) ta.addEventListener('input', updateConnectCharCount);
    // Initialize scraper header filters
    bindScraperColumnFilters();
});

function bindScraperColumnFilters() {
    const filters = ['filter-col-id', 'filter-col-email', 'filter-col-status', 'filter-col-keyword', 'filter-col-timestamp'];
    filters.forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            const eventName = el.tagName === 'SELECT' ? 'change' : 'input';
            el.addEventListener(eventName, () => {
                scraperCurrentPage = 1;
                applyScraperFiltersAndRender();
            });
        }
    });
}

function populateKeywordDropdown() {
    const select = document.getElementById('filter-col-keyword');
    if (!select) return;
    
    // Save current selected value
    const currentVal = select.value;
    
    // Get unique keywords (filter out empty/falsy, sort alphabetically)
    const keywords = [...new Set(dbData['scraper'].map(r => r.Keyword).filter(Boolean))];
    keywords.sort((a, b) => a.localeCompare(b));
    
    // Rebuild options
    let html = '<option value="">All</option>';
    keywords.forEach(kw => {
        const selected = kw === currentVal ? 'selected' : '';
        html += `<option value="${kw}" ${selected}>${kw}</option>`;
    });
    
    select.innerHTML = html;
}

function showEditScraperModal(id, email, status, keyword) {
    const idField = document.getElementById('edit-scraper-id');
    const emailField = document.getElementById('edit-scraper-email');
    const statusField = document.getElementById('edit-scraper-status');
    const keywordField = document.getElementById('edit-scraper-keyword');
    
    if (idField) idField.value = id;
    if (emailField) emailField.value = email;
    if (statusField) {
        const formattedStatus = status.toLowerCase() === 'sent' ? 'Sent' : 'New';
        statusField.value = formattedStatus;
    }
    if (keywordField) keywordField.value = keyword === 'None' || keyword === 'null' || !keyword ? '' : keyword;
    
    const modal = document.getElementById('edit-scraper-modal');
    if (modal) modal.classList.remove('hidden');
}

function hideEditScraperModal() {
    const modal = document.getElementById('edit-scraper-modal');
    if (modal) modal.classList.add('hidden');
}

async function saveScraperEditForm(event) {
    if (event) event.preventDefault();
    
    const id = document.getElementById('edit-scraper-id').value;
    const email = document.getElementById('edit-scraper-email').value;
    const status = document.getElementById('edit-scraper-status').value;
    const keyword = document.getElementById('edit-scraper-keyword').value;
    
    try {
        const response = await fetch('/api/data/edit_row', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                db_type: 'scraper',
                id: id,
                email: email,
                status: status,
                keyword: keyword
            })
        });
        const data = await response.json();
        if (data.status === 'success') {
            hideEditScraperModal();
            await loadTableData('scraper');
        } else {
            alert(`Error updating record: ${data.message}`);
        }
    } catch (e) {
        console.error("Failed to save record:", e);
        alert("Failed to save changes. Please try again.");
    }
}

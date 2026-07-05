// Tab Navigation Controller
const navItems = document.querySelectorAll('.nav-menu .nav-item');
const tabPanes = document.querySelectorAll('.main-content .tab-pane');

navItems.forEach(item => {
    item.addEventListener('click', () => {
        // Find if we were on settings tab
        const currentActive = document.querySelector('.nav-menu .nav-item.active');
        const wasOnSettings = currentActive ? currentActive.getAttribute('data-tab') === 'settings' : false;
        
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
            loadTableData('referrals');
        } else if (targetTab === 'dashboard') {
            loadStats();
            if (typeof loadDashboardAnalytics === 'function') loadDashboardAnalytics();
        }

        // If navigating away from settings, reset settings inputs to saved config
        if (wasOnSettings && targetTab !== 'settings') {
            loadSettings();
        }
    });
});

// Click logo to switch to dashboard
const logoContainer = document.querySelector('.sidebar .logo');
if (logoContainer) {
    logoContainer.addEventListener('click', () => {
        const dashboardTab = document.querySelector('.nav-menu .nav-item[data-tab="dashboard"]');
        if (dashboardTab) {
            dashboardTab.click();
        }
    });
}

// ChartJS Configuration
let metricsChartInstance = null;
function updateChart(stats) {
    const canvas = document.getElementById('metricsChart');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    
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
        
        const elEmailsScraped = document.getElementById('stat-emails-scraped');
        const elEmailsSent = document.getElementById('stat-emails-sent');
        const elJobsScraped = document.getElementById('stat-jobs-scraped');
        const elReferralsSent = document.getElementById('stat-referrals-sent');

        if (elEmailsScraped) elEmailsScraped.innerText = stats.total_emails_scraped;
        if (elEmailsSent) elEmailsSent.innerText = stats.emails_sent;
        if (elJobsScraped) elJobsScraped.innerText = stats.total_jobs_scraped;
        if (elReferralsSent) elReferralsSent.innerText = stats.referral_requests_sent;

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
            setGlobalPipelineLock(null);
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

            // Trigger real-time updates for dashboard and database tracker tables
            const isModalOpen = !document.getElementById('edit-scraper-modal').classList.contains('hidden') ||
                                (document.getElementById('edit-referral-modal') && !document.getElementById('edit-referral-modal').classList.contains('hidden')) ||
                                (document.getElementById('edit-referral-contact-modal') && !document.getElementById('edit-referral-contact-modal').classList.contains('hidden')) ||
                                document.querySelector('.modal-overlay:not(.hidden)');
            
            const isInteractingWithTable = document.activeElement && 
                                          (document.activeElement.closest('.data-table') || 
                                           document.activeElement.closest('.table-responsive') || 
                                           document.activeElement.classList.contains('status-inline-select'));
                                           
            if (!isModalOpen && !isInteractingWithTable) {
                loadTableData('scraper');
                loadTableData('referral');
                loadTableData('referrals');
            }
            if (typeof loadDashboardAnalytics === 'function') {
                loadDashboardAnalytics();
            }
        }

        // Highlight step numbers in sequence
        const activeTaskType = activeTaskId.split('::').pop(); // e.g. "referral_pipeline"
        if (activeTaskType === 'referral_pipeline') {
            updateReferralPipelineSteps(data);
        } else if (activeTaskType === 'scraper_pipeline') {
            updateScraperPipelineSteps(data);
        } else if (activeTaskType === 'recruiter_pipeline') {
            updateRecruiterPipelineSteps(data);
        }

        // Extract the pipeline type suffix (e.g. "referral" from "Lalit::referral_pipeline")
        const pipelineType = activeTaskId.split('::').pop();  // e.g. "scraper_pipeline"
        const pipelinePrefix = pipelineType.replace('_pipeline', '').replace(/_/g, '-');

        // Update badges
        const badge = document.getElementById(`badge-${pipelinePrefix}`);
        if (badge) {
            badge.innerText = data.status;
            badge.className = `status-badge status-${data.status}`;
        }

        // Toggle action buttons based on state
        const runBtn = document.getElementById(`btn-run-${pipelinePrefix}`);
        const killBtn = document.getElementById(`btn-kill-${pipelinePrefix}`);
        
        if (data.status === 'running' || data.status === 'queued') {
            if (runBtn) runBtn.classList.add('hidden');
            if (killBtn) killBtn.classList.remove('hidden');
            setGlobalPipelineLock(activeTaskId);
        } else {
            if (runBtn) runBtn.classList.remove('hidden');
            if (killBtn) killBtn.classList.add('hidden');
            setGlobalPipelineLock(null);
            stopPolling();
            loadStats(); // Reload stats after completion
            if (typeof loadDashboardAnalytics === 'function') loadDashboardAnalytics();
            loadTableData('scraper');
            loadTableData('referral');
            loadTableData('referrals');
            
            // Clear active steps, but keep completed steps visible
            const finishedType = activeTaskId.split('::').pop();
            if (finishedType === 'scraper_pipeline') {
                const steps = document.querySelectorAll('#card-scraper .p-step-seq');
                steps.forEach(el => el.classList.remove('active'));
            } else if (finishedType === 'referral_pipeline') {
                const steps = document.querySelectorAll('#card-referral .p-step-seq');
                steps.forEach(el => el.classList.remove('active'));
            } else if (finishedType === 'recruiter_pipeline') {
                const steps = document.querySelectorAll('#card-recruiter .p-step-seq');
                steps.forEach(el => el.classList.remove('active'));
            }
        }

        // Show/Hide Stdin interactive overlay
        const stdinOverlay = document.getElementById('stdin-overlay');
        if (data.waiting_for_input) {
            stdinOverlay.classList.remove('hidden');
            const refButtons = document.getElementById('stdin-referral-buttons');
            const outButtons = document.getElementById('stdin-outreach-buttons');
            const promptText = document.getElementById('stdin-prompt-text');
            const isConnector = (data.current_step_name && data.current_step_name.includes("linkedin_connect")) ||
                                (data.current_step_name && data.current_step_name.includes("recruiter_outreach")) ||
                                (data.current_step_name && data.current_step_name.includes("run_referral_outreach_send")) ||
                                activeTaskId.split('::').pop() === 'recruiter_pipeline';
            if (activeTaskId.split('::').pop() === 'scraper_pipeline' || isConnector) {
                if (refButtons) refButtons.classList.add('hidden');
                if (outButtons) outButtons.classList.remove('hidden');
                if (activeTaskId === 'scraper_pipeline') {
                    if (promptText) promptText.innerText = "Outreach Quality Gate is waiting for your choice. Please review the generated email and select:";
                } else {
                    if (promptText) promptText.innerText = "Invite Quality Gate is waiting for your choice. Please review the LinkedIn window and select:";
                }
            } else {
                if (refButtons) refButtons.classList.remove('hidden');
                if (outButtons) outButtons.classList.add('hidden');
                if (promptText) promptText.innerText = "Manual review script is waiting for your choice. Please review the Chrome window and make a selection:";
            }
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
    if (activeStepName.includes("linkedin_find_job.py") || activeStepName.includes("run_job_search.py")) activeStepIdx = 1;
    else if (activeStepName.includes("review_for_referral.py") || activeStepName.includes("run_referral_review.py")) activeStepIdx = 2;
    else if (activeStepName.includes("run_referral_outreach_discover.py")) activeStepIdx = 3;
    else if (activeStepName.includes("run_referral_outreach_send.py")) activeStepIdx = 4;
    else if (activeStepName.includes("shorten_urls.py") || activeStepName.includes("run_url_shortener.py")) activeStepIdx = 5;
    else if (activeStepName.includes("linkdin_connect.py") || activeStepName.includes("run_linkedin_connect.py")) activeStepIdx = 6;

    if (activeStepIdx > 0) {
        if (isSingle) {
            const stepEl = document.querySelector(`#card-referral .p-step-seq[data-step="${activeStepIdx}"]`);
            if (stepEl) {
                if (taskData.status === 'success') {
                    stepEl.classList.add('completed');
                } else {
                    stepEl.classList.add('active');
                }
            }
        } else {
            for (let i = 1; i <= 6; i++) {
                const stepEl = document.querySelector(`#card-referral .p-step-seq[data-step="${i}"]`);
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

async function updatePipelineLocks() {
    try {
        const response = await fetch('/api/tasks');
        const tasks = await response.json();
        
        const pipelines = ['scraper', 'referral', 'recruiter'];
        
        // Find task entry for current user + pipeline type from the namespaced task map.
        // Tasks are keyed as "{username}::scraper_pipeline" etc.
        // We match by username (activeUser) and pipeline type suffix.
        pipelines.forEach(p => {
            const pipelineKey = `${p}_pipeline`;
            // Look for a task belonging to the active user for this pipeline type
            const taskEntry = Object.entries(tasks).find(
                ([tid, t]) => t.username === activeUser && tid.endsWith(`::${pipelineKey}`)
            );
            const isRunning = taskEntry && (taskEntry[1].status === 'running' || taskEntry[1].status === 'queued');
            const taskId = taskEntry ? taskEntry[0] : `${activeUser}::${pipelineKey}`;
            
            // 1. Run Complete Pipeline button
            const runBtn = document.getElementById(`btn-run-${p}`);
            if (runBtn) {
                runBtn.disabled = isRunning;
            }
            
            // 2. Individual step buttons inside this card
            const cardEl = document.getElementById(`card-${p}`);
            if (cardEl) {
                const stepBtns = cardEl.querySelectorAll('.btn-step-run');
                stepBtns.forEach(btn => {
                    btn.disabled = isRunning;
                });
            }
            
            // 3. Kill button
            const killBtn = document.getElementById(`btn-kill-${p}`);
            if (killBtn) {
                killBtn.disabled = !isRunning;
                if (isRunning) {
                    killBtn.classList.remove('hidden');
                    if (runBtn) runBtn.classList.add('hidden');
                    // Store the actual namespaced task ID on the button for kill use
                    killBtn.dataset.taskId = taskId;
                } else {
                    killBtn.classList.add('hidden');
                    if (runBtn) runBtn.classList.remove('hidden');
                }
            }
            
            // 4. Update status badges
            const badge = document.getElementById(`badge-${p}`);
            if (badge && taskEntry) {
                badge.innerText = taskEntry[1].status;
                badge.className = `status-badge status-${taskEntry[1].status}`;
            }
        });
    } catch (e) {
        console.error("Failed to update pipeline locks:", e);
    }
}

function setGlobalPipelineLock(runningTaskId) {
    updatePipelineLocks();
}

function startPolling(taskId) {
    stopPolling();
    activeTaskId = taskId;
    lastLogLength = 0;
    
    // Clear console logs
    const consoleLogs = document.getElementById('console-logs');
    consoleLogs.innerHTML = '';
    
    setGlobalPipelineLock(taskId);
    
    logPollInterval = setInterval(pollLogs, 1500);
}

function stopPolling() {
    if (logPollInterval) {
        clearInterval(logPollInterval);
        logPollInterval = null;
    }
}

// Start Pipelines triggers — always for the active user profile
async function runPipeline(type) {
    try {
        const checkRes = await fetch('/api/tasks');
        const tasks = await checkRes.json();
        const pipelineKey = `${type}_pipeline`;
        // Find existing task for this user + type
        const existing = Object.entries(tasks).find(
            ([tid, t]) => t.username === activeUser && tid.endsWith(`::${pipelineKey}`)
        );
        if (existing && (existing[1].status === 'running' || existing[1].status === 'queued')) {
            alert(`The ${type.charAt(0).toUpperCase() + type.slice(1)} pipeline is already running for ${activeUser}. Please stop it or wait for it to finish first.`);
            return;
        }

        const response = await fetch(`/api/run/${type}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username: activeUser })
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
    
    // Check if referral pipeline is running for the active user
    try {
        const checkRes = await fetch('/api/tasks');
        const tasks = await checkRes.json();
        const existing = Object.entries(tasks).find(
            ([tid, t]) => t.username === activeUser && tid.endsWith('::referral_pipeline')
        );
        if (existing && (existing[1].status === 'running' || existing[1].status === 'queued')) {
            alert("The Referral pipeline is already running. Please stop it or wait for it to finish first.");
            return;
        }
        
        const response = await fetch('/api/run/referral', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ step: stepNum, username: activeUser })
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

// Start individual step in recruiter pipeline
async function runRecruiterStep(stepNum, event) {
    if (event) {
        event.stopPropagation();
    }
    
    // Check if recruiter pipeline is running for the active user
    try {
        const checkRes = await fetch('/api/tasks');
        const tasks = await checkRes.json();
        const existing = Object.entries(tasks).find(
            ([tid, t]) => t.username === activeUser && tid.endsWith('::recruiter_pipeline')
        );
        if (existing && (existing[1].status === 'running' || existing[1].status === 'queued')) {
            alert("The Recruiter pipeline is already running. Please stop it or wait for it to finish first.");
            return;
        }
        
        const response = await fetch('/api/run/recruiter', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ step: stepNum, username: activeUser })
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
        console.error(`Failed to launch recruiter step ${stepNum}:`, e);
    }
}

// Start individual step in scraper pipeline
async function runScraperStep(phase, event) {
    if (event) {
        event.stopPropagation();
    }
    
    // Check if scraper pipeline is running for the active user
    try {
        const checkRes = await fetch('/api/tasks');
        const tasks = await checkRes.json();
        const existing = Object.entries(tasks).find(
            ([tid, t]) => t.username === activeUser && tid.endsWith('::scraper_pipeline')
        );
        if (existing && (existing[1].status === 'running' || existing[1].status === 'queued')) {
            alert("The Scraper pipeline is already running. Please stop it or wait for it to finish first.");
            return;
        }
        
        const response = await fetch('/api/run/scraper', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ phase: phase, username: activeUser })
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

    const step1El = document.querySelector('#card-scraper .p-step-seq[data-step="1"]');
    const step2El = document.querySelector('#card-scraper .p-step-seq[data-step="2"]');
    const activeStepName = taskData.current_step_name || '';
    const isSingle = taskData.is_single_step;

    // Dedicated script mode: detect step by current running script name
    if (activeStepName.includes('run_email_scraper.py')) {
        // Step 1 only — dedicated scraper script
        if (taskData.status === 'success') {
            if (step1El) step1El.classList.add('completed');
        } else if (taskData.status === 'running') {
            if (step1El) step1El.classList.add('active');
        }
    } else if (activeStepName.includes('run_email_sender.py')) {
        // Step 2 only — dedicated sender script
        if (taskData.status === 'success') {
            if (step2El) step2El.classList.add('completed');
        } else if (taskData.status === 'running') {
            if (step2El) step2El.classList.add('active');
        }
    } else {
        // Full pipeline mode (run_email_outreach.py) — detect phase from logs
        let reachedPhase2 = false;
        if (taskData.logs) {
            for (let i = 0; i < taskData.logs.length; i++) {
                const line = taskData.logs[i];
                if (line.includes('Sending email to') || line.includes('sending email') || line.includes('Phase 2') || line.includes('Email sending')) {
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

function updateRecruiterPipelineSteps(taskData) {
    const steps = document.querySelectorAll('#card-recruiter .p-step-seq');
    steps.forEach(el => el.classList.remove('active', 'completed'));

    const activeStepName = taskData.current_step_name;
    const isSingle = taskData.is_single_step;

    if (!activeStepName) return;

    let activeStepIdx = 0;
    if (activeStepName.includes("run_recruiter_outreach_discover.py")) activeStepIdx = 1;
    else if (activeStepName.includes("run_recruiter_outreach_send.py")) activeStepIdx = 2;
    else if (activeStepName.includes("run_recruiter_outreach.py")) activeStepIdx = 3;

    if (activeStepIdx > 0) {
        if (isSingle) {
            const stepEl = document.querySelector(`#card-recruiter .p-step-seq[data-step="${activeStepIdx}"]`);
            if (stepEl) {
                if (taskData.status === 'success') {
                    stepEl.classList.add('completed');
                } else {
                    stepEl.classList.add('active');
                }
            }
        } else {
            for (let i = 1; i <= 3; i++) {
                const stepEl = document.querySelector(`#card-recruiter .p-step-seq[data-step="${i}"]`);
                if (stepEl) {
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
}



// Kill running pipeline tasks — uses the namespaced task ID stored on the kill button
async function killPipeline(type) {
    // Try to find the actual namespaced task ID from the kill button's data attribute.
    // Falls back to constructing it from activeUser for backward compat.
    const killBtn = document.getElementById(`btn-kill-${type}`);
    const taskId = (killBtn && killBtn.dataset.taskId) || `${activeUser}::${type}_pipeline`;
    try {
        await fetch(`/api/task/${encodeURIComponent(taskId)}/kill`, { method: 'POST' });
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
document.getElementById('btn-run-recruiter').addEventListener('click', () => runPipeline('recruiter'));
document.getElementById('btn-kill-scraper').addEventListener('click', () => killPipeline('scraper'));
document.getElementById('btn-kill-referral').addEventListener('click', () => killPipeline('referral'));
document.getElementById('btn-kill-recruiter').addEventListener('click', () => killPipeline('recruiter'));

document.querySelectorAll('.start-pipeline-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        const type = btn.getAttribute('data-pipeline');
        runPipeline(type);
    });
});

// Database Table Loaders (Search, Sort, Paginate)
let dbData = { scraper: [], referral: [], referrals: [] };

// Scraper Pagination State
let scraperCurrentPage = 1;
const scraperRecordsPerPage = 10;

// Referral Pagination State
let referralCurrentPage = 1;
const referralRecordsPerPage = 10;

// Referrals Outreach Pagination State
let referralsCurrentPage = 1;
const referralsRecordsPerPage = 10;

async function loadTableData(type) {
    let url;
    if (type === 'scraper') {
        url = '/api/data/job_tracker';
    } else if (type === 'referral') {
        url = '/api/data/job_leads';
    } else if (type === 'referrals') {
        url = '/api/data/referrals';
    }
    try {
        const response = await fetch(url);
        const data = await response.json();
        dbData[type] = data;
        
        if (type === 'scraper') {
            populateKeywordDropdown();
            applyScraperFiltersAndRender();
        } else if (type === 'referral') {
            applyFilters('referral');
        } else if (type === 'referrals') {
            applyReferralsFiltersAndRender();
        }
    } catch (e) {
        console.error(`Failed to load ${type} data:`, e);
    }
}

function applyReferralsFiltersAndRender() {
    const searchEl = document.getElementById('search-referrals-outreach');
    const statusEl = document.getElementById('filter-status-referrals-outreach');
    const sourceEl = document.getElementById('filter-source-referrals-outreach');
    
    const searchVal = searchEl ? searchEl.value.toLowerCase().trim() : '';
    const statusVal = statusEl ? statusEl.value.toLowerCase() : 'all';
    const sourceVal = sourceEl ? sourceEl.value.toLowerCase() : 'all';
    
    const originalData = dbData['referrals'] || [];
    
    const filtered = originalData.filter(row => {
        // 1. Text Search
        let textMatch = true;
        if (searchVal) {
            textMatch = (row.Referral_Person_Name && row.Referral_Person_Name.toLowerCase().includes(searchVal)) ||
                        (row.CompanyName && row.CompanyName.toLowerCase().includes(searchVal)) ||
                        (row.Referral_Status && row.Referral_Status.toLowerCase().includes(searchVal));
        }
        
        // 2. Status Match
        let statusMatch = true;
        if (statusVal !== 'all') {
            const currentStatus = (row.Referral_Status || 'pending').toLowerCase().trim();
            statusMatch = currentStatus === statusVal;
        }
        
        // 3. Source Match
        let sourceMatch = true;
        if (sourceVal !== 'all') {
            const currentSource = normalizeReferralSource(row.Referral_Source).toLowerCase();
            sourceMatch = currentSource === sourceVal;
        }
        
        return textMatch && statusMatch && sourceMatch;
    });
    
    // Sort referrals by ReferralID ascending
    filtered.sort((a, b) => {
        const idA = parseInt(a.ReferralID) || 0;
        const idB = parseInt(b.ReferralID) || 0;
        return idA - idB;
    });
    
    const totalPages = Math.ceil(filtered.length / referralsRecordsPerPage) || 1;
    if (referralsCurrentPage > totalPages) {
        referralsCurrentPage = totalPages;
    }
    if (referralsCurrentPage < 1) {
        referralsCurrentPage = 1;
    }
    
    const startIndex = (referralsCurrentPage - 1) * referralsRecordsPerPage;
    const pageData = filtered.slice(startIndex, startIndex + referralsRecordsPerPage);
    
    renderReferralsTable(pageData);
    renderReferralsPaginationControls(filtered.length);
}

function renderReferralsTable(data) {
    const tbody = document.querySelector('#table-referrals-outreach tbody');
    if (!tbody) return;
    tbody.innerHTML = '';
    
    if (data.length === 0) {
        tbody.innerHTML = `<tr><td colspan="10" class="table-empty">No matching referral contacts found.</td></tr>`;
        return;
    }
    
    data.forEach(row => {
        const tr = document.createElement('tr');
        
        const statusClean = String(row.Referral_Status || 'pending').toLowerCase().trim();
        const badgeClass = `badge-${statusClean.replace(/\s+/g, '_')}`;
        const statusHtml = `<span class="badge ${badgeClass}">${statusClean.toUpperCase()}</span>`;
        
        const verificationClean = String(row.Employment_Verification_Status || 'Verified').toLowerCase().trim();
        const verificationBadgeClass = `badge-${verificationClean.replace(/\s+/g, '_')}`;
        const verificationHtml = `<span class="badge ${verificationBadgeClass}">${verificationClean.toUpperCase()}</span>`;
        
        const encName = encodeURIComponent(row.Referral_Person_Name || "");
        const encEmail = encodeURIComponent(row.Referral_Person_Email || "");
        const encUrl = encodeURIComponent(row.Referral_Person_Profile_URL || "");
        const normalizedSource = normalizeReferralSource(row.Referral_Source);
        const encSource = encodeURIComponent(normalizedSource);
        const encStatus = encodeURIComponent(row.Referral_Status || "");
        const encCompany = encodeURIComponent(row.CompanyName || "");
        const encNotes = encodeURIComponent(row.Error_Reason || "");
        const encVerification = encodeURIComponent(row.Employment_Verification_Status || "Verified");
        const encJobUrl = encodeURIComponent(row.Job_URL || "");
        
        const jUrl = row.Job_URL || "";
        const jUrlHtml = jUrl.startsWith("http") ? `<a href="${jUrl}" target="_blank" class="table-link" title="${jUrl}"><i class="fa-solid fa-up-right-from-square" style="font-size:0.75rem;"></i> Open Job</a>` : jUrl;
        
        const pUrl = row.Referral_Person_Profile_URL || "";
        const pUrlHtml = pUrl.startsWith("http") ? `<a href="${pUrl}" target="_blank" class="table-link" title="${pUrl}"><strong>${row.Referral_Person_Name || ""}</strong></a>` : (row.Referral_Person_Name || "");

        tr.innerHTML = `
            <td>${row.ReferralID || ""}</td>
            <td><strong>${row.CompanyName || ""}</strong></td>
            <td>${jUrlHtml}</td>
            <td>${pUrlHtml}</td>
            <td><a href="${pUrl}" target="_blank" class="table-link" title="${pUrl}"><i class="fa-brands fa-linkedin" style="color:#0a66c2; font-size:1.1rem;"></i></a></td>
            <td><span style="font-size: 0.8rem;">${normalizedSource}</span></td>
            <td>${verificationHtml}</td>
            <td>${statusHtml}</td>
            <td>${row.Sent_Time ? formatDisplayDate(row.Sent_Time) : ""}</td>
            <td style="text-align: center;">
                <div style="display: flex; gap: 8px; justify-content: center;">
                    <button class="table-action-btn btn-edit" onclick="showEditReferralContactModal(${row.ReferralID}, '${encName}', '${encEmail}', '${encUrl}', '${encSource}', '${encStatus}', '${encCompany}', '${encNotes}', '${encVerification}', '${encJobUrl}')" title="Edit contact">
                        <i class="fa-solid fa-pen-to-square"></i>
                    </button>
                    <button class="table-action-btn btn-delete" onclick="deleteRow('referrals', ${row.ReferralID})" title="Delete contact">
                        <i class="fa-solid fa-trash-can"></i>
                    </button>
                </div>
            </td>
        `;
        tbody.appendChild(tr);
    });
}


function renderTable(type, data) {
    const tbody = document.querySelector(`#table-${type} tbody`);
    tbody.innerHTML = '';

    if (data.length === 0) {
        const cols = type === 'scraper' ? 6 : 8;
        tbody.innerHTML = `<tr><td colspan="${cols}" class="table-empty">No records found.</td></tr>`;
        return;
    }

    if (type === 'scraper') {
        applyScraperFiltersAndRender();
        return;
    }

    data.forEach(row => {
        const tr = document.createElement('tr');
        const lUrl = row.LinkedIn_Company_URL || "";
        const lUrlHtml = lUrl.startsWith("http") ? `<a href="${lUrl}" target="_blank" class="table-link" title="${lUrl}"><i class="fa-solid fa-up-right-from-square" style="font-size:0.75rem;"></i> Company</a>` : lUrl;

        const companyUrl = row.CompanyURL || "";
        const companyLinkHtml = companyUrl.startsWith("http") ? `<a href="${companyUrl}" target="_blank" title="${companyUrl}">Open Job</a>` : companyUrl;
        
        const shortenUrl = row.ShortenURL || "";
        const shortenLinkHtml = shortenUrl.startsWith("http") ? `<a href="${shortenUrl}" target="_blank">${shortenUrl}</a>` : shortenUrl;
        
        const targetOptions = [
            'new', 'interested', 'not interested', 'asked for referral', 'referred', 'done', 
            'in progress', 'completed – target not met', 'cancelled', 'failed', 'referral outreach completed'
        ];
        let statusOptionsHtml = '';
        targetOptions.forEach(opt => {
            const selected = (row.Status || 'new').toLowerCase().trim() === opt ? 'selected' : '';
            statusOptionsHtml += `<option value="${opt}" ${selected}>${opt.toUpperCase()}</option>`;
        });
        const cleanStatus = (row.Status || 'new').toLowerCase().replace(/\s+/g, '_');

        const encCompany = encodeURIComponent(row.CompanyName || "");
        const encUrl = encodeURIComponent(row.CompanyURL || "");
        const encShorten = encodeURIComponent(row.ShortenURL || "");
        const encKeyword = encodeURIComponent(row.SearchKeyword || "");
        const encPosition = encodeURIComponent(row.JobTitle || "");
        const encStatus = encodeURIComponent(row.Status || "");

        tr.innerHTML = `
            <td>${row.JobID || ""}</td>
            <td><strong>${row.CompanyName || ""}</strong></td>
            <td>${lUrlHtml}</td>
            <td>${companyLinkHtml}</td>
            <td>${shortenLinkHtml}</td>
            <td>${row.SearchKeyword || ""}</td>
            <td><strong>${row.Referral_Target || 5}</strong></td>
            <td><span style="color:var(--accent-green); font-weight:bold;">${row.Referral_Completed || 0}</span></td>
            <td><span style="color:${row.Referral_Remaining > 0 ? 'var(--accent-yellow)' : 'var(--text-secondary)'};">${row.Referral_Remaining ?? 5}</span></td>
            <td>
                <div class="status-select-wrapper ${cleanStatus}">
                    <select class="status-inline-select" onchange="updateStatus('referral', ${row.JobID}, this.value)">
                        ${statusOptionsHtml}
                    </select>
                </div>
            </td>
            <td>${row.CreatedDateTime || ""}</td>
            <td style="text-align: center;">
                <div style="display: flex; gap: 8px; justify-content: center;">
                    <button class="table-action-btn btn-edit" onclick="showEditReferralModal(${row.JobID}, '${encCompany}', '${encUrl}', '${encShorten}', '${encKeyword}', '${encPosition}', '${encStatus}')" title="Edit record">
                        <i class="fa-solid fa-pen-to-square"></i>
                    </button>
                    <button class="table-action-btn btn-delete" onclick="deleteRow('referral', ${row.JobID})" title="Delete job">
                        <i class="fa-solid fa-trash-can"></i>
                    </button>
                </div>
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
    const companyFilter = document.getElementById('filter-col-company') ? document.getElementById('filter-col-company').value.toLowerCase().trim() : '';
    const experienceFilter = document.getElementById('filter-col-experience') ? document.getElementById('filter-col-experience').value.toLowerCase().trim() : '';
    const locationFilter = document.getElementById('filter-col-location') ? document.getElementById('filter-col-location').value.toLowerCase().trim() : '';
    
    const allData = dbData['scraper'] || [];
    
    // 1. Filter
    const filtered = allData.filter(row => {
        const matchesId = !idFilter || String(row.ID || '').toLowerCase().includes(idFilter);
        const matchesEmail = !emailFilter || String(row.Email || '').toLowerCase().includes(emailFilter);
        const matchesStatus = !statusFilter || String(row.Status || '').toLowerCase().trim() === statusFilter;
        const matchesKeyword = !keywordFilter || String(row.Keyword || '').toLowerCase().trim() === keywordFilter;
        const matchesCompany = !companyFilter || String(row.CompanyName || '').toLowerCase().includes(companyFilter);
        const matchesExperience = !experienceFilter || String(row.Experience || '').toLowerCase().includes(experienceFilter);
        const matchesLocation = !locationFilter || String(row.Location || '').toLowerCase().includes(locationFilter);
        
        let matchesTimestamp = true;
        if (timestampFilter) {
            matchesTimestamp = String(row.Timestamp || '').toLowerCase().includes(timestampFilter);
        }
        
        return matchesId && matchesEmail && matchesStatus && matchesKeyword && matchesTimestamp && matchesCompany && matchesExperience && matchesLocation;
    });
    
    // 2. Sort by ID ascending (incremental by default)
    filtered.sort((a, b) => {
        const idA = parseInt(a.ID) || 0;
        const idB = parseInt(b.ID) || 0;
        return idA - idB;
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
            tbody.innerHTML = `<tr><td colspan="10" class="table-empty">No matching records found.</td></tr>`;
            renderScraperPaginationControls(filtered.length);
            return;
        }
        
        pageData.forEach(row => {
            const tr = document.createElement('tr');
            
            const statusClean = String(row.Status || 'New').toLowerCase().trim();
            const badgeClass = `badge-${statusClean}`;
            const statusHtml = `<span class="badge ${badgeClass}">${statusClean.toUpperCase()}</span>`;
            
            const escapedEmail = String(row.Email || '').replace(/'/g, "\\'");
            const escapedStatus = String(row.Status || '').replace(/'/g, "\\'");
            const escapedKeyword = String(row.Keyword || '').replace(/'/g, "\\'");
            const escapedPostUrl = String(row.PostURL || '').replace(/'/g, "\\'");
            const escapedCompany = String(row.CompanyName || '').replace(/'/g, "\\'");
            const escapedExperience = String(row.Experience || '').replace(/'/g, "\\'");
            const escapedLocation = String(row.Location || '').replace(/'/g, "\\'");
            
            // Render Post URL as a clickable link if present
            const postUrlHtml = row.PostURL
                ? `<a href="${row.PostURL}" target="_blank" rel="noopener noreferrer" title="${row.PostURL}" style="color: var(--accent-primary); font-size: 12px;"><i class="fa-solid fa-arrow-up-right-from-square"></i> View Post</a>`
                : `<span style="color: var(--text-muted); font-size: 12px;">—</span>`;
            
            tr.innerHTML = `
                <td>${row.ID || ""}</td>
                <td><strong>${row.Email || ""}</strong></td>
                <td>${statusHtml}</td>
                <td>${row.Keyword || ""}</td>
                <td>${row.Timestamp ? formatDisplayDate(row.Timestamp) : ""}</td>
                <td>${postUrlHtml}</td>
                <td>${row.CompanyName || "<span style='color:var(--text-muted)'>—</span>"}</td>
                <td>${row.Experience || "<span style='color:var(--text-muted)'>—</span>"}</td>
                <td>${row.Location || "<span style='color:var(--text-muted)'>—</span>"}</td>
                <td style="text-align: center;">
                    <div style="display: flex; gap: 8px; justify-content: center;">
                        <button class="table-action-btn btn-edit" onclick="showEditScraperModal(${row.ID}, '${escapedEmail}', '${escapedStatus}', '${escapedKeyword}', '${escapedPostUrl}', '${escapedCompany}', '${escapedExperience}', '${escapedLocation}')" title="Edit record">
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

function renderReferralPaginationControls(totalRecords) {
    const container = document.getElementById('referral-pagination');
    if (!container) return;
    
    const totalPages = Math.ceil(totalRecords / referralRecordsPerPage) || 1;
    
    const startRecord = totalRecords === 0 ? 0 : (referralCurrentPage - 1) * referralRecordsPerPage + 1;
    const endRecord = Math.min(referralCurrentPage * referralRecordsPerPage, totalRecords);
    
    let infoHtml = `<div class="pagination-info">Showing <strong>${startRecord}</strong> to <strong>${endRecord}</strong> of <strong>${totalRecords}</strong> records</div>`;
    
    let controlsHtml = `<div class="pagination-controls">`;
    const prevDisabled = referralCurrentPage === 1 ? 'disabled' : '';
    controlsHtml += `
        <button class="pagination-btn" onclick="changeReferralPage(${referralCurrentPage - 1})" ${prevDisabled}>
            <i class="fa-solid fa-chevron-left"></i> Prev
        </button>
    `;
    
    controlsHtml += `<div class="pagination-pages">`;
    for (let i = 1; i <= totalPages; i++) {
        if (totalPages <= 6 || i === 1 || i === totalPages || (i >= referralCurrentPage - 1 && i <= referralCurrentPage + 1)) {
            const activeClass = i === referralCurrentPage ? 'active' : '';
            controlsHtml += `<button class="pagination-page-btn ${activeClass}" onclick="changeReferralPage(${i})">${i}</button>`;
        } else if (i === 2 && referralCurrentPage > 3) {
            controlsHtml += `<span style="color: var(--text-secondary); padding: 0 4px;">...</span>`;
            i = referralCurrentPage - 2;
        } else if (i === referralCurrentPage + 2 && referralCurrentPage < totalPages - 2) {
            controlsHtml += `<span style="color: var(--text-secondary); padding: 0 4px;">...</span>`;
            i = totalPages - 1;
        }
    }
    controlsHtml += `</div>`;
    
    const nextDisabled = referralCurrentPage === totalPages ? 'disabled' : '';
    controlsHtml += `
        <button class="pagination-btn" onclick="changeReferralPage(${referralCurrentPage + 1})" ${nextDisabled}>
            Next <i class="fa-solid fa-chevron-right"></i>
        </button>
    `;
    controlsHtml += `</div>`;
    
    container.innerHTML = infoHtml + controlsHtml;
}

function changeReferralPage(page) {
    referralCurrentPage = page;
    applyFilters('referral');
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
        const url = type === 'referrals' ? '/api/data/delete_referral_row' : '/api/data/delete_row';
        const body = type === 'referrals' ? { "id": id } : { "db_type": type, "id": id };
        const response = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
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
let userDetails = {};
let scraperSearchKeywords = [];
let scraperTitleKeywords = [];
let connectSearchKeywords = [];
let connectTitleKeywords = [];
let scraperExcludedKeywords = [];
let connectExcludedKeywords = [];
let cachedConfig = {};

// Helper to get 1 or 2 initials from a username
function getUserInitials(name) {
    // If we have profile details loaded, use first/last name to calculate initials
    if (name && userDetails[name]) {
        const details = userDetails[name];
        if (details.first_name || details.last_name) {
            const first = details.first_name ? details.first_name.trim().charAt(0) : '';
            const last = details.last_name ? details.last_name.trim().charAt(0) : '';
            if (first || last) {
                return (first + last).toUpperCase();
            }
        }
    }
    if (!name) return 'U';
    const parts = name.trim().split(/[\s\._\-]+/);
    const validParts = parts.filter(p => p.length > 0);
    if (validParts.length === 0) return 'U';
    if (validParts.length === 1) {
        const word = validParts[0];
        return word.length > 1 ? word.slice(0, 2).toUpperCase() : word.charAt(0).toUpperCase();
    }
    return (validParts[0].charAt(0) + validParts[validParts.length - 1].charAt(0)).toUpperCase();
}

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
    
    // Active profile always floats to top; rest sorted alphabetically
    const sorted = [...filtered].sort((a, b) => {
        if (a === activeUser) return -1;
        if (b === activeUser) return 1;
        return a.toLowerCase().localeCompare(b.toLowerCase());
    });
    
    sorted.forEach(user => {
        const option = document.createElement('div');
        const initials = getUserInitials(user);
        option.className = `searchable-select-option ${user === activeUser ? 'selected' : ''}`;
        
        let displayName = user;
        if (userDetails[user]) {
            const details = userDetails[user];
            displayName = [details.first_name, details.last_name].filter(Boolean).join(' ').trim() || user;
        }
        
        option.innerHTML = `
            <div class="option-avatar-circle">${initials}</div>
            <span>${displayName}</span>
            ${user === activeUser ? '<i class="fa-solid fa-check option-check-icon"></i>' : ''}
        `;
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
            // Force a fully fresh reload (bypass_cache=true) so we get the switched user's data
            cachedConfig = null;
            await loadUsers();
            await loadSettings();
            // Navigate to dashboard
            const dashboardTab = document.querySelector('.nav-menu .nav-item[data-tab="dashboard"]');
            if (dashboardTab) dashboardTab.click();
            // Show brief switch confirmation toast
            const toast = document.createElement('div');
            toast.style.cssText = `
                position: fixed; bottom: 30px; right: 30px; z-index: 9999;
                background: linear-gradient(135deg, #6366f1, #4f46e5);
                color: white; padding: 14px 20px; border-radius: 10px;
                font-size: 0.9rem; font-weight: 600; box-shadow: 0 8px 32px rgba(99,102,241,0.3);
                display: flex; align-items: center; gap: 10px;
                animation: slideInRight 0.3s ease;
            `;
            toast.innerHTML = `<i class="fa-solid fa-user-check"></i> Switched to <strong>${username}</strong>`;
            document.body.appendChild(toast);
            setTimeout(() => toast.remove(), 3000);
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
            // Refresh user list in the dropdown without switching active user
            await loadUsers();
            // Show a brief toast/notification instead of switching profile
            const toast = document.createElement('div');
            toast.style.cssText = `
                position: fixed; bottom: 30px; right: 30px; z-index: 9999;
                background: linear-gradient(135deg, #22c55e, #16a34a);
                color: white; padding: 14px 20px; border-radius: 10px;
                font-size: 0.9rem; font-weight: 600; box-shadow: 0 8px 32px rgba(34,197,94,0.3);
                display: flex; align-items: center; gap: 10px;
                animation: slideInRight 0.3s ease;
            `;
            toast.innerHTML = `<i class="fa-solid fa-user-plus"></i> Profile "<strong>${username}</strong>" created! Switch to it from the profile menu.`;
            document.body.appendChild(toast);
            setTimeout(() => toast.remove(), 4000);
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
        userDetails = data.user_details || {};
        
        // Compute active user display name (full name if available)
        let activeDisplayName = activeUser || 'Select Profile';
        if (activeUser && userDetails[activeUser]) {
            const details = userDetails[activeUser];
            activeDisplayName = [details.first_name, details.last_name].filter(Boolean).join(' ').trim() || activeUser;
        }
        document.getElementById('selected-user-display').innerText = activeDisplayName;
        
        // Update initials on circular triggers and headers
        const initials = getUserInitials(activeUser);
        const initEl1 = document.getElementById('selected-user-display-initials');
        if (initEl1) initEl1.textContent = initials;
        const initEl2 = document.getElementById('dropdown-user-avatar-initials');
        if (initEl2) initEl2.textContent = initials;
        
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
            // Initialize pipeline status for the active user
            await initPipelineStatus();
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

// Subtab navigation in Pipelines section
// Subtab navigation in Pipelines section
document.querySelectorAll('.pipeline-tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.pipeline-tab-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.pipeline-tab-pane').forEach(p => p.classList.remove('active'));
        
        btn.classList.add('active');
        const tabName = btn.getAttribute('data-pipeline-tab');
        const paneId = `pane-${tabName}`;
        const pane = document.getElementById(paneId);
        if (pane) {
            pane.classList.add('active');
        }

        // Switch active console log viewer when switching sub-tabs
        // Build the namespaced task ID for the active user
        let newTaskId = null;
        if (tabName === 'email-scraper') {
            newTaskId = `${activeUser}::scraper_pipeline`;
        } else if (tabName === 'referral-connect') {
            newTaskId = `${activeUser}::referral_pipeline`;
        } else if (tabName === 'recruiter-outreach') {
            newTaskId = `${activeUser}::recruiter_pipeline`;
        }
        
        if (newTaskId) {
            startPolling(newTaskId);
        }
    });
});

// Keywords tags rendering
function renderKeywords(type) {
    const container = document.getElementById(`${type}-keywords-container`);
    const inputField = document.getElementById(`${type}-tag-input`);
    if (!container || !inputField) return;

    let keywordsList;
    if (type === 'scraper-search') keywordsList = scraperSearchKeywords;
    else if (type === 'scraper-title') keywordsList = scraperTitleKeywords;
    else if (type === 'connect-search') keywordsList = connectSearchKeywords;
    else if (type === 'connect-title') keywordsList = connectTitleKeywords;
    else if (type === 'scraper-excluded') keywordsList = scraperExcludedKeywords;
    else if (type === 'connect-excluded') keywordsList = connectExcludedKeywords;
    else return;
    
    // Clear old tags
    const oldTags = container.querySelectorAll('.tag-badge, .tag-badge-excluded');
    oldTags.forEach(el => el.remove());
    
    // Render current tags
    const isExcluded = type.endsWith('-excluded');
    keywordsList.forEach((kw, index) => {
        const badge = document.createElement('div');
        badge.className = isExcluded ? 'tag-badge-excluded' : 'tag-badge';
        badge.innerHTML = `
            <span>${kw}</span>
            <i class="fa-solid fa-xmark btn-remove-tag" onclick="removeKeyword('${type}', ${index})"></i>
        `;
        container.insertBefore(badge, inputField);
    });
}

// Immediately save keywords to backend JSON files - NOW DISABLED, updates unsaved state in UI instead
function saveKeywordsToBackend(type) {
    if (type.startsWith('scraper')) {
        updateTabUnsavedState('scraper', true);
    } else if (type.startsWith('connect')) {
        updateTabUnsavedState('connect', true);
    }
}

function addKeyword(type) {
    const inputField = document.getElementById(`${type}-tag-input`);
    if (!inputField) return;
    const value = inputField.value.trim();
    if (!value) return;
    
    let keywordsList;
    if (type === 'scraper-search') keywordsList = scraperSearchKeywords;
    else if (type === 'scraper-title') keywordsList = scraperTitleKeywords;
    else if (type === 'connect-search') keywordsList = connectSearchKeywords;
    else if (type === 'connect-title') keywordsList = connectTitleKeywords;
    else if (type === 'scraper-excluded') keywordsList = scraperExcludedKeywords;
    else if (type === 'connect-excluded') keywordsList = connectExcludedKeywords;
    else return;

    if (!keywordsList.includes(value)) {
        keywordsList.push(value);
        renderKeywords(type);
        saveKeywordsToBackend(type);
    }
    inputField.value = '';
}

function removeKeyword(type, index) {
    let keywordsList;
    if (type === 'scraper-search') keywordsList = scraperSearchKeywords;
    else if (type === 'scraper-title') keywordsList = scraperTitleKeywords;
    else if (type === 'connect-search') keywordsList = connectSearchKeywords;
    else if (type === 'connect-title') keywordsList = connectTitleKeywords;
    else if (type === 'scraper-excluded') keywordsList = scraperExcludedKeywords;
    else if (type === 'connect-excluded') keywordsList = connectExcludedKeywords;
    else return;

    keywordsList.splice(index, 1);
    renderKeywords(type);
    saveKeywordsToBackend(type);
}

// Inline Bulk paste keywords
function toggleBulkPaste(type) {
    const box = document.getElementById(`${type}-bulk-paste-box`);
    if (!box) return;
    box.classList.toggle('hidden');
    if (!box.classList.contains('hidden')) {
        let keywordsList;
        if (type === 'scraper-search') keywordsList = scraperSearchKeywords;
        else if (type === 'scraper-title') keywordsList = scraperTitleKeywords;
        else if (type === 'connect-search') keywordsList = connectSearchKeywords;
        else if (type === 'connect-title') keywordsList = connectTitleKeywords;
        else return;

        const textarea = document.getElementById(`${type}-bulk-paste-text`);
        if (textarea) {
            textarea.value = keywordsList.join(', ');
            textarea.focus();
        }
    }
}

function applyBulkKeywords(type) {
    const textarea = document.getElementById(`${type}-bulk-paste-text`);
    if (!textarea) return;
    const text = textarea.value;
    const splitKws = text.split(/,|\n/).map(k => k.trim()).filter(k => k.length > 0);
    
    if (type === 'scraper-search') {
        scraperSearchKeywords = splitKws;
    } else if (type === 'scraper-title') {
        scraperTitleKeywords = splitKws;
    } else if (type === 'connect-search') {
        connectSearchKeywords = splitKws;
    } else if (type === 'connect-title') {
        connectTitleKeywords = splitKws;
    } else {
        return;
    }
    renderKeywords(type);
    toggleBulkPaste(type);
    saveKeywordsToBackend(type);
}

// Inline Bulk paste excluded keywords
function toggleExcludedBulkPaste(type) {
    const box = document.getElementById(`${type}-excluded-bulk-paste-box`);
    if (!box) return;
    box.classList.toggle('hidden');
    if (!box.classList.contains('hidden')) {
        const keywordsList = type === 'scraper' ? scraperExcludedKeywords : connectExcludedKeywords;
        const textarea = document.getElementById(`${type}-excluded-bulk-paste-text`);
        if (textarea) {
            textarea.value = keywordsList.join(', ');
            textarea.focus();
        }
    }
}

function applyExcludedBulkKeywords(type) {
    const textarea = document.getElementById(`${type}-excluded-bulk-paste-text`);
    if (!textarea) return;
    const text = textarea.value;
    const splitKws = text.split(/,|\n/).map(k => k.trim()).filter(k => k.length > 0);
    
    if (type === 'scraper') {
        scraperExcludedKeywords = splitKws;
    } else {
        connectExcludedKeywords = splitKws;
    }
    renderKeywords(`${type}-excluded`);
    toggleExcludedBulkPaste(type);
    saveKeywordsToBackend(`${type}-excluded`);
}

// Switch email/connect templates between preview and edit mode
function switchTemplateMode(type, mode) {
    const editBtn = document.getElementById(`btn-mode-edit-${type}`);
    const previewBtn = document.getElementById(`btn-mode-preview-${type}`);
    const textarea = document.getElementById(`${type}-${type === 'scraper' ? 'email' : 'message'}-template`);
    const previewBox = document.getElementById(`${type}-template-preview`);
    const subjectContainer = document.getElementById('scraper-subject-container');
    
    if (mode === 'edit') {
        editBtn.classList.add('active');
        previewBtn.classList.remove('active');
        textarea.classList.remove('hidden');
        previewBox.classList.add('hidden');
        if (type === 'scraper' && subjectContainer) {
            subjectContainer.classList.remove('hidden');
        }
    } else {
        editBtn.classList.remove('active');
        previewBtn.classList.add('active');
        textarea.classList.add('hidden');
        previewBox.classList.remove('hidden');
        if (type === 'scraper' && subjectContainer) {
            subjectContainer.classList.add('hidden');
        }
        
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
        const noticePeriod = document.getElementById('profile-notice-period').value || 'Immediate';
        const lastWorkingDay = document.getElementById('profile-last-working-day').value || 'None';
        
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
            .replace(/{NOTICE_PERIOD}/g, noticePeriod)
            .replace(/{LAST_WORKING_DAY}/g, lastWorkingDay)
            // uppercase canonical tokens
            .replace(/{RECEIVER_NAME}/g, "John")
            .replace(/{COMPANY}/g, "Sample Company")
            .replace(/{JOB_URL}/g, "https://linkedin.com/jobs/view/12345")
            .replace(/{POST_URL}/g, "https://linkedin.com/posts/sample-post-12345")
            .replace(/{RESUME}/g, resumeUrl)
            // legacy lowercase aliases (for templates saved before renaming)
            .replace(/{resume}/g, resumeUrl)
            .replace(/{company}/g, "Sample Company")
            .replace(/{job_url}/g, "https://linkedin.com/jobs/view/12345")
            .replace(/{first_name}/g, "John")
            .replace(/{PERSON_NAME}/g, "John");
            
        if (type === 'scraper') {
            const rawSubject = document.getElementById('scraper-email-subject') ? document.getElementById('scraper-email-subject').value : '';
            let previewSubject = rawSubject
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
                .replace(/{NOTICE_PERIOD}/g, noticePeriod)
                .replace(/{LAST_WORKING_DAY}/g, lastWorkingDay);
            
            const subjectPreviewElement = document.getElementById('scraper-preview-subject-content');
            if (subjectPreviewElement) {
                subjectPreviewElement.innerText = previewSubject || "Referral Request – DBA Opportunity";
            }
        }

        const bodyContent = document.getElementById(`${type}-preview-body-content`);
        if (bodyContent) {
            bodyContent.innerText = previewHtml;
        } else {
            previewBox.innerText = previewHtml;
        }
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

function updateProfileDisplayCard(profile, username) {
    const fullName = [profile.first_name, profile.last_name].filter(Boolean).join(' ').trim() || username || 'Active Candidate';
    
    // Calculate initials
    let initials = 'U';
    if (profile.first_name || profile.last_name) {
        const first = profile.first_name ? profile.first_name.charAt(0) : '';
        const last = profile.last_name ? profile.last_name.charAt(0) : '';
        initials = (first + last).toUpperCase();
    } else if (username) {
        initials = username.charAt(0).toUpperCase();
    }
    
    const nameEl = document.getElementById('profile-display-name');
    if (nameEl) nameEl.textContent = fullName;
    
    const avatarEl = document.getElementById('profile-avatar-circle');
    if (avatarEl) avatarEl.textContent = initials;
    
    const locEl = document.getElementById('profile-display-loc-val');
    if (locEl) locEl.textContent = profile.current_location || 'Location not set';
    
    const expEl = document.getElementById('profile-display-exp-val');
    if (expEl) expEl.textContent = profile.experience || 'Experience not set';
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
        const recruiter = config.recruiter_outreach || {};
        const referralOutreach = config.referral_outreach || {};
        
        const setVal = (id, val) => {
            const el = document.getElementById(id);
            if (el) el.value = (val !== null && val !== undefined) ? String(val) : '';
        };
        const setChecked = (id, checked) => {
            const el = document.getElementById(id);
            if (!el) return;
            // Handle JS boolean, string "True"/"False", and "1"/"0"
            if (typeof checked === 'boolean') {
                el.checked = checked;
            } else if (typeof checked === 'string') {
                el.checked = checked.toLowerCase() === 'true' || checked === '1';
            } else {
                el.checked = Boolean(checked);
            }
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
        setVal('profile-notice-period', profile.notice_period);
        setVal('profile-last-working-day', profile.last_working_day);
        
        // Update visual profile display card
        updateProfileDisplayCard(profile, username);
        
        // Update cache and refresh top header switcher triggers/headers
        if (username) {
            userDetails[username] = {
                first_name: profile.first_name || "",
                last_name: profile.last_name || ""
            };
            const initials = getUserInitials(username);
            const initEl1 = document.getElementById('selected-user-display-initials');
            if (initEl1) initEl1.textContent = initials;
            const initEl2 = document.getElementById('dropdown-user-avatar-initials');
            if (initEl2) initEl2.textContent = initials;
            
            const fullName = [profile.first_name, profile.last_name].filter(Boolean).join(' ').trim() || username || 'Active Candidate';
            const nameEl = document.getElementById('selected-user-display');
            if (nameEl) nameEl.textContent = fullName;
        }
        
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
        setChecked('scraper-review-mode', scraper.review_mode);
        setVal('scraper-max-emails', scraper.max_emails_per_run || '5');
        setVal('scraper-email-template', scraper.email_template);
        setVal('scraper-email-subject', scraper.email_subject || '');
        
        scraperSearchKeywords = (scraper.search_keywords && scraper.search_keywords.length > 0) ? scraper.search_keywords : (scraper.keywords || []);
        renderKeywords('scraper-search');
        scraperTitleKeywords = (scraper.title_keywords && scraper.title_keywords.length > 0) ? scraper.title_keywords : (scraper.keywords || []);
        renderKeywords('scraper-title');
        scraperExcludedKeywords = scraper.excluded_keywords || [];
        renderKeywords('scraper-excluded');
        
        // 3. LinkedIn Connect fields
        setVal('connect-interval', connect.interval || '60');
        setChecked('connect-review-mode', connect.review_mode);
        setVal('connect-max-connections', connect.max_connections_per_company || connect.max_connections_per_run || '5');
        setVal('connect-message-template', connect.message_template);
        setVal('referral-message-template', referralOutreach.message_template || '');
        
        connectSearchKeywords = (connect.search_keywords && connect.search_keywords.length > 0) ? connect.search_keywords : (connect.keywords || []);
        renderKeywords('connect-search');
        connectTitleKeywords = (connect.title_keywords && connect.title_keywords.length > 0) ? connect.title_keywords : (connect.keywords || []);
        renderKeywords('connect-title');
        connectExcludedKeywords = connect.excluded_keywords || [];
        renderKeywords('connect-excluded');

        // 4. Recruiter Outreach fields
        setVal('recruiter-interval', recruiter.interval || '120');
        setVal('recruiter-target-count', recruiter.target_count || '2');
        setChecked('recruiter-review-mode', recruiter.review_mode);
        setVal('recruiter-message-template', recruiter.message_template);
        setVal('recruiter-direct-message-template', recruiter.direct_message_template || '');


        // Reset Template mode displays to Edit
        switchTemplateMode('connect', 'edit');
        switchTemplateMode('referral', 'edit');
        switchTemplateMode('recruiter', 'edit');
        switchTemplateMode('recruiter-direct', 'edit');


        // Update character counter for connection template
        if (typeof updateConnectCharCount === 'function') updateConnectCharCount();
        if (typeof updateReferralCharCount === 'function') updateReferralCharCount();
        if (typeof updateRecruiterCharCount === 'function') updateRecruiterCharCount();
        if (typeof updateRecruiterDirectCharCount === 'function') updateRecruiterDirectCharCount();


        // 4. Global settings
        setVal('setting-linkedin-email', globalSettings.linkedin_email);
        setVal('setting-linkedin-password', globalSettings.linkedin_password);
        setVal('setting-search-location', globalSettings.search_location);
        setVal('setting-search-time', globalSettings.search_time_range);
        setChecked('setting-dry-run', globalSettings.dry_run);
        setVal('setting-smtp-password', globalSettings.smtp_password);
        
        // Google Sheets Database configuration
        setVal('setting-database-type', globalSettings.database_type || 'local');
        setVal('setting-google-sheet-url', globalSettings.google_sheet_url || '');
        setVal('setting-google-credentials-json', globalSettings.google_credentials_json || '');
        if (typeof toggleGoogleSheetsFields === 'function') toggleGoogleSheetsFields();
        if (typeof updateActiveStorageIndicator === 'function') updateActiveStorageIndicator(globalSettings.database_type || 'local');
        
        // Reset unsaved indicators
        updateTabUnsavedState('scraper', false);
        updateTabUnsavedState('connect', false);
        updateTabUnsavedState('recruiter', false);
        
    } catch (e) {
        console.error("Failed to load settings:", e);
    }
}

// Save active profile configuration form
async function saveSettingsForm(event) {
    if (event) event.preventDefault();
    
    const profileSaveStatus = document.getElementById('profile-save-status');
    if (profileSaveStatus) {
        profileSaveStatus.innerText = 'Saving profile...';
        profileSaveStatus.className = 'save-status';
    }
    
    const profile = cachedConfig.config?.profile || {};
    const emailScraper = cachedConfig.config?.email_scraper || {};
    const linkedinConnect = cachedConfig.config?.linkedin_connect || {};
    const recruiterOutreach = cachedConfig.config?.recruiter_outreach || {};
    const referralOutreach = cachedConfig.config?.referral_outreach || {};
    const globalSettings = cachedConfig.global_settings || {};
    
    const getVal = (id, fallback) => {
        const el = document.getElementById(id);
        return el ? el.value : fallback;
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
            "expected_ctc": getVal('profile-expected-ctc', profile.expected_ctc),
            "notice_period": getVal('profile-notice-period', profile.notice_period),
            "last_working_day": getVal('profile-last-working-day', profile.last_working_day)
        },
        "email_scraper": emailScraper,
        "linkedin_connect": linkedinConnect,
        "recruiter_outreach": recruiterOutreach,
        "referral_outreach": referralOutreach,
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
            "smtp_password": getVal('setting-smtp-password', globalSettings.smtp_password || ""),
            "database_type": getVal('setting-database-type', globalSettings.database_type || "local"),
            "google_sheet_url": getVal('setting-google-sheet-url', globalSettings.google_sheet_url || ""),
            "google_credentials_json": getVal('setting-google-credentials-json', globalSettings.google_credentials_json || "")
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
            if (profileSaveStatus) {
                profileSaveStatus.innerText = '✓ Profile successfully saved!';
                profileSaveStatus.className = 'save-status success';
                setTimeout(() => { profileSaveStatus.innerText = ''; }, 3000);
            }
            
            // Reload settings to refresh fields/labels
            await loadSettings();
        } else {
            if (profileSaveStatus) {
                profileSaveStatus.innerText = '✕ Error saving profile.';
                profileSaveStatus.className = 'save-status error';
            }
        }
    } catch (e) {
        console.error("Failed to save settings:", e);
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
    
    const originalData = dbData[type] || [];
    
    const filtered = originalData.filter(row => {
        // 1. Text Search
        let textMatch = true;
        if (searchVal) {
            if (type === 'scraper') {
                textMatch = (row.Email && row.Email.toLowerCase().includes(searchVal)) ||
                            (row.Keyword && row.Keyword.toLowerCase().includes(searchVal));
            } else {
                textMatch = (row.CompanyName && row.CompanyName.toLowerCase().includes(searchVal)) ||
                            (row.SearchKeyword && row.SearchKeyword.toLowerCase().includes(searchVal));
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
    
    if (type === 'referral') {
        // Sort referrals by JobID ascending (incremental by default)
        filtered.sort((a, b) => {
            const idA = parseInt(a.JobID) || 0;
            const idB = parseInt(b.JobID) || 0;
            return idA - idB;
        });

        const totalPages = Math.ceil(filtered.length / referralRecordsPerPage) || 1;
        if (referralCurrentPage > totalPages) {
            referralCurrentPage = totalPages;
        }
        if (referralCurrentPage < 1) {
            referralCurrentPage = 1;
        }

        const startIndex = (referralCurrentPage - 1) * referralRecordsPerPage;
        const pageData = filtered.slice(startIndex, startIndex + referralRecordsPerPage);

        renderTable(type, pageData);
        renderReferralPaginationControls(filtered.length);
    } else {
        renderTable(type, filtered);
    }
}

// Bind listeners to Scraper column header filters
bindScraperColumnFilters();

// Bind listeners to Referral Database filters
document.getElementById('search-referral').addEventListener('input', () => {
    referralCurrentPage = 1;
    applyFilters('referral');
});
document.getElementById('filter-status-referral').addEventListener('change', () => {
    referralCurrentPage = 1;
    applyFilters('referral');
});
document.getElementById('filter-date-referral').addEventListener('change', () => {
    referralCurrentPage = 1;
    applyFilters('referral');
});

// Bind listeners to Referral Outreach Database filters
const searchRef = document.getElementById('search-referrals-outreach');
if (searchRef) {
    searchRef.addEventListener('input', () => {
        referralsCurrentPage = 1;
        applyReferralsFiltersAndRender();
    });
}
const filterStatusRef = document.getElementById('filter-status-referrals-outreach');
if (filterStatusRef) {
    filterStatusRef.addEventListener('change', () => {
        referralsCurrentPage = 1;
        applyReferralsFiltersAndRender();
    });
}
const filterSourceRef = document.getElementById('filter-source-referrals-outreach');
if (filterSourceRef) {
    filterSourceRef.addEventListener('change', () => {
        referralsCurrentPage = 1;
        applyReferralsFiltersAndRender();
    });
}


// Check if any pipeline is running on startup to restore log viewer state
async function checkActiveTasks() {
    try {
        const response = await fetch('/api/tasks');
        const tasks = await response.json();
        
        let foundRunning = false;
        for (let tid in tasks) {
            if (tasks[tid].status === 'running' || tasks[tid].status === 'queued') {
                startPolling(tid);
                foundRunning = true;
                
                // Auto-activate the sub-tab corresponding to the running task
                const pipelinePrefix = tid.replace('_pipeline', '').replace(/_/g, '-');
                let tabName = '';
                if (pipelinePrefix === 'scraper') tabName = 'email-scraper';
                else if (pipelinePrefix === 'referral') tabName = 'referral-connect';
                else if (pipelinePrefix === 'recruiter') tabName = 'recruiter-outreach';
                
                if (tabName) {
                    const tabBtn = document.querySelector(`.pipeline-tab-btn[data-pipeline-tab="${tabName}"]`);
                    if (tabBtn) {
                        // Click it to switch view and switch logs console
                        tabBtn.click();
                    }
                }
                break;
            }
        }
        
        if (!foundRunning) {
            setGlobalPipelineLock(null);
            loadStats();
        }
    } catch (e) {
        console.error("Failed to check active processes:", e);
        setGlobalPipelineLock(null);
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
const scraperSearchTagInput = document.getElementById('scraper-search-tag-input');
if (scraperSearchTagInput) {
    scraperSearchTagInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            addKeyword('scraper-search');
        }
    });
    scraperSearchTagInput.addEventListener('blur', () => addKeyword('scraper-search'));
}

const scraperTitleTagInput = document.getElementById('scraper-title-tag-input');
if (scraperTitleTagInput) {
    scraperTitleTagInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            addKeyword('scraper-title');
        }
    });
    scraperTitleTagInput.addEventListener('blur', () => addKeyword('scraper-title'));
}

const connectSearchTagInput = document.getElementById('connect-search-tag-input');
if (connectSearchTagInput) {
    connectSearchTagInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            addKeyword('connect-search');
        }
    });
    connectSearchTagInput.addEventListener('blur', () => addKeyword('connect-search'));
}

const connectTitleTagInput = document.getElementById('connect-title-tag-input');
if (connectTitleTagInput) {
    connectTitleTagInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            addKeyword('connect-title');
        }
    });
    connectTitleTagInput.addEventListener('blur', () => addKeyword('connect-title'));
}

const scraperExcludedTagInput = document.getElementById('scraper-excluded-tag-input');
if (scraperExcludedTagInput) {
    scraperExcludedTagInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            addKeyword('scraper-excluded');
        }
    });
    scraperExcludedTagInput.addEventListener('blur', () => addKeyword('scraper-excluded'));
}

const connectExcludedTagInput = document.getElementById('connect-excluded-tag-input');
if (connectExcludedTagInput) {
    connectExcludedTagInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            addKeyword('connect-excluded');
        }
    });
    connectExcludedTagInput.addEventListener('blur', () => addKeyword('connect-excluded'));
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

const DEFAULT_EMAIL_TEMPLATE = ``;

const DEFAULT_CONNECT_TEMPLATE = ``;

let unsavedChanges = {
    scraper: false,
    connect: false,
    recruiter: false
};

function updateTabUnsavedState(module, hasUnsaved) {
    unsavedChanges[module] = hasUnsaved;
    const dot = document.getElementById(`unsaved-dot-${module}`);
    if (dot) {
        if (hasUnsaved) {
            dot.classList.remove('hidden');
        } else {
            dot.classList.add('hidden');
        }
    }
}

function normalizeReferralSource(source) {
    if (!source) return "Existing Employee";
    const src = source.toLowerCase().trim();
    
    // Check recruiter first
    if (src.includes('recruiter')) {
        if (src.includes('sent')) {
            return "Sent Recruiter Connection";
        }
        return "Existing Recruiter";
    }
    
    // Then check employee
    if (src.includes('sent')) {
        return "Sent Employee Connection";
    }
    return "Existing Employee"; // fallback for existing employee
}

async function saveConfiguration(module) {
    const statusEl = document.getElementById(`save-status-${module}`);
    if (statusEl) {
        statusEl.innerText = 'Saving configuration...';
        statusEl.className = 'save-status';
    }

    // Read form values
    const getVal = (id) => {
        const el = document.getElementById(id);
        return el ? el.value : '';
    };
    const getChecked = (id) => {
        const el = document.getElementById(id);
        return el ? el.checked : false;
    };

    // Make sure cachedConfig structure is initialized
    if (!cachedConfig) cachedConfig = {};
    if (!cachedConfig.config) cachedConfig.config = {};
    if (!cachedConfig.config.profile) cachedConfig.config.profile = {};
    if (!cachedConfig.config.email_scraper) cachedConfig.config.email_scraper = {};
    if (!cachedConfig.config.linkedin_connect) cachedConfig.config.linkedin_connect = {};
    if (!cachedConfig.config.recruiter_outreach) cachedConfig.config.recruiter_outreach = {};
    if (!cachedConfig.config.referral_outreach) cachedConfig.config.referral_outreach = {};
    if (!cachedConfig.global_settings) cachedConfig.global_settings = {};

    // Validate and update cachedConfig locally depending on the module
    if (module === 'scraper') {
        const maxEmailsVal = parseInt(getVal('scraper-max-emails'), 10);
        if (isNaN(maxEmailsVal) || maxEmailsVal < 1 || maxEmailsVal > 100) {
            showSaveError(statusEl, '✕ Target Emails per Run must be between 1 and 100.');
            return;
        }
        
        cachedConfig.config.email_scraper = {
            "sender_email": cachedConfig.config.email_scraper.sender_email || "",
            "interval": getVal('scraper-interval'),
            "review_mode": getChecked('scraper-review-mode'),
            "max_emails_per_run": maxEmailsVal.toString(),
            "search_keywords": scraperSearchKeywords,
            "title_keywords": scraperTitleKeywords,
            "keywords": scraperSearchKeywords,
            "excluded_keywords": scraperExcludedKeywords,
            "email_subject": getVal('scraper-email-subject'),
            "email_template": getVal('scraper-email-template')
        };
    } else if (module === 'connect') {
        const maxConnsVal = parseInt(getVal('connect-max-connections'), 10);
        if (isNaN(maxConnsVal) || maxConnsVal < 1 || maxConnsVal > 100) {
            showSaveError(statusEl, '✕ Target Connections Per Company must be between 1 and 100.');
            return;
        }
        const noteTemplate = getVal('connect-message-template');
        if (noteTemplate.length > 300) {
            showSaveError(statusEl, '✕ LinkedIn Invite Note Template cannot exceed 300 characters.');
            return;
        }

        cachedConfig.config.linkedin_connect = {
            "interval": getVal('connect-interval') || '60',
            "review_mode": getChecked('connect-review-mode'),
            "max_connections_per_company": maxConnsVal.toString(),
            "max_connections_per_run": maxConnsVal.toString(),
            "search_keywords": connectSearchKeywords,
            "title_keywords": connectTitleKeywords,
            "keywords": connectSearchKeywords,
            "excluded_keywords": connectExcludedKeywords,
            "message_template": noteTemplate
        };
        cachedConfig.config.referral_outreach = {
            "message_template": getVal('referral-message-template')
        };
    } else if (module === 'recruiter') {
        const targetCountVal = parseInt(getVal('recruiter-target-count'), 10);
        if (isNaN(targetCountVal) || targetCountVal < 1 || targetCountVal > 100) {
            showSaveError(statusEl, '✕ Target Count must be between 1 and 100.');
            return;
        }
        const recruiterTemplate = getVal('recruiter-message-template');
        if (recruiterTemplate.length > 1000) {
            showSaveError(statusEl, '✕ Recruiter Message Template cannot exceed 1000 characters.');
            return;
        }
        const recruiterDirectTemplate = getVal('recruiter-direct-message-template');
        if (recruiterDirectTemplate.length > 1000) {
            showSaveError(statusEl, '✕ Recruiter Direct Message Template cannot exceed 1000 characters.');
            return;
        }

        cachedConfig.config.recruiter_outreach = {
            "interval": cachedConfig.config.recruiter_outreach?.interval || '120',
            "target_count": targetCountVal.toString(),
            "review_mode": getChecked('recruiter-review-mode'),
            "message_template": recruiterTemplate,
            "direct_message_template": recruiterDirectTemplate
        };
    } else if (module === 'cloud-db') {
        const dbType = getVal('setting-database-type');
        const sheetUrl = getVal('setting-google-sheet-url').trim();
        const credsJson = getVal('setting-google-credentials-json').trim();
        
        if (dbType === 'google_sheets') {
            if (!sheetUrl) {
                showSaveError(statusEl, '✕ Google Sheet URL is required.');
                return;
            }
            const sheetUrlRegex = /^https:\/\/docs\.google\.com\/spreadsheets\/d\/[a-zA-Z0-9-_]+\/?.*/ ;
            if (!sheetUrlRegex.test(sheetUrl)) {
                showSaveError(statusEl, '✕ Google Sheet URL is invalid. It must look like: https://docs.google.com/spreadsheets/d/spreadsheetId/edit');
                return;
            }
            if (!credsJson) {
                showSaveError(statusEl, '✕ Google Service Account Credentials JSON is required.');
                return;
            }
            try {
                const parsed = JSON.parse(credsJson);
                if (parsed.type !== 'service_account' || !parsed.client_email || !parsed.private_key) {
                    showSaveError(statusEl, '✕ Google Credentials JSON is missing key service account fields (type, client_email, or private_key).');
                    return;
                }
            } catch (e) {
                showSaveError(statusEl, '✕ Google Credentials must be a valid JSON format string.');
                return;
            }
        }

        const currentDbType = cachedConfig.global_settings?.database_type || 'local';
        const storageChanged = currentDbType !== dbType;

        // Update local cache always
        cachedConfig.global_settings.database_type = dbType;
        cachedConfig.global_settings.google_sheet_url = sheetUrl;
        cachedConfig.global_settings.google_credentials_json = credsJson;

        if (storageChanged) {
            // Storage type changed — run migration via streaming endpoint
            const globalSettingsPayload = { ...cachedConfig.global_settings };
            await runStorageMigration(dbType, globalSettingsPayload, statusEl, module);
            return; // runStorageMigration handles the rest (loadSettings, updateTabUnsavedState)
        }

        // No storage change — fall through to normal save below
    }

    // Now post the FULL config body
    const body = {
        "profile": cachedConfig.config.profile,
        "email_scraper": cachedConfig.config.email_scraper,
        "linkedin_connect": cachedConfig.config.linkedin_connect,
        "recruiter_outreach": cachedConfig.config.recruiter_outreach,
        "referral_outreach": cachedConfig.config.referral_outreach,
        "global_settings": cachedConfig.global_settings
    };

    try {
        const response = await fetch('/api/users/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        const data = await response.json();
        if (data.status === 'success') {
            statusEl.innerText = '✓ Configuration successfully saved!';
            statusEl.className = 'save-status success';
            updateTabUnsavedState(module, false);
            setTimeout(() => { statusEl.innerText = ''; }, 3000);
            
            // Reload settings to refresh fields/labels
            await loadSettings();
        } else {
            showSaveError(statusEl, '✕ Error saving configurations.');
        }
    } catch (e) {
        console.error("Failed to save configuration:", e);
        showSaveError(statusEl, '✕ Failed to save configuration.');
    }
}

/**
 * Runs the storage type migration via the /api/config/storage/switch SSE endpoint.
 * Shows a live-progress modal while migration is in progress.
 */
async function runStorageMigration(newDbType, globalSettingsPayload, statusEl, module) {
    const directionLabel = newDbType === 'google_sheets'
        ? 'Local Excel  →  Google Sheets'
        : 'Google Sheets  →  Local Excel';

    showMigrationModal(directionLabel);

    try {
        const response = await fetch('/api/config/storage/switch', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                database_type: newDbType,
                global_settings: globalSettingsPayload
            })
        });

        if (!response.ok) {
            const err = await response.json().catch(() => ({ message: 'Server error' }));
            appendMigrationLog(`❌ Error: ${err.message}`, 'error');
            finishMigrationModal(false);
            if (statusEl) showSaveError(statusEl, '✕ Migration failed. See migration log.');
            return;
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let success = false;

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });

            // Parse SSE lines: "data: {...}\n\n"
            const lines = buffer.split('\n');
            buffer = lines.pop(); // keep incomplete last line

            for (const line of lines) {
                const trimmed = line.trim();
                if (!trimmed.startsWith('data:')) continue;
                try {
                    const event = JSON.parse(trimmed.slice(5).trim());
                    if (event.type === 'log') {
                        appendMigrationLog(event.message, 'log');
                    } else if (event.type === 'done') {
                        appendMigrationLog('✅ ' + event.message, 'success');
                        success = true;
                    } else if (event.type === 'error') {
                        appendMigrationLog('❌ ' + event.message, 'error');
                        success = false;
                    }
                } catch (_) { /* ignore parse errors on partial lines */ }
            }
        }

        finishMigrationModal(success);

        if (success) {
            if (statusEl) {
                statusEl.innerText = '✓ Storage migration complete!';
                statusEl.className = 'save-status success';
                setTimeout(() => { statusEl.innerText = ''; }, 4000);
            }
            updateTabUnsavedState(module, false);
            await loadSettings();
        } else {
            if (statusEl) showSaveError(statusEl, '✕ Migration encountered errors. Check the log.');
        }
    } catch (e) {
        console.error('Migration fetch error:', e);
        appendMigrationLog('❌ Network error: ' + e.message, 'error');
        finishMigrationModal(false);
        if (statusEl) showSaveError(statusEl, '✕ Migration failed (network error).');
    }
}

function showMigrationModal(directionLabel) {
    let modal = document.getElementById('migration-modal');
    if (!modal) {
        modal = document.createElement('div');
        modal.id = 'migration-modal';
        modal.innerHTML = `
<div class="migration-modal-backdrop">
  <div class="migration-modal-box">
    <div class="migration-modal-header">
      <span class="migration-modal-icon">🔄</span>
      <div>
        <h3 class="migration-modal-title">Migrating Data</h3>
        <p class="migration-modal-subtitle" id="migration-direction-label"></p>
      </div>
    </div>
    <div class="migration-log-container" id="migration-log-container"></div>
    <div class="migration-modal-footer">
      <div class="migration-spinner" id="migration-spinner"></div>
      <span class="migration-status-text" id="migration-status-text">Please wait, migration in progress...</span>
      <button class="migration-close-btn" id="migration-close-btn" style="display:none" onclick="hideMigrationModal()">Close</button>
    </div>
  </div>
</div>`;
        document.body.appendChild(modal);
    }
    document.getElementById('migration-direction-label').textContent = directionLabel;
    document.getElementById('migration-log-container').innerHTML = '';
    document.getElementById('migration-spinner').style.display = 'block';
    document.getElementById('migration-status-text').textContent = 'Please wait, migration in progress...';
    document.getElementById('migration-status-text').style.color = '';
    document.getElementById('migration-close-btn').style.display = 'none';
    modal.style.display = 'block';
}

function appendMigrationLog(message, type) {
    const container = document.getElementById('migration-log-container');
    if (!container) return;
    const line = document.createElement('div');
    line.className = `migration-log-line migration-log-${type}`;
    line.textContent = message;
    container.appendChild(line);
    container.scrollTop = container.scrollHeight;
}

function finishMigrationModal(success) {
    const spinner = document.getElementById('migration-spinner');
    const statusText = document.getElementById('migration-status-text');
    const closeBtn = document.getElementById('migration-close-btn');
    if (spinner) spinner.style.display = 'none';
    if (statusText) {
        statusText.textContent = success ? '✅ Migration completed successfully!' : '❌ Migration encountered errors.';
        statusText.style.color = success ? '#10b981' : '#ef4444';
    }
    if (closeBtn) closeBtn.style.display = 'inline-block';
}

function hideMigrationModal() {
    const modal = document.getElementById('migration-modal');
    if (modal) modal.style.display = 'none';
}

function showSaveError(statusEl, msg) {
    if (statusEl) {
        statusEl.innerText = msg;
        statusEl.className = 'save-status error';
    }
}

function insertToken(type, token) {
    if (token === undefined) {
        token = type;
        type = 'connect';
    }
    
    let targetId = '';
    if (type === 'scraper') {
        targetId = 'scraper-email-template';
    } else if (type === 'connect') {
        targetId = 'connect-message-template';
    } else if (type === 'referral') {
        targetId = 'referral-message-template';
    } else if (type === 'recruiter') {
        targetId = 'recruiter-message-template';
    } else if (type === 'recruiter-direct') {
        targetId = 'recruiter-direct-message-template';
    } else {
        targetId = `${type}-message-template`;
    }

    const el = document.getElementById(targetId);
    if (!el) return;
    const start = el.selectionStart;
    const end = el.selectionEnd;
    const text = el.value;
    el.value = text.substring(0, start) + token + text.substring(end);
    el.focus();
    el.selectionStart = el.selectionEnd = start + token.length;
    
    if (type === 'connect' && typeof updateConnectCharCount === 'function') {
        updateConnectCharCount();
    } else if (type === 'referral' && typeof updateReferralCharCount === 'function') {
        updateReferralCharCount();
    } else if (type === 'recruiter' && typeof updateRecruiterCharCount === 'function') {
        updateRecruiterCharCount();
    } else if (type === 'recruiter-direct' && typeof updateRecruiterDirectCharCount === 'function') {
        updateRecruiterDirectCharCount();
    }

    // Trigger unsaved state change since we inserted text
    if (type === 'scraper') {
        updateTabUnsavedState('scraper', true);
    } else if (type === 'connect' || type === 'referral') {
        updateTabUnsavedState('connect', true);
    } else if (type === 'recruiter' || type === 'recruiter-direct') {
        updateTabUnsavedState('recruiter', true);
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

function updateRecruiterCharCount() {
    const ta  = document.getElementById('recruiter-message-template');
    const ctr = document.getElementById('recruiter-char-count');
    if (!ta || !ctr) return;
    const len = ta.value.length;
    ctr.textContent = `${len} / 300`;
    ctr.style.color = len > 280 ? 'var(--accent-red)' : len > 240 ? 'var(--accent-yellow)' : 'var(--text-secondary)';
}

function updateRecruiterDirectCharCount() {
    const ta  = document.getElementById('recruiter-direct-message-template');
    const ctr = document.getElementById('recruiter-direct-char-count');
    if (!ta || !ctr) return;
    const len = ta.value.length;
    ctr.textContent = `${len} / 1000`;
    ctr.style.color = len > 950 ? 'var(--accent-red)' : len > 850 ? 'var(--accent-yellow)' : 'var(--text-secondary)';
}

function updateReferralCharCount() {
    const ta  = document.getElementById('referral-message-template');
    const ctr = document.getElementById('referral-char-count');
    if (!ta || !ctr) return;
    const len = ta.value.length;
    ctr.textContent = `${len} / 2000`;
    ctr.style.color = len > 1900 ? 'var(--accent-red)' : len > 1750 ? 'var(--accent-yellow)' : 'var(--text-secondary)';
}



// Initialise character counter whenever settings are loaded
const _origSwitchTemplate = window.switchTemplateMode;
const _origLoadSettings   = window.loadSettings;

// Keep char count in sync when the connect template textarea is loaded
document.addEventListener('DOMContentLoaded', () => {
    const ta = document.getElementById('connect-message-template');
    if (ta) ta.addEventListener('input', updateConnectCharCount);
    
    const recruiterTa = document.getElementById('recruiter-message-template');
    if (recruiterTa) recruiterTa.addEventListener('input', updateRecruiterCharCount);

    const recruiterDirectTa = document.getElementById('recruiter-direct-message-template');
    if (recruiterDirectTa) recruiterDirectTa.addEventListener('input', updateRecruiterDirectCharCount);
    
    const referralTa = document.getElementById('referral-message-template');
    if (referralTa) referralTa.addEventListener('input', updateReferralCharCount);
    
    // Set unsaved indicators on settings modification
    const scraperContainer = document.getElementById('subtab-email-scraper');
    if (scraperContainer) {
        ['input', 'change'].forEach(evtType => {
            scraperContainer.addEventListener(evtType, (e) => {
                if (e.target.id !== 'scraper-tag-input' && e.target.id !== 'scraper-excluded-tag-input') {
                    updateTabUnsavedState('scraper', true);
                }
            });
        });
    }

    const connectContainer = document.getElementById('subtab-linkedin-connect');
    if (connectContainer) {
        ['input', 'change'].forEach(evtType => {
            connectContainer.addEventListener(evtType, (e) => {
                if (e.target.id !== 'connect-tag-input' && e.target.id !== 'connect-excluded-tag-input') {
                    updateTabUnsavedState('connect', true);
                }
            });
        });
    }

    const recruiterContainer = document.getElementById('subtab-recruiter-outreach');
    if (recruiterContainer) {
        ['input', 'change'].forEach(evtType => {
            recruiterContainer.addEventListener(evtType, () => {
                updateTabUnsavedState('recruiter', true);
            });
        });
    }
    
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

function showEditScraperModal(id, email, status, keyword, postUrl, companyName, experience, location) {
    const idField = document.getElementById('edit-scraper-id');
    const emailField = document.getElementById('edit-scraper-email');
    const statusField = document.getElementById('edit-scraper-status');
    const keywordField = document.getElementById('edit-scraper-keyword');
    const postUrlField = document.getElementById('edit-scraper-post-url');
    const companyField = document.getElementById('edit-scraper-company');
    const experienceField = document.getElementById('edit-scraper-experience');
    const locationField = document.getElementById('edit-scraper-location');
    
    if (idField) idField.value = id;
    if (emailField) emailField.value = email;
    if (statusField) {
        let formattedStatus = 'New';
        const lower = status.toLowerCase();
        if (lower === 'sent') {
            formattedStatus = 'Sent';
        } else if (lower === 'skipped') {
            formattedStatus = 'Skipped';
        }
        statusField.value = formattedStatus;
    }
    if (keywordField) keywordField.value = keyword === 'None' || keyword === 'null' || !keyword ? '' : keyword;
    if (postUrlField) postUrlField.value = postUrl && postUrl !== 'None' && postUrl !== 'null' ? postUrl : '';
    if (companyField) companyField.value = companyName && companyName !== 'None' && companyName !== 'null' ? companyName : '';
    if (experienceField) experienceField.value = experience && experience !== 'None' && experience !== 'null' ? experience : '';
    if (locationField) locationField.value = location && location !== 'None' && location !== 'null' ? location : '';
    
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
    const post_url = document.getElementById('edit-scraper-post-url')?.value || '';
    const company_name = document.getElementById('edit-scraper-company')?.value || '';
    const experience = document.getElementById('edit-scraper-experience')?.value || '';
    const location = document.getElementById('edit-scraper-location')?.value || '';
    
    try {
        const response = await fetch('/api/data/edit_row', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                db_type: 'scraper',
                id: id,
                email: email,
                status: status,
                keyword: keyword,
                post_url: post_url,
                company_name: company_name,
                experience: experience,
                location: location
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

// ── Live Reload Helper (Development Only) ───────────────────────────────────
if (location.hostname === 'localhost' || location.hostname === '127.0.0.1') {
    const source = new EventSource('/api/dev-reload');
    source.onerror = function() {
        console.log("[Dev Reload] Connection lost. Server is restarting...");
        const checkServer = setInterval(() => {
            fetch('/api/users')
                .then(res => {
                    if (res.ok) {
                        clearInterval(checkServer);
                        console.log("[Dev Reload] Server is back online. Reloading...");
                        location.reload();
                    }
                })
                .catch(() => {});
        }, 800);
    };
}


// ── Referral Record Modal Triggers ──────────────────────────────────
function showEditReferralModal(id, encCompany, encUrl, encShorten, encKeyword, encPosition, encStatus) {
    document.getElementById('edit-referral-id').value = id;
    document.getElementById('edit-referral-company').value = decodeURIComponent(encCompany);
    document.getElementById('edit-referral-url').value = decodeURIComponent(encUrl);
    document.getElementById('edit-referral-shorten').value = decodeURIComponent(encShorten === 'None' || encShorten === 'null' || !encShorten ? '' : encShorten);
    document.getElementById('edit-referral-keyword').value = decodeURIComponent(encKeyword === 'None' || encKeyword === 'null' || !encKeyword ? '' : encKeyword);
    document.getElementById('edit-referral-position').value = decodeURIComponent(encPosition === 'None' || encPosition === 'null' || !encPosition ? '' : encPosition);
    document.getElementById('edit-referral-status').value = decodeURIComponent(encStatus).toLowerCase();
    
    const modal = document.getElementById('edit-referral-modal');
    if (modal) modal.classList.remove('hidden');
}

function hideEditReferralModal() {
    const modal = document.getElementById('edit-referral-modal');
    if (modal) modal.classList.add('hidden');
}

async function saveReferralEditForm(event) {
    if (event) event.preventDefault();
    
    const id = document.getElementById('edit-referral-id').value;
    const company = document.getElementById('edit-referral-company').value;
    const url = document.getElementById('edit-referral-url').value;
    const shorten = document.getElementById('edit-referral-shorten').value;
    const keyword = document.getElementById('edit-referral-keyword').value;
    const position = document.getElementById('edit-referral-position').value;
    const status = document.getElementById('edit-referral-status').value;
    
    try {
        const response = await fetch('/api/data/edit_row', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                db_type: 'referral',
                id: id,
                company: company,
                url: url,
                shorten: shorten,
                keyword: keyword,
                position: position,
                status: status
            })
        });
        const data = await response.json();
        if (data.status === 'success') {
            hideEditReferralModal();
            await loadTableData('referral');
        } else {
            alert(`Error updating record: ${data.message}`);
        }
    } catch (e) {
        console.error("Failed to save record:", e);
        alert("Failed to save changes. Please try again.");
    }
}

// ── Referral Contact Modal Triggers ──────────────────────────────────
function updateStatusSelectColor(selectEl) {
    if (!selectEl) return;
    selectEl.classList.remove(
        'status-select-pending', 'status-select-sent', 
        'status-select-failed', 'status-select-skipped', 'status-select-replied'
    );
    const val = selectEl.value.toLowerCase();
    if (val === 'pending') selectEl.classList.add('status-select-pending');
    else if (val === 'sent') selectEl.classList.add('status-select-sent');
    else if (val === 'failed') selectEl.classList.add('status-select-failed');
    else if (val === 'skipped') selectEl.classList.add('status-select-skipped');
    else if (val === 'replied') selectEl.classList.add('status-select-replied');
}

function showEditReferralContactModal(id, name, email, profileUrl, source, status, company, notes, verification, jobUrl) {
    document.getElementById('edit-referral-contact-id').value = id;
    document.getElementById('edit-referral-contact-name').value = decodeURIComponent(name);
    document.getElementById('edit-referral-contact-email').value = decodeURIComponent(email === 'None' || email === 'null' || !email ? '' : email);
    document.getElementById('edit-referral-contact-url').value = decodeURIComponent(profileUrl);
    document.getElementById('edit-referral-contact-source').value = normalizeReferralSource(decodeURIComponent(source));
    
    const statusEl = document.getElementById('edit-referral-contact-status');
    statusEl.value = decodeURIComponent(status || 'Pending');
    updateStatusSelectColor(statusEl);
    
    document.getElementById('edit-referral-contact-company').value = decodeURIComponent(company === 'None' || company === 'null' || !company ? '' : company);
    document.getElementById('edit-referral-contact-job-url').value = decodeURIComponent(jobUrl === 'None' || jobUrl === 'null' || !jobUrl ? '' : jobUrl);
    document.getElementById('edit-referral-contact-notes').value = decodeURIComponent(notes === 'None' || notes === 'null' || !notes ? '' : notes);
    
    const verificationVal = decodeURIComponent(verification || 'Verified');
    const verificationEl = document.getElementById('edit-referral-contact-verification');
    if (verificationEl) {
        verificationEl.value = verificationVal;
    }
    
    const modal = document.getElementById('edit-referral-contact-modal');
    if (modal) modal.classList.remove('hidden');
}

function hideEditReferralContactModal() {
    const modal = document.getElementById('edit-referral-contact-modal');
    if (modal) modal.classList.add('hidden');
}

async function saveReferralContactEditForm(event) {
    if (event) event.preventDefault();
    
    const id = document.getElementById('edit-referral-contact-id').value;
    const name = document.getElementById('edit-referral-contact-name').value;
    const email = document.getElementById('edit-referral-contact-email').value;
    const profile_url = document.getElementById('edit-referral-contact-url').value;
    const source = document.getElementById('edit-referral-contact-source').value;
    const status = document.getElementById('edit-referral-contact-status').value;
    const company = document.getElementById('edit-referral-contact-company').value;
    const job_url = document.getElementById('edit-referral-contact-job-url').value;
    const notes = document.getElementById('edit-referral-contact-notes').value;
    
    const verificationEl = document.getElementById('edit-referral-contact-verification');
    const verification = verificationEl ? verificationEl.value : 'Verified';
    
    try {
        const response = await fetch('/api/data/edit_referral_row', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                id: id,
                name: name,
                email: email,
                profile_url: profile_url,
                source: source,
                status: status,
                company: company,
                job_url: job_url,
                notes: notes,
                employment_verification_status: verification
            })
        });
        const data = await response.json();
        if (data.status === 'success') {
            hideEditReferralContactModal();
            await loadTableData('referrals');
        } else {
            alert(`Error updating contact: ${data.message}`);
        }
    } catch (e) {
        console.error("Failed to save contact:", e);
        alert("Failed to save changes. Please try again.");
    }
}

function renderReferralsPaginationControls(totalRecords) {
    const container = document.getElementById('referrals-outreach-pagination');
    if (!container) return;
    
    const totalPages = Math.ceil(totalRecords / referralsRecordsPerPage) || 1;
    
    const startRecord = totalRecords === 0 ? 0 : (referralsCurrentPage - 1) * referralsRecordsPerPage + 1;
    const endRecord = Math.min(referralsCurrentPage * referralsRecordsPerPage, totalRecords);
    
    let infoHtml = `<div class="pagination-info">Showing <strong>${startRecord}</strong> to <strong>${endRecord}</strong> of <strong>${totalRecords}</strong> records</div>`;
    
    let controlsHtml = `<div class="pagination-controls">`;
    const prevDisabled = referralsCurrentPage === 1 ? 'disabled' : '';
    controlsHtml += `
        <button class="pagination-btn" type="button" onclick="changeReferralsPage(${referralsCurrentPage - 1})" ${prevDisabled}>
            <i class="fa-solid fa-chevron-left"></i> Prev
        </button>
    `;
    
    controlsHtml += `<div class="pagination-pages">`;
    for (let i = 1; i <= totalPages; i++) {
        if (totalPages <= 6 || i === 1 || i === totalPages || (i >= referralsCurrentPage - 1 && i <= referralsCurrentPage + 1)) {
            const activeClass = i === referralsCurrentPage ? 'active' : '';
            controlsHtml += `<button class="pagination-page-btn ${activeClass}" type="button" onclick="changeReferralsPage(${i})">${i}</button>`;
        } else if (i === 2 && referralsCurrentPage > 3) {
            controlsHtml += `<span style="color: var(--text-secondary); padding: 0 4px;">...</span>`;
            i = referralsCurrentPage - 2;
        } else if (i === referralsCurrentPage + 2 && referralsCurrentPage < totalPages - 2) {
            controlsHtml += `<span style="color: var(--text-secondary); padding: 0 4px;">...</span>`;
            i = totalPages - 1;
        }
    }
    controlsHtml += `</div>`;
    
    const nextDisabled = referralsCurrentPage === totalPages ? 'disabled' : '';
    controlsHtml += `
        <button class="pagination-btn" type="button" onclick="changeReferralsPage(${referralsCurrentPage + 1})" ${nextDisabled}>
            Next <i class="fa-solid fa-chevron-right"></i>
        </button>
    `;
    controlsHtml += `</div>`;
    
    container.innerHTML = infoHtml + controlsHtml;
}

function changeReferralsPage(page) {
    referralsCurrentPage = page;
    applyReferralsFiltersAndRender();
}

// ── Two-way Synchronization: Excel-to-UI Poll ─────────────────────────────
setInterval(() => {
    // Only fetch updates if the user is not actively editing in a modal
    const isModalOpen = !document.getElementById('edit-scraper-modal').classList.contains('hidden') ||
                        (document.getElementById('edit-referral-modal') && !document.getElementById('edit-referral-modal').classList.contains('hidden')) ||
                        (document.getElementById('edit-referral-contact-modal') && !document.getElementById('edit-referral-contact-modal').classList.contains('hidden')) ||
                        document.querySelector('.modal-overlay:not(.hidden)');
    
    // Check if the user is focused on settings fields specifically
    const isEditingSettings = document.activeElement && 
                              (document.activeElement.tagName === 'INPUT' || 
                               document.activeElement.tagName === 'TEXTAREA' || 
                               document.activeElement.tagName === 'SELECT') &&
                              (document.activeElement.closest('.settings-card') ||
                               document.activeElement.closest('#settings-form') ||
                               document.activeElement.closest('#settings') ||
                               (document.activeElement.id && (
                                   document.activeElement.id.startsWith('scraper-') || 
                                   document.activeElement.id.startsWith('connect-') || 
                                   document.activeElement.id.startsWith('recruiter-') ||
                                   document.activeElement.id.startsWith('referral-')
                               )));
    
    // Check if the user is interacting with any input/select inside the tables
    const isInteractingWithTable = document.activeElement && 
                                  (document.activeElement.closest('.data-table') || 
                                   document.activeElement.closest('.table-responsive') || 
                                   document.activeElement.classList.contains('status-inline-select'));
    
    if (!isModalOpen && !isInteractingWithTable) {
        loadTableData('scraper');
        loadTableData('referral');
        loadTableData('referrals');
    }
}, 30000);

// Check pipeline status on page load to restore running state if active
async function initPipelineStatus() {
    try {
        const response = await fetch('/api/tasks');
        const tasks = await response.json();
        
        const pipelines = ['scraper', 'referral', 'recruiter'];
        
        // For each pipeline type, find a task that belongs to the active user.
        // Task IDs are namespaced as "{username}::pipeline_type".
        pipelines.forEach(p => {
            const pipelineKey = `${p}_pipeline`;
            const entry = Object.entries(tasks).find(
                ([tid, t]) => t.username === activeUser && tid.endsWith(`::${pipelineKey}`)
            );
            const taskId = entry ? entry[0] : null;
            const task = entry ? entry[1] : null;
            const isRunning = task && (task.status === 'running' || task.status === 'queued');
            
            // Set buttons visibility and lock state based on status
            const runBtn = document.getElementById(`btn-run-${p}`);
            const killBtn = document.getElementById(`btn-kill-${p}`);
            const badge = document.getElementById(`badge-${p}`);
            
            if (isRunning && taskId) {
                if (runBtn) runBtn.classList.add('hidden');
                if (killBtn) {
                    killBtn.classList.remove('hidden');
                    killBtn.disabled = false;
                    killBtn.dataset.taskId = taskId;  // Store for killPipeline()
                }
                startPolling(taskId);
            } else {
                if (runBtn) runBtn.classList.remove('hidden');
                if (killBtn) killBtn.classList.add('hidden');
                // If the active log view was polling a task for a different user, stop it
                if (activeTaskId && activeTaskId.endsWith(`::${pipelineKey}`) && !activeTaskId.startsWith(`${activeUser}::`)) {
                    stopPolling();
                    activeTaskId = null;
                    const consoleLogs = document.getElementById('console-logs');
                    if (consoleLogs) consoleLogs.innerHTML = '<div class="log-line system">Log channel idle. Select an active pipeline to view logs.</div>';
                }
            }
            
            if (badge) {
                const statusText = task ? task.status : 'idle';
                badge.innerText = statusText;
                badge.className = `status-badge status-${statusText}`;
            }
        });
        
        updatePipelineLocks();
    } catch (e) {
        console.error("Failed to initialize pipeline status on load:", e);
    }
}

// Run on page load
document.addEventListener('DOMContentLoaded', () => {
    initPipelineStatus();
});

function toggleGoogleSheetsFields() {
    const dbTypeEl = document.getElementById('setting-database-type');
    const sheetsGroup = document.getElementById('google-sheets-config-group');
    if (dbTypeEl && sheetsGroup) {
        if (dbTypeEl.value === 'google_sheets') {
            sheetsGroup.style.display = 'block';
        } else {
            sheetsGroup.style.display = 'none';
        }
    }
}

async function testSheetsConnection() {
    const testStatus = document.getElementById('sheets-test-status');
    const url = document.getElementById('setting-google-sheet-url').value.trim();
    const creds = document.getElementById('setting-google-credentials-json').value.trim();
    
    if (!url || !creds) {
        if (testStatus) {
            testStatus.innerText = '⚠️ Please fill in Sheet URL and Credentials JSON first.';
            testStatus.style.color = '#ef4444';
        }
        return;
    }
    
    if (testStatus) {
        testStatus.innerText = '⚡ Connecting to Google Sheets...';
        testStatus.style.color = '#38bdf8';
    }
    
    try {
        const response = await fetch('/api/config/sheets/test', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                google_sheet_url: url,
                google_credentials_json: creds
            })
        });
        const data = await response.json();
        if (data.status === 'success') {
            testStatus.innerText = '✅ Connection Successful! Worksheets verified.';
            testStatus.style.color = '#22c55e';
        } else {
            testStatus.innerText = `❌ Connection Failed: ${data.message}`;
            testStatus.style.color = '#ef4444';
        }
    } catch (e) {
        testStatus.innerText = `❌ Error: ${e.message}`;
        testStatus.style.color = '#ef4444';
    }
}

function updateActiveStorageIndicator(dbType) {
    const indicator = document.getElementById('active-storage-indicator');
    if (indicator) {
        const span = indicator.querySelector('span');
        const icon = indicator.querySelector('i');
        if (dbType === 'google_sheets') {
            indicator.className = 'active-storage-badge badge-sheets';
            if (span) span.innerText = 'Active Storage: Google Sheets';
            if (icon) icon.className = 'fa-solid fa-cloud';
        } else {
            indicator.className = 'active-storage-badge badge-local';
            if (span) span.innerText = 'Active Storage: Local Database';
            if (icon) icon.className = 'fa-solid fa-database';
        }
    }
}


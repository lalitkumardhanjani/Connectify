// ============================================================
//  Connectify Dashboard Analytics — dashboard.js
// ============================================================

const CHART_DEFAULTS = {
    plugins: {
        legend: { display: false },
        tooltip: {
            backgroundColor: 'rgba(10,8,19,0.92)',
            titleColor: '#e0e0e0',
            bodyColor: '#9ea4c0',
            borderColor: 'rgba(127,90,240,0.3)',
            borderWidth: 1,
            padding: 10,
        }
    }
};

const PALETTE = {
    cyan:   '#00b0ff',
    green:  '#00e676',
    yellow: '#ffb300',
    purple: '#7f5af0',
    teal:   '#2cb67d',
    red:    '#ff3d00',
    orange: '#ff6d00',
    pink:   '#f72585',
    indigo: '#7b2ff7',
    gray:   '#9ea4c0',
};

const BAR_COLORS = [
    PALETTE.cyan, PALETTE.purple, PALETTE.teal, PALETTE.yellow,
    PALETTE.green, PALETTE.pink,  PALETTE.orange, PALETTE.indigo,
];

// Active chart instances (so we can destroy and re-create cleanly)
let emailStatusChartInst   = null;
let emailKeywordChartInst  = null;
let emailDomainChartInst   = null;
let emailDailyChartInst    = null;
let coStatusChartInst      = null;
let coKeywordChartInst     = null;
let coHiringChartInst      = null;
let outreachStatusChartInst = null;
let outreachSourceChartInst = null;
let outreachDailyChartInst = null;

// Pending Queue Pagination State
let pendingCurrentPage = 1;
const pendingRecordsPerPage = 10;
let pendingQueueData = [];

// ─────────────────────────────────────────────────────────
//  Helpers
// ─────────────────────────────────────────────────────────
function fmt(n) {
    if (n === null || n === undefined) return '—';
    return Number(n).toLocaleString();
}

function pct(part, total) {
    if (!total) return '0%';
    return ((part / total) * 100).toFixed(1) + '%';
}

function rankClass(i) {
    if (i === 0) return 'gold';
    if (i === 1) return 'silver';
    if (i === 2) return 'bronze';
    return '';
}

function mkRow(...cells) {
    const tr = document.createElement('tr');
    cells.forEach(c => {
        const td = document.createElement('td');
        td.innerHTML = c;
        tr.appendChild(td);
    });
    return tr;
}

function emptyRow(cols, msg = 'No data available') {
    return `<tr><td colspan="${cols}" class="table-empty"><i class="fa-solid fa-database" style="opacity:0.3;margin-right:8px;"></i>${msg}</td></tr>`;
}

function progressBar(value, max) {
    const w = max ? Math.round((value / max) * 100) : 0;
    return `<div class="kw-bar-wrap">
        <div class="kw-bar-bg"><div class="kw-bar-fill" style="width:${w}%"></div></div>
        <span class="kw-pct">${w}%</span>
    </div>`;
}

// ─────────────────────────────────────────────────────────
//  Module tab switching
// ─────────────────────────────────────────────────────────
function switchDashModule(module) {
    ['email', 'company', 'outreach'].forEach(m => {
        const panel = document.getElementById(`dash-panel-${m}`);
        const tab = document.getElementById(`dash-module-${m}`);
        if (panel) panel.classList.remove('active');
        if (tab) tab.classList.remove('active');
    });
    const activePanel = document.getElementById(`dash-panel-${module}`);
    const activeTab = document.getElementById(`dash-module-${module}`);
    if (activePanel) activePanel.classList.add('active');
    if (activeTab) activeTab.classList.add('active');
}

// ─────────────────────────────────────────────────────────
//  Chart factory helpers
// ─────────────────────────────────────────────────────────
function makePieChart(canvasId, labels, data, colors) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return null;
    const ctx = canvas.getContext('2d');
    return new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels,
            datasets: [{
                data,
                backgroundColor: colors.map(c => c + '33'),
                borderColor: colors,
                borderWidth: 2,
                hoverOffset: 8,
            }]
        },
        options: {
            ...CHART_DEFAULTS,
            responsive: true,
            maintainAspectRatio: false,
            cutout: '68%',
            plugins: {
                ...CHART_DEFAULTS.plugins,
                legend: { display: false },
            }
        }
    });
}

function makeBarChart(canvasId, labels, data, color = PALETTE.purple) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return null;
    const ctx = canvas.getContext('2d');
    return new Chart(ctx, {
        type: 'bar',
        data: {
            labels,
            datasets: [{
                data,
                backgroundColor: BAR_COLORS.slice(0, labels.length).map(c => c + '55'),
                borderColor:     BAR_COLORS.slice(0, labels.length),
                borderWidth: 1.5,
                borderRadius: 6,
            }]
        },
        options: {
            ...CHART_DEFAULTS,
            responsive: true,
            maintainAspectRatio: false,
            indexAxis: 'y',
            scales: {
                x: {
                    grid: { color: 'rgba(255,255,255,0.04)' },
                    ticks: { color: '#9ea4c0', font: { size: 11 } }
                },
                y: {
                    grid: { display: false },
                    ticks: { color: '#e0e0e0', font: { size: 11 } }
                }
            }
        }
    });
}

function makeLineChart(canvasId, labels, data) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return null;
    const ctx = canvas.getContext('2d');
    const gradient = ctx.createLinearGradient(0, 0, 0, 200);
    gradient.addColorStop(0,   'rgba(0,176,255,0.35)');
    gradient.addColorStop(1,   'rgba(0,176,255,0.0)');
    return new Chart(ctx, {
        type: 'line',
        data: {
            labels,
            datasets: [{
                data,
                borderColor: PALETTE.cyan,
                borderWidth: 2,
                pointBackgroundColor: PALETTE.cyan,
                pointRadius: 4,
                pointHoverRadius: 6,
                fill: true,
                backgroundColor: gradient,
                tension: 0.4,
            }]
        },
        options: {
            ...CHART_DEFAULTS,
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: {
                    grid: { color: 'rgba(255,255,255,0.04)' },
                    ticks: { color: '#9ea4c0', font: { size: 11 } }
                },
                y: {
                    grid: { color: 'rgba(255,255,255,0.04)' },
                    ticks: { color: '#9ea4c0', font: { size: 11 } }
                }
            }
        }
    });
}

function renderLegend(containerId, labels, colors, data) {
    const el = document.getElementById(containerId);
    if (!el) return;
    const total = data.reduce((a, b) => a + b, 0);
    el.innerHTML = labels.map((lbl, i) => `
        <div class="legend-item">
            <span class="legend-dot" style="background:${colors[i]}"></span>
            <span class="legend-name">${lbl}</span>
            <span class="legend-pct">${pct(data[i], total)}</span>
        </div>
    `).join('');
}

// ─────────────────────────────────────────────────────────
//  MODULE 1 — Email Scraper Analytics
// ─────────────────────────────────────────────────────────
async function loadEmailDashboard() {
    let d;
    try {
        const res = await fetch('/api/email_stats');
        d = await res.json();
    } catch(e) {
        console.warn('Could not fetch email stats:', e);
        d = {
            total_emails: 0, sent: 0, pending: 0, added_today: 0,
            send_success_rate: 0.0, status_distribution: {}, domain_distribution: {},
            keyword_counts: {}, daily_counts: [], pending_queue: []
        };
    }

    // KPI cards
    document.getElementById('email-total').textContent   = fmt(d.total_emails);
    document.getElementById('email-sent').textContent    = fmt(d.sent);
    document.getElementById('email-pending').textContent = fmt(d.pending);
    document.getElementById('email-today').textContent   = fmt(d.added_today);
    document.getElementById('pending-count-badge').textContent = fmt(d.pending) + ' pending';

    const successRateEl = document.getElementById('email-success-rate');
    if (successRateEl) {
        successRateEl.textContent = (d.send_success_rate !== undefined ? d.send_success_rate : 0) + '% rate';
    }

    // Leaderboard
    const kwEntries = Object.entries(d.keyword_counts || {}).sort((a,b) => b[1]-a[1]);
    const topKw = kwEntries[0];
    document.getElementById('email-top-keyword').textContent =
        topKw ? `${topKw[0]}  —  ${fmt(topKw[1])} emails` : 'No data yet';

    // Status Pie Chart
    const sentVal    = d.sent    || 0;
    const pendingVal = d.pending || 0;
    const skippedVal = d.skipped || 0;
    const statusLabels = ['Sent', 'Pending', 'Skipped'];
    const statusData   = [sentVal, pendingVal, skippedVal];
    const statusColors = [PALETTE.cyan, PALETTE.yellow, PALETTE.gray];

    if (emailStatusChartInst) emailStatusChartInst.destroy();
    emailStatusChartInst = makePieChart('emailStatusChart', statusLabels, statusData, statusColors);
    renderLegend('email-status-legend', statusLabels, statusColors, statusData);

    // Keyword Bar Chart (top 8)
    const topKws = kwEntries.slice(0, 8);
    if (emailKeywordChartInst) emailKeywordChartInst.destroy();
    emailKeywordChartInst = makeBarChart(
        'emailKeywordChart',
        topKws.map(([k]) => k),
        topKws.map(([,v]) => v)
    );

    // Domain Doughnut Chart
    const domains = Object.entries(d.domain_distribution || {}).sort((a,b)=>b[1]-a[1]);
    const topDomains = domains.slice(0, 7);
    const otherDomainsCount = domains.slice(7).reduce((sum, [,v]) => sum + v, 0);
    const domainLabels = topDomains.map(([k]) => k.startsWith('.') ? k : '@' + k);
    const domainData = topDomains.map(([,v]) => v);
    if (otherDomainsCount > 0) {
        domainLabels.push('Other corporate');
        domainData.push(otherDomainsCount);
    }
    
    if (emailDomainChartInst) emailDomainChartInst.destroy();
    emailDomainChartInst = makePieChart('emailDomainChart', domainLabels, domainData, BAR_COLORS);

    // Daily Line Chart
    const daily = d.daily_counts || [];
    if (emailDailyChartInst) emailDailyChartInst.destroy();
    emailDailyChartInst = makeLineChart(
        'emailDailyChart',
        daily.map(r => r.date),
        daily.map(r => r.count)
    );

    // Keyword Effectiveness Table
    const kwTbody = document.querySelector('#email-keyword-table tbody');
    if (kwTbody) {
        if (kwEntries.length === 0) {
            kwTbody.innerHTML = emptyRow(4);
        } else {
            const maxKw = kwEntries[0][1];
            kwTbody.innerHTML = '';
            kwEntries.slice(0, 15).forEach(([kw, count], i) => {
                kwTbody.appendChild(mkRow(
                    `<span class="rank-num ${rankClass(i)}">${i+1}</span>`,
                    kw,
                    `<span class="count-value">${fmt(count)}</span>`,
                    progressBar(count, maxKw)
                ));
            });
        }
    }

    // Pending Queue Table
    pendingQueueData = d.pending_queue || [];
    pendingCurrentPage = 1; // Reset to page 1 on refresh
    renderPendingQueuePage();
}

// ─────────────────────────────────────────────────────────
//  MODULE 2 — Company Database Analytics
// ─────────────────────────────────────────────────────────
async function loadCompanyDashboard() {
    let d;
    try {
        const res = await fetch('/api/company_stats');
        d = await res.json();
    } catch(e) {
        console.warn('Could not fetch company stats:', e);
        d = {
            total_companies: 0, new: 0, done: 0, not_interested: 0,
            status_distribution: {}, keyword_counts: {}, keyword_status: {},
            top_hiring_companies: {}
        };
    }

    // KPI cards
    document.getElementById('co-total').textContent = fmt(d.total_companies);
    document.getElementById('co-new').textContent   = fmt(d.new);
    document.getElementById('co-done').textContent  = fmt(d.done);
    document.getElementById('co-ni').textContent    = fmt(d.not_interested);

    // Leaderboard
    const coKwEntries = Object.entries(d.keyword_counts || {}).sort((a,b)=>b[1]-a[1]);
    const topCoKw = coKwEntries[0];
    document.getElementById('co-top-keyword').textContent =
        topCoKw ? `${topCoKw[0]}  —  ${fmt(topCoKw[1])} companies` : 'No data yet';

    // Dynamic Status Pie Chart
    const statusDist = d.status_distribution || {};
    const coStatusLabels = Object.keys(statusDist).map(s => s.charAt(0).toUpperCase() + s.slice(1));
    const coStatusData = Object.values(statusDist);
    
    const statusColorsMap = {
        'new': PALETTE.cyan,
        'done': PALETTE.teal,
        'not interested': PALETTE.red,
        'interested': PALETTE.purple,
        'asked for referral': PALETTE.indigo,
        'in progress': PALETTE.yellow,
        'discovered': PALETTE.green,
        'referred': PALETTE.pink
    };
    const coStatusColors = Object.keys(statusDist).map(s => statusColorsMap[s.toLowerCase()] || PALETTE.gray);

    if (coStatusChartInst) coStatusChartInst.destroy();
    coStatusChartInst = makePieChart('coStatusChart', coStatusLabels, coStatusData, coStatusColors);
    renderLegend('co-status-legend', coStatusLabels, coStatusColors, coStatusData);

    // Keyword Bar Chart (top 8)
    const topCoKws = coKwEntries.slice(0, 8);
    if (coKeywordChartInst) coKeywordChartInst.destroy();
    coKeywordChartInst = makeBarChart(
        'coKeywordChart',
        topCoKws.map(([k])=>k),
        topCoKws.map(([,v])=>v)
    );

    // Top Hiring Companies Chart
    const hiringEntries = Object.entries(d.top_hiring_companies || {}).sort((a,b)=>b[1]-a[1]);
    if (coHiringChartInst) coHiringChartInst.destroy();
    coHiringChartInst = makeBarChart(
        'coHiringChart',
        hiringEntries.map(([k])=>k),
        hiringEntries.map(([,v])=>v)
    );

    // Keyword Analysis Table
    const coKwTbody = document.querySelector('#co-keyword-table tbody');
    if (coKwTbody) {
        if (coKwEntries.length === 0) {
            coKwTbody.innerHTML = emptyRow(4);
        } else {
            const maxCoKw = coKwEntries[0][1];
            coKwTbody.innerHTML = '';
            coKwEntries.slice(0, 15).forEach(([kw, count], i) => {
                coKwTbody.appendChild(mkRow(
                    `<span class="rank-num ${rankClass(i)}">${i+1}</span>`,
                    kw,
                    `<span class="count-value">${fmt(count)}</span>`,
                    progressBar(count, maxCoKw)
                ));
            });
        }
    }

    // Keyword vs Status Table
    const ksTbody = document.querySelector('#co-keyword-status-table tbody');
    if (ksTbody) {
        const ks = d.keyword_status || {};
        const ksEntries = Object.entries(ks).sort((a,b) => {
            const totalA = (a[1].new||0)+(a[1].done||0)+(a[1].not_interested||0);
            const totalB = (b[1].new||0)+(b[1].done||0)+(b[1].not_interested||0);
            return totalB - totalA;
        });

        if (ksEntries.length === 0) {
            ksTbody.innerHTML = emptyRow(4);
        } else {
            ksTbody.innerHTML = '';
            ksEntries.slice(0, 15).forEach(([kw, s]) => {
                ksTbody.appendChild(mkRow(
                    `<strong>${kw}</strong>`,
                    `<span class="count-value" style="color:var(--accent-cyan)">${fmt(s.new||0)}</span>`,
                    `<span class="count-value" style="color:var(--accent-teal)">${fmt(s.done||0)}</span>`,
                    `<span class="count-value" style="color:var(--accent-red)">${fmt(s.not_interested||0)}</span>`
                ));
            });
        }
    }
}

function renderPendingQueuePage() {
    const pqTbody = document.querySelector('#email-pending-table tbody');
    if (!pqTbody) return;
    
    if (pendingQueueData.length === 0) {
        pqTbody.innerHTML = emptyRow(3, 'No pending emails 🎉');
        renderPendingPaginationControls(0);
        return;
    }
    
    const totalPages = Math.ceil(pendingQueueData.length / pendingRecordsPerPage) || 1;
    if (pendingCurrentPage > totalPages) {
        pendingCurrentPage = totalPages;
    }
    if (pendingCurrentPage < 1) {
        pendingCurrentPage = 1;
    }
    
    const startIndex = (pendingCurrentPage - 1) * pendingRecordsPerPage;
    const pageData = pendingQueueData.slice(startIndex, startIndex + pendingRecordsPerPage);
    
    pqTbody.innerHTML = '';
    pageData.forEach(row => {
        const email   = row.Email   || row.email   || '—';
        const keyword = row.Keyword || row.keyword || '—';
        const ts      = row.Timestamp || row.timestamp || '—';
        pqTbody.appendChild(mkRow(email, keyword, ts));
    });
    
    renderPendingPaginationControls(pendingQueueData.length);
}

function renderPendingPaginationControls(totalRecords) {
    const container = document.getElementById('email-pending-pagination');
    if (!container) return;
    
    if (totalRecords <= pendingRecordsPerPage) {
        container.innerHTML = '';
        return;
    }
    
    const totalPages = Math.ceil(totalRecords / pendingRecordsPerPage) || 1;
    const startRecord = (pendingCurrentPage - 1) * pendingRecordsPerPage + 1;
    const endRecord = Math.min(pendingCurrentPage * pendingRecordsPerPage, totalRecords);
    
    let infoHtml = `<div class="pagination-info">Showing <strong>${startRecord}</strong> to <strong>${endRecord}</strong> of <strong>${totalRecords}</strong> records</div>`;
    
    let controlsHtml = `<div class="pagination-controls">`;
    const prevDisabled = pendingCurrentPage === 1 ? 'disabled' : '';
    controlsHtml += `
        <button class="pagination-btn" type="button" onclick="changePendingPage(${pendingCurrentPage - 1})" ${prevDisabled}>
            <i class="fa-solid fa-chevron-left"></i> Prev
        </button>
    `;
    
    controlsHtml += `<div class="pagination-pages">`;
    for (let i = 1; i <= totalPages; i++) {
        const activeClass = i === pendingCurrentPage ? 'active' : '';
        controlsHtml += `<button class="pagination-page-btn ${activeClass}" type="button" onclick="changePendingPage(${i})">${i}</button>`;
    }
    controlsHtml += `</div>`;
    
    const nextDisabled = pendingCurrentPage === totalPages ? 'disabled' : '';
    controlsHtml += `
        <button class="pagination-btn" type="button" onclick="changePendingPage(${pendingCurrentPage + 1})" ${nextDisabled}>
            Next <i class="fa-solid fa-chevron-right"></i>
        </button>
    `;
    controlsHtml += `</div>`;
    
    container.innerHTML = infoHtml + controlsHtml;
}

function changePendingPage(page) {
    pendingCurrentPage = page;
    renderPendingQueuePage();
}

// Expose changePendingPage globally
window.changePendingPage = changePendingPage;

// ─────────────────────────────────────────────────────────
//  Bootstrap — run when dashboard tab is active
// ─────────────────────────────────────────────────────────
async function loadOutreachDashboard() {
    let d;
    try {
        const res = await fetch('/api/outreach_stats');
        d = await res.json();
    } catch(e) {
        console.warn('Could not fetch outreach stats:', e);
        d = {
            total_contacts: 0, sent: 0, pending: 0, failed: 0,
            status_distribution: {}, source_distribution: {}, company_distribution: {},
            daily_counts: [], recent_outreach: []
        };
    }

    // KPI cards
    const elTotal = document.getElementById('outreach-total');
    const elSent = document.getElementById('outreach-sent');
    const elPending = document.getElementById('outreach-pending');
    const elFailed = document.getElementById('outreach-failed');

    if (elTotal) elTotal.textContent = fmt(d.total_contacts);
    if (elSent) elSent.textContent = fmt(d.sent);
    if (elPending) elPending.textContent = fmt(d.pending);
    if (elFailed) elFailed.textContent = fmt(d.failed);

    // Leaderboard Target Company
    const compEntries = Object.entries(d.company_distribution || {}).sort((a,b)=>b[1]-a[1]);
    const topComp = compEntries[0];
    const elLeaderboard = document.getElementById('outreach-top-company');
    if (elLeaderboard) {
        elLeaderboard.textContent = topComp ? `${topComp[0]}  —  ${fmt(topComp[1])} outreach contacts` : 'No data yet';
    }

    // Status Pie Chart
    const statusLabels = Object.keys(d.status_distribution || {}).map(s => s.charAt(0).toUpperCase() + s.slice(1));
    const statusData = Object.values(d.status_distribution || {});
    const statusColorsMap = {
        'sent': PALETTE.green,
        'pending': PALETTE.yellow,
        'failed': PALETTE.red,
        'error': PALETTE.red
    };
    const statusColors = Object.keys(d.status_distribution || {}).map(s => statusColorsMap[s.toLowerCase()] || PALETTE.gray);

    if (outreachStatusChartInst) outreachStatusChartInst.destroy();
    outreachStatusChartInst = makePieChart('outreachStatusChart', statusLabels, statusData, statusColors);
    renderLegend('outreach-status-legend', statusLabels, statusColors, statusData);

    // Source Bar Chart
    const sourceEntries = Object.entries(d.source_distribution || {}).sort((a,b)=>b[1]-a[1]);
    if (outreachSourceChartInst) outreachSourceChartInst.destroy();
    outreachSourceChartInst = makeBarChart(
        'outreachSourceChart',
        sourceEntries.map(([k])=>k),
        sourceEntries.map(([,v])=>v)
    );

    // Daily Line Chart
    const daily = d.daily_counts || [];
    if (outreachDailyChartInst) outreachDailyChartInst.destroy();
    outreachDailyChartInst = makeLineChart(
        'outreachDailyChart',
        daily.map(r => r.date),
        daily.map(r => r.count)
    );

    // Recent Outreach Log Table
    const tbody = document.querySelector('#outreach-recent-table tbody');
    if (tbody) {
        const recent = d.recent_outreach || [];
        if (recent.length === 0) {
            tbody.innerHTML = emptyRow(6, 'No outreach sent yet');
        } else {
            tbody.innerHTML = '';
            recent.forEach(row => {
                const statusClass = row.Status.toLowerCase() === 'sent' ? 'status-pill done' : 
                                   (row.Status.toLowerCase() === 'pending' ? 'status-pill new' : 'status-pill ni');
                const statusText = row.Status || 'Unknown';
                const statusBadge = `<span class="${statusClass}">${statusText}</span>`;
                
                tbody.appendChild(mkRow(
                    row.Name || '—',
                    `<strong>${row.Company}</strong>`,
                    row.Source || '—',
                    row.SentTime || '—',
                    statusBadge,
                    row.Error ? `<span class="text-danger" style="color:var(--accent-red);font-size:0.82rem;"><i class="fa-solid fa-triangle-exclamation"></i> ${row.Error}</span>` : '—'
                ));
            });
        }
    }
}

//  Bootstrap — run when dashboard tab is active
// ─────────────────────────────────────────────────────────
async function loadDashboardAnalytics() {
    await Promise.all([loadEmailDashboard(), loadCompanyDashboard(), loadOutreachDashboard()]);
}

// Hook into main.js tab click (the `loadStats` call in main.js already
// calls this function when the dashboard nav-item is clicked).
// We expose it globally:
window.loadDashboardAnalytics = loadDashboardAnalytics;
window.switchDashModule       = switchDashModule;

// Auto-load on first paint if dashboard is already active
document.addEventListener('DOMContentLoaded', () => {
    const dashTab = document.getElementById('tab-dashboard');
    if (dashTab && dashTab.classList.contains('active')) {
        loadDashboardAnalytics();
    }
});

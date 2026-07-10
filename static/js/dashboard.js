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
    cyan: '#00b0ff',
    green: '#00e676',
    yellow: '#ffb300',
    purple: '#7f5af0',
    teal: '#2cb67d',
    red: '#ff3d00',
    orange: '#ff6d00',
    pink: '#f72585',
    indigo: '#7b2ff7',
    gray: '#9ea4c0',
};

const BAR_COLORS = [
    PALETTE.cyan, PALETTE.purple, PALETTE.teal, PALETTE.yellow,
    PALETTE.green, PALETTE.pink, PALETTE.orange, PALETTE.indigo,
];

// Active chart instances (so we can destroy and re-create cleanly)
let emailStatusChartInst = null;
let emailKeywordChartInst = null;
let emailTitleChartInst = null;
let emailDailyChartInst = null;
let coStatusChartInst = null;
let coKeywordChartInst = null;
let coTitleChartInst = null;
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
    ['email', 'company'].forEach(m => {
        const panel = document.getElementById(`dash-panel-${m}`);
        const tab = document.getElementById(`dash-module-${m}`);
        if (panel) panel.classList.remove('active');
        if (tab) tab.classList.remove('active');
    });
    const activePanel = document.getElementById(`dash-panel-${module}`);
    const activeTab = document.getElementById(`dash-module-${module}`);
    if (activePanel) activePanel.classList.add('active');
    if (activeTab) activeTab.classList.add('active');

    // Refresh statistics upon module switch to show real-time changes
    if (module === 'email') {
        loadEmailDashboard();
    } else if (module === 'company') {
        loadCompanyDashboard();
    }
}

// ─────────────────────────────────────────────────────────
//  Chart factory helpers
// ─────────────────────────────────────────────────────────
function getChartOptions(isLine = false) {
    const isLight = document.body.classList.contains('light-theme');
    const gridColor = isLight ? 'rgba(0,0,0,0.06)' : 'rgba(255,255,255,0.04)';
    const tickColor = isLight ? '#5e6480' : '#9ea4c0';
    const tickColorAlt = isLight ? '#1f1f2e' : '#e0e0e0';
    const tooltipBg = isLight ? 'rgba(255,255,255,0.96)' : 'rgba(10,8,19,0.92)';
    const tooltipText = isLight ? '#1f1f2e' : '#e0e0e0';
    const tooltipBody = isLight ? '#5e6480' : '#9ea4c0';
    const tooltipBorder = isLight ? 'rgba(127,90,240,0.2)' : 'rgba(127,90,240,0.3)';

    return {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
            legend: { display: false },
            tooltip: {
                backgroundColor: tooltipBg,
                titleColor: tooltipText,
                bodyColor: tooltipBody,
                borderColor: tooltipBorder,
                borderWidth: 1,
                padding: 10,
            }
        },
        scales: {
            x: {
                grid: { color: gridColor },
                ticks: { color: tickColor, font: { size: 11 } }
            },
            y: {
                grid: isLine ? { color: gridColor } : { display: false },
                ticks: { color: tickColorAlt, font: { size: 11 } }
            }
        }
    };
}

function getPieChartOptions() {
    const isLight = document.body.classList.contains('light-theme');
    const tooltipBg = isLight ? 'rgba(255,255,255,0.96)' : 'rgba(10,8,19,0.92)';
    const tooltipText = isLight ? '#1f1f2e' : '#e0e0e0';
    const tooltipBody = isLight ? '#5e6480' : '#9ea4c0';
    const tooltipBorder = isLight ? 'rgba(127,90,240,0.2)' : 'rgba(127,90,240,0.3)';

    return {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '68%',
        plugins: {
            legend: { display: false },
            tooltip: {
                backgroundColor: tooltipBg,
                titleColor: tooltipText,
                bodyColor: tooltipBody,
                borderColor: tooltipBorder,
                borderWidth: 1,
                padding: 10,
            }
        }
    };
}

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
        options: getPieChartOptions()
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
                borderColor: BAR_COLORS.slice(0, labels.length),
                borderWidth: 1.5,
                borderRadius: 6,
            }]
        },
        options: {
            ...getChartOptions(false),
            indexAxis: 'y'
        }
    });
}

function makeLineChart(canvasId, labels, generatedData, sentData) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return null;
    const ctx = canvas.getContext('2d');

    const genGradient = ctx.createLinearGradient(0, 0, 0, 200);
    genGradient.addColorStop(0, 'rgba(0,176,255,0.35)');
    genGradient.addColorStop(1, 'rgba(0,176,255,0.0)');

    const datasets = [{
        label: 'Emails Generated',
        data: generatedData,
        borderColor: PALETTE.cyan,
        borderWidth: 2,
        pointBackgroundColor: PALETTE.cyan,
        pointRadius: 4,
        pointHoverRadius: 6,
        fill: true,
        backgroundColor: genGradient,
        tension: 0.4,
    }];

    if (sentData) {
        const sentGradient = ctx.createLinearGradient(0, 0, 0, 200);
        sentGradient.addColorStop(0, 'rgba(0,230,118,0.25)');
        sentGradient.addColorStop(1, 'rgba(0,230,118,0.0)');

        datasets.push({
            label: 'Emails Sent',
            data: sentData,
            borderColor: '#00e676', // Emerald Green
            borderWidth: 2,
            pointBackgroundColor: '#00e676',
            pointRadius: 4,
            pointHoverRadius: 6,
            fill: true,
            backgroundColor: sentGradient,
            tension: 0.4,
        });
    }

    return new Chart(ctx, {
        type: 'line',
        data: {
            labels,
            datasets
        },
        options: {
            ...getChartOptions(true),
            plugins: {
                ...getChartOptions(true).plugins,
                legend: {
                    display: true,
                    position: 'top',
                    labels: {
                        color: 'rgba(255,255,255,0.7)',
                        font: { family: 'Outfit, sans-serif', size: 11 }
                    }
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
    } catch (e) {
        console.warn('Could not fetch email stats:', e);
        d = {
            total_emails: 0, sent: 0, pending: 0, added_today: 0,
            send_success_rate: 0.0, status_distribution: {}, domain_distribution: {},
            keyword_counts: {}, daily_counts: [], pending_queue: []
        };
    }

    // KPI cards
    document.getElementById('email-total').textContent = fmt(d.total_emails);
    document.getElementById('email-sent').textContent = fmt(d.sent);
    const sentTodayEl = document.getElementById('email-sent-today');
    if (sentTodayEl) {
        sentTodayEl.textContent = fmt(d.sent_today || 0);
    }
    document.getElementById('email-pending').textContent = fmt(d.pending);
    document.getElementById('email-today').textContent = fmt(d.added_today);

    const successRateEl = document.getElementById('email-success-rate');
    if (successRateEl) {
        successRateEl.textContent = (d.send_success_rate !== undefined ? d.send_success_rate : 0) + '% rate';
    }

    // Leaderboard
    const kwEntries = Object.entries(d.keyword_counts || {}).sort((a, b) => b[1] - a[1]);
    const topKw = kwEntries[0];
    document.getElementById('email-top-keyword').textContent =
        topKw ? `${topKw[0]}  —  ${fmt(topKw[1])} emails` : 'No data yet';

    // Status Pie Chart
    const sentVal = d.sent || 0;
    const pendingVal = d.pending || 0;
    const skippedVal = d.skipped || 0;
    const statusLabels = ['Sent', 'Pending', 'Skipped'];
    const statusData = [sentVal, pendingVal, skippedVal];
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
        topKws.map(([, v]) => v)
    );

    // Job Title Bar Chart (top 8)
    const titleEntries = Object.entries(d.title_counts || {}).sort((a, b) => b[1] - a[1]);
    const topTitles = titleEntries.slice(0, 8);
    if (emailTitleChartInst) emailTitleChartInst.destroy();
    emailTitleChartInst = makeBarChart(
        'emailTitleChart',
        topTitles.map(([k]) => k),
        topTitles.map(([, v]) => v)
    );

    // Daily Line Chart
    const daily = d.daily_counts || [];
    if (emailDailyChartInst) emailDailyChartInst.destroy();
    emailDailyChartInst = makeLineChart(
        'emailDailyChart',
        daily.map(r => r.date),
        daily.map(r => r.generated || r.count || 0),
        daily.map(r => r.sent || 0)
    );

    // Search Keyword Effectiveness Table
    const kwTbody = document.querySelector('#email-keyword-table tbody');
    if (kwTbody) {
        if (kwEntries.length === 0) {
            kwTbody.innerHTML = emptyRow(4);
        } else {
            const maxKw = kwEntries[0][1];
            kwTbody.innerHTML = '';
            kwEntries.slice(0, 15).forEach(([kw, count], i) => {
                kwTbody.appendChild(mkRow(
                    `<span class="rank-num ${rankClass(i)}">${i + 1}</span>`,
                    kw,
                    `<span class="count-value">${fmt(count)}</span>`,
                    progressBar(count, maxKw)
                ));
            });
        }
    }

    // Job Title Effectiveness Table
    const titleTbody = document.querySelector('#email-title-table tbody');
    if (titleTbody) {
        if (titleEntries.length === 0) {
            titleTbody.innerHTML = emptyRow(4);
        } else {
            const maxTitle = titleEntries[0][1];
            titleTbody.innerHTML = '';
            titleEntries.slice(0, 15).forEach(([title, count], i) => {
                titleTbody.appendChild(mkRow(
                    `<span class="rank-num ${rankClass(i)}">${i + 1}</span>`,
                    title,
                    `<span class="count-value">${fmt(count)}</span>`,
                    progressBar(count, maxTitle)
                ));
            });
        }
    }

}

// ─────────────────────────────────────────────────────────
//  MODULE 2 — Company Database Analytics
// ─────────────────────────────────────────────────────────
async function loadCompanyDashboard() {
    let d;
    try {
        const res = await fetch('/api/company_stats');
        d = await res.json();
    } catch (e) {
        console.warn('Could not fetch company stats:', e);
        d = {
            total_companies: 0, new: 0, done: 0, not_interested: 0, interested: 0, referral_outreach: 0,
            status_distribution: {}, keyword_counts: {}, keyword_status: {},
            top_hiring_companies: {}
        };
    }

    // KPI cards
    document.getElementById('co-total').textContent = fmt(d.total_companies);
    document.getElementById('co-new').textContent = fmt(d.new);
    const coInterestedEl = document.getElementById('co-interested');
    if (coInterestedEl) coInterestedEl.textContent = fmt(d.interested || 0);
    const coReferralEl = document.getElementById('co-referral-outreach');
    if (coReferralEl) coReferralEl.textContent = fmt(d.referral_outreach || 0);
    document.getElementById('co-done').textContent = fmt(d.done);
    document.getElementById('co-ni').textContent = fmt(d.not_interested);

    // Leaderboard
    const coKwEntries = Object.entries(d.keyword_counts || {}).sort((a, b) => b[1] - a[1]);
    const topCoKw = coKwEntries[0];
    document.getElementById('co-top-keyword').textContent =
        topCoKw ? `${topCoKw[0]}  —  ${fmt(topCoKw[1])} companies` : 'No data yet';

    // Dynamic Status Pie Chart
    const statusDist = d.status_distribution || {};
    let newCount = 0;
    let interestedCount = 0;
    let outreachCount = 0;
    let doneCount = 0;
    let niCount = 0;

    Object.entries(statusDist).forEach(([status, val]) => {
        const s = status.toLowerCase();
        if (s === 'new') {
            newCount += val;
        } else if (s === 'interested') {
            interestedCount += val;
        } else if (['ask for referral', 'asked for referral', 'referred', 'referral outreach completed'].includes(s)) {
            outreachCount += val;
        } else if (s === 'done') {
            doneCount += val;
        } else if (s === 'not interested') {
            niCount += val;
        }
    });

    const coStatusLabels = ['New', 'Interested', 'Referral Outreach', 'Done', 'Not Interested'];
    const coStatusData = [newCount, interestedCount, outreachCount, doneCount, niCount];
    const coStatusColors = [
        PALETTE.purple, // New -> Purple
        PALETTE.green,  // Interested -> Green
        PALETTE.yellow, // Referral Outreach -> Yellow
        PALETTE.teal,   // Done -> Teal
        PALETTE.red     // Not Interested -> Red
    ];

    if (coStatusChartInst) coStatusChartInst.destroy();
    coStatusChartInst = makePieChart('coStatusChart', coStatusLabels, coStatusData, coStatusColors);
    renderLegend('co-status-legend', coStatusLabels, coStatusColors, coStatusData);

    // Search Keyword Bar Chart (top 8)
    const topCoKws = coKwEntries.slice(0, 8);
    if (coKeywordChartInst) coKeywordChartInst.destroy();
    coKeywordChartInst = makeBarChart(
        'coKeywordChart',
        topCoKws.map(([k]) => k),
        topCoKws.map(([, v]) => v)
    );

    // Job Title Bar Chart (top 8)
    const coTitleEntries = Object.entries(d.title_counts || {}).sort((a, b) => b[1] - a[1]);
    const topCoTitles = coTitleEntries.slice(0, 8);
    if (coTitleChartInst) coTitleChartInst.destroy();
    coTitleChartInst = makeBarChart(
        'coTitleChart',
        topCoTitles.map(([k]) => k),
        topCoTitles.map(([, v]) => v)
    );

    // Search Keyword Analysis Table
    const coKwTbody = document.querySelector('#co-keyword-table tbody');
    if (coKwTbody) {
        if (coKwEntries.length === 0) {
            coKwTbody.innerHTML = emptyRow(4);
        } else {
            const maxCoKw = coKwEntries[0][1];
            coKwTbody.innerHTML = '';
            coKwEntries.slice(0, 15).forEach(([kw, count], i) => {
                coKwTbody.appendChild(mkRow(
                    `<span class="rank-num ${rankClass(i)}">${i + 1}</span>`,
                    kw,
                    `<span class="count-value">${fmt(count)}</span>`,
                    progressBar(count, maxCoKw)
                ));
            });
        }
    }

    // Job Title Analysis Table
    const coTitleTbody = document.querySelector('#co-title-table tbody');
    if (coTitleTbody) {
        if (coTitleEntries.length === 0) {
            coTitleTbody.innerHTML = emptyRow(4);
        } else {
            const maxCoTitle = coTitleEntries[0][1];
            coTitleTbody.innerHTML = '';
            coTitleEntries.slice(0, 15).forEach(([title, count], i) => {
                coTitleTbody.appendChild(mkRow(
                    `<span class="rank-num ${rankClass(i)}">${i + 1}</span>`,
                    title,
                    `<span class="count-value">${fmt(count)}</span>`,
                    progressBar(count, maxCoTitle)
                ));
            });
        }
    }



// ─────────────────────────────────────────────────────────
//  Bootstrap — run when dashboard tab is active
// ─────────────────────────────────────────────────────────
async function loadOutreachDashboard() {
    let d;
    try {
        const res = await fetch('/api/outreach_stats');
        d = await res.json();
    } catch (e) {
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
    const compEntries = Object.entries(d.company_distribution || {}).sort((a, b) => b[1] - a[1]);
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
    const sourceEntries = Object.entries(d.source_distribution || {}).sort((a, b) => b[1] - a[1]);
    if (outreachSourceChartInst) outreachSourceChartInst.destroy();
    outreachSourceChartInst = makeBarChart(
        'outreachSourceChart',
        sourceEntries.map(([k]) => k),
        sourceEntries.map(([, v]) => v)
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
    await Promise.all([loadEmailDashboard(), loadCompanyDashboard()]);
}

// Hook into main.js tab click (the `loadStats` call in main.js already
// calls this function when the dashboard nav-item is clicked).
// We expose it globally:
window.loadDashboardAnalytics = loadDashboardAnalytics;
window.switchDashModule = switchDashModule;

// Auto-load on first paint if dashboard is already active
document.addEventListener('DOMContentLoaded', () => {
    const dashTab = document.getElementById('tab-dashboard');
    if (dashTab && dashTab.classList.contains('active')) {
        loadDashboardAnalytics();
    }
});

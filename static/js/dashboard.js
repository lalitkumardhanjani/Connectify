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
let emailDailyChartInst    = null;
let coStatusChartInst      = null;
let coKeywordChartInst     = null;

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
        document.getElementById(`dash-panel-${m}`).classList.remove('active');
        document.getElementById(`dash-module-${m}`).classList.remove('active');
    });
    document.getElementById(`dash-panel-${module}`).classList.add('active');
    document.getElementById(`dash-module-${module}`).classList.add('active');
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
            status_distribution: {}, keyword_counts: {}, daily_counts: [],
            pending_queue: []
        };
    }

    // KPI cards
    document.getElementById('email-total').textContent   = fmt(d.total_emails);
    document.getElementById('email-sent').textContent    = fmt(d.sent);
    document.getElementById('email-pending').textContent = fmt(d.pending);
    document.getElementById('email-today').textContent   = fmt(d.added_today);
    document.getElementById('pending-count-badge').textContent = fmt(d.pending) + ' pending';

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

    // Pending Queue Table
    const pqTbody = document.querySelector('#email-pending-table tbody');
    const queue = d.pending_queue || [];
    if (queue.length === 0) {
        pqTbody.innerHTML = emptyRow(3, 'No pending emails 🎉');
    } else {
        pqTbody.innerHTML = '';
        queue.forEach(row => {
            const email   = row.Email   || row.email   || '—';
            const keyword = row.Keyword || row.keyword || '—';
            const ts      = row.Timestamp || row.timestamp || '—';
            pqTbody.appendChild(mkRow(email, keyword, ts));
        });
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
    } catch(e) {
        console.warn('Could not fetch company stats:', e);
        d = {
            total_companies: 0, new: 0, done: 0, not_interested: 0,
            status_distribution: {}, keyword_counts: {}, keyword_status: {}
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

    // Status Pie Chart
    const coStatusLabels = ['New', 'Done', 'Not Interested'];
    const coStatusData   = [d.new||0, d.done||0, d.not_interested||0];
    const coStatusColors = [PALETTE.cyan, PALETTE.teal, PALETTE.red];

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

    // Keyword Analysis Table
    const coKwTbody = document.querySelector('#co-keyword-table tbody');
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

    // Keyword vs Status Table
    const ksTbody = document.querySelector('#co-keyword-status-table tbody');
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

// ─────────────────────────────────────────────────────────
//  Bootstrap — run when dashboard tab is active
// ─────────────────────────────────────────────────────────
async function loadDashboardAnalytics() {
    await Promise.all([loadEmailDashboard(), loadCompanyDashboard()]);
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

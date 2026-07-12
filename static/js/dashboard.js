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
let emailDailyChartInst = null;
let coStatusChartInst = null;
let coKeywordChartInst = null;
let coDailyChartInst = null;
let coHiringChartInst = null;
let outreachStatusChartInst = null;
let outreachSourceChartInst = null;
let outreachDailyChartInst = null;

// Caching & Timeframe State for Daily Line Charts
let rawEmailDailyCounts = [];
let currentEmailTimeframe = 30;
let rawCompanyDailyCounts = [];
let currentCompanyTimeframe = 30;

// Gold star SVG image for daily chart achievements (white-backed to prevent line bleed-through)
const goldStarImg = new Image();
goldStarImg.src = 'data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24"><circle cx="12" cy="12" r="11" fill="%23ffffff" stroke="%23ffb300" stroke-width="2.5"/><path d="M12 5.5l1.94 3.93 4.34.63-3.14 3.06.74 4.32L12 15.4l-3.88 2.04.74-4.32-3.14-3.06 4.34-.63z" fill="%23ffb300"/></svg>';
goldStarImg.width = 18;
goldStarImg.height = 18;

function computeStreaks(subset, type) {
    let maxStreak = 0;
    let tempStreak = 0;

    // Sort ascending by date
    const sorted = [...subset].sort((a, b) => a.date.localeCompare(b.date));

    // An "active" day = any day where outreach was actually SENT
    function isActiveDay(r) {
        if (type === 'email') {
            return (r.sent || 0) > 0;
        } else if (type === 'company') {
            return (r.connections_sent || 0) > 0;
        }
        return false;
    }

    // Max streak: longest consecutive run in full history
    sorted.forEach(r => {
        if (isActiveDay(r)) {
            tempStreak++;
            if (tempStreak > maxStreak) maxStreak = tempStreak;
        } else {
            tempStreak = 0;
        }
    });

    // Current streak: how many consecutive active days ending at TODAY (local timezone).
    let currentStreak = 0;
    const localDate = new Date();
    const year = localDate.getFullYear();
    const month = String(localDate.getMonth() + 1).padStart(2, '0');
    const day = String(localDate.getDate()).padStart(2, '0');
    const todayStr = `${year}-${month}-${day}`;

    let startIdx = sorted.length - 1;

    if (startIdx >= 0) {
        const lastDate = sorted[startIdx].date;

        if (lastDate === todayStr) {
            // Today is recorded: if no outreach sent, streak is 0 immediately
            if (!isActiveDay(sorted[startIdx])) {
                return { currentStreak: 0, maxStreak };
            }
        }
        // If lastDate < todayStr: today has no entry yet, start from last known day
    }

    // Walk backwards counting consecutive active days
    for (let i = startIdx; i >= 0; i--) {
        if (isActiveDay(sorted[i])) {
            currentStreak++;
        } else {
            break; // Gap found — streak is broken
        }
    }

    return { currentStreak, maxStreak };
}


function updateStreakDisplay(type, currentCountId, maxCountId, currentBadgeId, maxBadgeId, rawData) {
    const { currentStreak, maxStreak } = computeStreaks(rawData, type);
    
    const curCount = document.getElementById(currentCountId);
    const curBadge = document.getElementById(currentBadgeId);
    const mxCount = document.getElementById(maxCountId);
    const mxBadge = document.getElementById(maxBadgeId);
    
    if (curCount && curBadge) {
        if (currentStreak > 0) {
            curCount.textContent = currentStreak;
            curBadge.style.display = 'inline-flex';
        } else {
            curBadge.style.display = 'none';
        }
    }
    
    if (mxCount && mxBadge) {
        if (maxStreak > 0) {
            mxCount.textContent = maxStreak;
            mxBadge.style.display = 'inline-flex';
        } else {
            mxBadge.style.display = 'none';
        }
    }
}


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

function makeLineChart(canvasId, labels, data) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return null;
    const ctx = canvas.getContext('2d');
    
    const gradient = ctx.createLinearGradient(0, 0, 0, 200);
    gradient.addColorStop(0, 'rgba(127,90,240,0.35)');
    gradient.addColorStop(1, 'rgba(127,90,240,0.0)');
    
    return new Chart(ctx, {
        type: 'line',
        data: {
            labels,
            datasets: [{
                data,
                borderColor: PALETTE.purple,
                borderWidth: 2,
                fill: true,
                backgroundColor: gradient,
                tension: 0.4
            }]
        },
        options: getChartOptions(true)
    });
}

function makeCustomEmailLineChart(canvasId, labels, generatedData, sentData, genPointStyles, genPointRadii, genPointHoverRadii, sentPointStyles, sentPointRadii, sentPointHoverRadii, sentPointBgColors, sentPointBorderColors, rawSubset) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return null;
    const ctx = canvas.getContext('2d');

    const genGradient = ctx.createLinearGradient(0, 0, 0, 200);
    genGradient.addColorStop(0, 'rgba(0,176,255,0.35)');
    genGradient.addColorStop(1, 'rgba(0,176,255,0.0)');

    const sentGradient = ctx.createLinearGradient(0, 0, 0, 200);
    sentGradient.addColorStop(0, 'rgba(0,230,118,0.25)');
    sentGradient.addColorStop(1, 'rgba(0,230,118,0.0)');

    const datasets = [
        {
            label: 'Emails Generated',
            data: generatedData,
            borderColor: PALETTE.cyan,
            borderWidth: 2,
            pointStyle: genPointStyles, // Array of point styles!
            pointBackgroundColor: PALETTE.cyan,
            pointRadius: genPointRadii, // Hide on achievement days!
            pointHoverRadius: genPointHoverRadii,
            fill: true,
            backgroundColor: genGradient,
            tension: 0.4,
            order: 2, // Draw first (bottom)
        },
        {
            label: 'Emails Sent',
            data: sentData,
            borderColor: '#00e676',
            borderWidth: 2,
            pointStyle: sentPointStyles, // Array of point styles!
            pointBackgroundColor: sentPointBgColors, // Gold for achievements!
            pointBorderColor: sentPointBorderColors,
            pointRadius: sentPointRadii,
            pointHoverRadius: sentPointHoverRadii,
            fill: true,
            backgroundColor: sentGradient,
            tension: 0.4,
            order: 1, // Draw last (top)
        }
    ];

    const chart = new Chart(ctx, {
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
                        usePointStyle: true, // Use dataset point styles in legend!
                        color: document.body.classList.contains('light-theme') ? '#1f1f2e' : 'rgba(255,255,255,0.7)',
                        font: { family: 'Outfit, sans-serif', size: 11 }
                    }
                },
                tooltip: {
                    ...getChartOptions(true).plugins.tooltip,
                    callbacks: {
                        label: function(context) {
                            let label = context.dataset.label || '';
                            if (label) {
                                label += ': ';
                            }
                            if (context.parsed.y !== null) {
                                label += context.parsed.y;
                            }
                            
                            // Check if this point is an achievement!
                            if (context.datasetIndex === 1) { // Emails Sent
                                const r = context.chart.rawSubset ? context.chart.rawSubset[context.dataIndex] : null;
                                if (r) {
                                    const gen = r.generated || r.count || 0;
                                    const sent = r.sent || 0;
                                    if (gen > 0 && sent >= gen) {
                                        label += ' ⭐ Goal Achieved! (Sent all generated)';
                                    }
                                }
                            }
                            return label;
                        }
                    }
                }
            }
        }
    });
    chart.rawSubset = rawSubset;
    return chart;
}

function makeCustomCompanyLineChart(canvasId, labels, companiesAdded, connectionsSent, addPointStyles, addPointRadii, addPointHoverRadii, sentPointStyles, sentPointRadii, sentPointHoverRadii, sentPointBgColors, sentPointBorderColors, rawSubset) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return null;
    const ctx = canvas.getContext('2d');

    const addedGradient = ctx.createLinearGradient(0, 0, 0, 200);
    addedGradient.addColorStop(0, 'rgba(127,90,240,0.35)');
    addedGradient.addColorStop(1, 'rgba(127,90,240,0.0)');

    const sentGradient = ctx.createLinearGradient(0, 0, 0, 200);
    sentGradient.addColorStop(0, 'rgba(0,176,255,0.25)');
    sentGradient.addColorStop(1, 'rgba(0,176,255,0.0)');

    const datasets = [
        {
            label: 'Companies Added',
            data: companiesAdded,
            borderColor: PALETTE.purple,
            borderWidth: 2,
            pointStyle: addPointStyles, // Array of point styles!
            pointBackgroundColor: PALETTE.purple,
            pointRadius: addPointRadii, // Hide on achievement days!
            pointHoverRadius: addPointHoverRadii,
            fill: true,
            backgroundColor: addedGradient,
            tension: 0.4,
            order: 2, // Draw first (bottom)
        },
        {
            label: 'Connection Requests Sent',
            data: connectionsSent,
            borderColor: PALETTE.cyan,
            borderWidth: 2,
            pointStyle: sentPointStyles,
            pointBackgroundColor: sentPointBgColors,
            pointBorderColor: sentPointBorderColors,
            pointRadius: sentPointRadii,
            pointHoverRadius: sentPointHoverRadii,
            fill: true,
            backgroundColor: sentGradient,
            tension: 0.4,
            order: 1, // Draw last (top)
        }
    ];

    const chart = new Chart(ctx, {
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
                        usePointStyle: true,
                        color: document.body.classList.contains('light-theme') ? '#1f1f2e' : 'rgba(255,255,255,0.7)',
                        font: { family: 'Outfit, sans-serif', size: 11 }
                    }
                },
                tooltip: {
                    ...getChartOptions(true).plugins.tooltip,
                    callbacks: {
                        label: function(context) {
                            let label = context.dataset.label || '';
                            if (label) {
                                label += ': ';
                            }
                            if (context.parsed.y !== null) {
                                label += context.parsed.y;
                            }
                            
                            // Check if this point is an achievement!
                            if (context.datasetIndex === 1) { // Connections Sent
                                const r = context.chart.rawSubset ? context.chart.rawSubset[context.dataIndex] : null;
                                if (r) {
                                    const added = r.companies_added || 0;
                                    const sent = r.connections_sent || 0;
                                    if (added > 0 && sent >= (added * 5)) {
                                        label += ' 🏆 Target Met! (Sent 5x+ connections vs added)';
                                    }
                                }
                            }
                            return label;
                        }
                    }
                }
            }
        }
    });
    chart.rawSubset = rawSubset;
    return chart;
}

function renderEmailDailyChart() {
    const subset = rawEmailDailyCounts.slice(-currentEmailTimeframe);
    
    let achievementsCount = 0;
    const genPointStyles = [];
    const genPointRadii = [];
    const genPointHoverRadii = [];
    
    const sentPointStyles = [];
    const sentPointRadii = [];
    const sentPointHoverRadii = [];
    const sentPointBgColors = [];
    const sentPointBorderColors = [];
    
    const isStarView = currentEmailTimeframe > 7;
    subset.forEach(r => {
        const gen = r.generated || r.count || 0;
        const sent = r.sent || 0;
        const isAchieved = gen > 0 && sent >= gen;
        
        if (isAchieved && isStarView) {
            achievementsCount++;
            
            // Hide diamond Generated point at this overlap index
            genPointStyles.push('circle');
            genPointRadii.push(0);
            genPointHoverRadii.push(0);
            
            // Show custom Gold Star image
            sentPointStyles.push(goldStarImg);
            sentPointRadii.push(9);
            sentPointHoverRadii.push(11);
            sentPointBgColors.push('#ffb300');
            sentPointBorderColors.push('#ffb300');
        } else {
            if (isAchieved) {
                achievementsCount++;
            }
            // Normal diamond shape
            genPointStyles.push('rectRot');
            genPointRadii.push(5);
            genPointHoverRadii.push(7);
            
            // Normal circle shape
            sentPointStyles.push('circle');
            sentPointRadii.push(5);
            sentPointHoverRadii.push(7);
            sentPointBgColors.push('#00e676');
            sentPointBorderColors.push('#00e676');
        }
    });

    const badge = document.getElementById('email-achievements-badge');
    const countEl = document.getElementById('email-achievements-count');
    if (badge && countEl) {
        if (achievementsCount > 0) {
            countEl.textContent = achievementsCount;
            badge.style.display = 'inline-flex';
        } else {
            badge.style.display = 'none';
        }
    }

    updateStreakDisplay('email', 'email-current-streak-count', 'email-max-streak-count', 'email-current-streak-badge', 'email-max-streak-badge', rawEmailDailyCounts);

    if (emailDailyChartInst) {
        emailDailyChartInst.rawSubset = subset;
        emailDailyChartInst.data.labels = subset.map(r => r.date);
        emailDailyChartInst.data.datasets[0].data = subset.map(r => r.generated || r.count || 0);
        emailDailyChartInst.data.datasets[0].pointStyle = genPointStyles;
        emailDailyChartInst.data.datasets[0].pointRadius = genPointRadii;
        emailDailyChartInst.data.datasets[0].pointHoverRadius = genPointHoverRadii;
        
        emailDailyChartInst.data.datasets[1].data = subset.map(r => r.sent || 0);
        emailDailyChartInst.data.datasets[1].pointStyle = sentPointStyles;
        emailDailyChartInst.data.datasets[1].pointRadius = sentPointRadii;
        emailDailyChartInst.data.datasets[1].pointHoverRadius = sentPointHoverRadii;
        emailDailyChartInst.data.datasets[1].pointBackgroundColor = sentPointBgColors;
        emailDailyChartInst.data.datasets[1].pointBorderColor = sentPointBorderColors;
        
        emailDailyChartInst.update('none'); // Update smoothly without reload animation
    } else {
        emailDailyChartInst = makeCustomEmailLineChart(
            'emailDailyChart',
            subset.map(r => r.date),
            subset.map(r => r.generated || r.count || 0),
            subset.map(r => r.sent || 0),
            genPointStyles,
            genPointRadii,
            genPointHoverRadii,
            sentPointStyles,
            sentPointRadii,
            sentPointHoverRadii,
            sentPointBgColors,
            sentPointBorderColors,
            subset
        );
    }
}

function toggleEmailTimeframe(days) {
    currentEmailTimeframe = days;
    [7, 30, 90].forEach(d => {
        const btn = document.getElementById(`email-tf-${d}`);
        if (btn) {
            if (d === days) btn.classList.add('active');
            else btn.classList.remove('active');
        }
    });
    renderEmailDailyChart();
}

function renderCompanyDailyChart() {
    const subset = rawCompanyDailyCounts.slice(-currentCompanyTimeframe);
    
    let achievementsCount = 0;
    const addPointStyles = [];
    const addPointRadii = [];
    const addPointHoverRadii = [];
    
    const sentPointStyles = [];
    const sentPointRadii = [];
    const sentPointHoverRadii = [];
    const sentPointBgColors = [];
    const sentPointBorderColors = [];
    
    const isStarView = currentCompanyTimeframe > 7;
    subset.forEach(r => {
        const added = r.companies_added || 0;
        const sent = r.connections_sent || 0;
        const isAchieved = added > 0 && sent >= (added * 5);
        
        if (isAchieved && isStarView) {
            achievementsCount++;
            
            // Hide triangle Added point at this overlap index
            addPointStyles.push('circle');
            addPointRadii.push(0);
            addPointHoverRadii.push(0);
            
            // Show custom Gold Star image
            sentPointStyles.push(goldStarImg);
            sentPointRadii.push(9);
            sentPointHoverRadii.push(11);
            sentPointBgColors.push('#ffb300');
            sentPointBorderColors.push('#ffb300');
        } else {
            if (isAchieved) {
                achievementsCount++;
            }
            // Normal triangle shape
            addPointStyles.push('triangle');
            addPointRadii.push(5);
            addPointHoverRadii.push(7);
            
            // Normal circle shape
            sentPointStyles.push('circle');
            sentPointRadii.push(5);
            sentPointHoverRadii.push(7);
            sentPointBgColors.push(PALETTE.cyan);
            sentPointBorderColors.push(PALETTE.cyan);
        }
    });

    const badge = document.getElementById('company-achievements-badge');
    const countEl = document.getElementById('company-achievements-count');
    if (badge && countEl) {
        if (achievementsCount > 0) {
            countEl.textContent = achievementsCount;
            badge.style.display = 'inline-flex';
        } else {
            badge.style.display = 'none';
        }
    }

    updateStreakDisplay('company', 'company-current-streak-count', 'company-max-streak-count', 'company-current-streak-badge', 'company-max-streak-badge', rawCompanyDailyCounts);

    if (coDailyChartInst) {
        coDailyChartInst.rawSubset = subset;
        coDailyChartInst.data.labels = subset.map(r => r.date);
        coDailyChartInst.data.datasets[0].data = subset.map(r => r.companies_added || 0);
        coDailyChartInst.data.datasets[0].pointStyle = addPointStyles;
        coDailyChartInst.data.datasets[0].pointRadius = addPointRadii;
        coDailyChartInst.data.datasets[0].pointHoverRadius = addPointHoverRadii;
        
        coDailyChartInst.data.datasets[1].data = subset.map(r => r.connections_sent || 0);
        coDailyChartInst.data.datasets[1].pointStyle = sentPointStyles;
        coDailyChartInst.data.datasets[1].pointRadius = sentPointRadii;
        coDailyChartInst.data.datasets[1].pointHoverRadius = sentPointHoverRadii;
        coDailyChartInst.data.datasets[1].pointBackgroundColor = sentPointBgColors;
        coDailyChartInst.data.datasets[1].pointBorderColor = sentPointBorderColors;
        
        coDailyChartInst.update('none'); // Update smoothly without reload animation
    } else {
        coDailyChartInst = makeCustomCompanyLineChart(
            'coDailyChart',
            subset.map(r => r.date),
            subset.map(r => r.companies_added || 0),
            subset.map(r => r.connections_sent || 0),
            addPointStyles,
            addPointRadii,
            addPointHoverRadii,
            sentPointStyles,
            sentPointRadii,
            sentPointHoverRadii,
            sentPointBgColors,
            sentPointBorderColors,
            subset
        );
    }
}

function toggleCompanyTimeframe(days) {
    currentCompanyTimeframe = days;
    [7, 30, 90].forEach(d => {
        const btn = document.getElementById(`company-tf-${d}`);
        if (btn) {
            if (d === days) btn.classList.add('active');
            else btn.classList.remove('active');
        }
    });
    renderCompanyDailyChart();
}

window.toggleEmailTimeframe = toggleEmailTimeframe;
window.toggleCompanyTimeframe = toggleCompanyTimeframe;

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

    // Daily Line Chart
    rawEmailDailyCounts = d.daily_counts || [];
    renderEmailDailyChart();

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
                    `<span class="rank-num ${rankClass(i)}">${i + 1}</span>`,
                    kw,
                    `<span class="count-value">${fmt(count)}</span>`,
                    progressBar(count, maxKw)
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

    // Keyword Bar Chart (top 8)
    const topCoKws = coKwEntries.slice(0, 8);
    if (coKeywordChartInst) coKeywordChartInst.destroy();
    coKeywordChartInst = makeBarChart(
        'coKeywordChart',
        topCoKws.map(([k]) => k),
        topCoKws.map(([, v]) => v)
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
                    `<span class="rank-num ${rankClass(i)}">${i + 1}</span>`,
                    kw,
                    `<span class="count-value">${fmt(count)}</span>`,
                    progressBar(count, maxCoKw)
                ));
            });
        }
    }

    // Daily Company & Connection Activity Line Chart
    rawCompanyDailyCounts = d.daily_counts || [];
    renderCompanyDailyChart();
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
    if (outreachDailyChartInst) {
        outreachDailyChartInst.data.labels = daily.map(r => r.date);
        outreachDailyChartInst.data.datasets[0].data = daily.map(r => r.count);
        outreachDailyChartInst.update('none');
    } else {
        outreachDailyChartInst = makeLineChart(
            'outreachDailyChart',
            daily.map(r => r.date),
            daily.map(r => r.count)
        );
    }

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

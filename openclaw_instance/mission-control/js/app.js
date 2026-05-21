/* ─────────────────────────────────────────────
   OROVA Mission Control — Application Engine v2
   ───────────────────────────────────────────── */

const API = window.location.origin;

// ═══════════════════ DATA LAYER ═══════════════════
const Store = {
    async getTasks() { 
        const res = await apiFetch('/api/tasks');
        return res ? res.tasks : []; 
    },
    async setTasks(v) { 
        await apiFetch('/api/tasks', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(v) });
    },
    async getContent() { 
        const res = await apiFetch('/api/content');
        return res ? res.content : []; 
    },
    async setContent(v) { 
        await apiFetch('/api/content', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(v) });
    },
    async getMemories() { 
        const res = await apiFetch('/api/memory');
        return res ? res.memories : []; 
    },
    async setMemories(v) { 
        await apiFetch('/api/memory', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(v) });
    },
    async getChatHistory() { 
        const res = await apiFetch('/api/chat/history');
        return res ? res.history : []; 
    },
    async setChatHistory(v) { 
        await apiFetch('/api/chat/history', { method: 'POST', body: JSON.stringify({history: v}) });
    },
};

function uid() { return Date.now().toString(36) + Math.random().toString(36).slice(2, 7); }

// ═══════════════════ AGENT DATA ═══════════════════
const AGENTS = [
    { id: 'nova', name: 'Nova', role: 'CEO & Director', dept: 'Leadership', color: '#6366f1', initial: 'N', desc: 'Orchestrates all operations. The brain behind every decision.', status: 'working', task: 'Coordinating lead outreach campaign' },
    { id: 'atlas', name: 'Atlas', role: 'Lead Developer', dept: 'Engineering', color: '#3b82f6', initial: 'AT', desc: 'Builds tools, integrations, APIs, and automations.', status: 'working', task: 'Building Mission Control dashboard' },
    { id: 'pixel', name: 'Pixel', role: 'Creative Director', dept: 'Creative', color: '#ec4899', initial: 'PX', desc: 'B&W luxury aesthetics. Instagram visual identity.', status: 'working', task: 'Designing social media content' },
    { id: 'quill', name: 'Quill', role: 'Content Strategist', dept: 'Creative', color: '#a855f7', initial: 'QU', desc: 'Cold emails, scripts, blog posts, ad copy.', status: 'idle', task: '' },
    { id: 'hawk', name: 'Hawk', role: 'Lead Hunter', dept: 'Sales', color: '#f59e0b', initial: 'HK', desc: 'Prospecting, competitive intel, lead research.', status: 'working', task: 'Hunting luxury remodel leads in LA' },
    { id: 'closer', name: 'Closer', role: 'Sales Director', dept: 'Sales', color: '#ef4444', initial: 'CL', desc: 'Outreach sequences, follow-ups, appointment setting.', status: 'idle', task: '' },
    { id: 'sentinel', name: 'Sentinel', role: 'Operations Manager', dept: 'Operations', color: '#10b981', initial: 'SN', desc: 'Scheduling, monitoring, CRM, reporting.', status: 'working', task: 'Monitoring reply inbox & cron jobs' },
    { id: 'echo', name: 'Echo', role: 'Client Success', dept: 'Operations', color: '#14b8a6', initial: 'EC', desc: 'Reply management, relationship nurturing.', status: 'idle', task: '' },
    { id: 'oracle', name: 'Oracle', role: 'Data Intelligence', dept: 'Analytics', color: '#8b5cf6', initial: 'OR', desc: 'Pipeline analytics, conversion tracking, ROI analysis.', status: 'idle', task: '' },
    { id: 'viper', name: 'Viper', role: 'Stealth Ops', dept: 'Intelligence', color: '#059669', initial: 'VP', desc: 'Anti-bot scraping, proxy rotation, stealth extraction.', status: 'idle', task: '' },
];

// ═══════════════════ DEFAULT MEMORIES ═══════════════════
const DEFAULT_MEMORIES = [
    { id: uid(), tag: 'config', title: 'Office Hours (California Law)', body: 'Mark\'s office hours are strictly 7:30 AM – 11:30 AM and 6:00 PM – 8:00 PM California Time (PT). Never propose or book meetings outside these windows.', date: '2026-02-15' },
    { id: uid(), tag: 'persona', title: 'Nova CEO Persona (Hormozi-Mode)', body: 'Nova operates as OROVA\'s autonomous CEO. She leads with Grand Slam Offers, identifies Offer Gaps via SEO audits, and executes multi-channel attacks (Email + Voice). Social replies max 25 words.', date: '2026-02-14' },
    { id: uid(), tag: 'strategy', title: 'Brand Aesthetic: B&W Luxury', body: 'All Instagram visuals MUST be high-contrast Black & White, minimalist, luxury. The Creative Director (Pixel) enforces this via brand_guidelines.json.', date: '2026-02-14' },
    { id: uid(), tag: 'outreach', title: 'AgentMail Configuration', body: 'Nova\'s email identity runs on AgentMail. She can create inboxes, send outreach, check replies, and respond. Reply Monitor polls every 5 minutes.', date: '2026-02-15' },
    { id: uid(), tag: 'lead', title: 'Lead Qualification Criteria', body: 'Target: High-end businesses with $4-5k+ CLV. Must find Owner Name + Phone. Use 4-tier search fallback: Stealth (Scrapling) → Tavily → Google Scraper → DuckDuckGo. Deep-scrape every candidate site.', date: '2026-02-12' },
    { id: uid(), tag: 'config', title: 'AI Model Tier System', body: 'Primary: OpenAI o3-pro (CEO Brain). Coder: Claude Sonnet (Technical). Safety Net: Google Antigravity (Zero-Downtime failover). All accessed via OpenCode Bridge.', date: '2026-02-10' },
    { id: uid(), tag: 'strategy', title: 'Multi-Agent Team Structure', body: '10 specialized agents: Nova (CEO), Atlas (Dev), Pixel (Creative), Quill (Writer), Hawk (Lead Hunter), Closer (Sales), Sentinel (Ops), Echo (Client Success), Oracle (Data Intelligence), Viper (Stealth Ops).', date: '2026-03-13' },
    { id: uid(), tag: 'outreach', title: 'Appointment Setter Protocol', body: 'When a prospect replies with interest: 1) Check calendar. 2) Call get_office_hour_slots. 3) Propose exactly 2 time slots within the California windows. 4) Create event on confirmation.', date: '2026-02-15' },
    { id: uid(), tag: 'config', title: 'Hugging Face Deployment', body: 'The Mission Control dashboard & API run on Hugging Face Spaces free tier. Worker runs cron jobs (Fast Lane 2min, Reply Monitor 5min, Cold Lead Escalation 30min, Slow Lane 60min).', date: '2026-03-21' },
    { id: uid(), tag: 'lead', title: 'Vertical: Automotive (Default)', body: 'Default vertical is Automotive. Config loaded from Niche_Verticals. Search queries focus on luxury car dealers and high-end automotive services.', date: '2026-02-08' },
];

// ═══════════════════ CRON SCHEDULE ═══════════════════
const CRON_EVENTS = [
    { title: 'Fast Lane Check', type: 'cron', time: '2min interval', repeat: 'daily' },
    { title: 'Reply Monitor', type: 'cron', time: '5min interval', repeat: 'daily' },
    { title: 'Lead Hunt (Slow)', type: 'cron', time: '60min interval', repeat: 'daily' },
    { title: 'Cold Lead → Call', type: 'cron', time: '30min interval', repeat: 'daily' },
    { title: 'Office Hours AM', type: 'meeting', time: '7:30-11:30 PT', repeat: 'weekday' },
    { title: 'Office Hours PM', type: 'meeting', time: '6:00-8:00 PT', repeat: 'weekday' },
];

// ═══════════════════ API HELPER ═══════════════════
async function apiFetch(path, opts) {
    try {
        const res = await fetch(API + path, opts);
        return await res.json();
    } catch (e) {
        console.warn('API error:', path, e);
        return null;
    }
}

// ═══════════════════ TOAST SYSTEM ═══════════════════
function showToast(message, type) {
    type = type || 'info';
    var container = document.getElementById('toast-container');
    if (!container) return;
    var toast = document.createElement('div');
    toast.className = 'toast ' + type;
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(function () { toast.remove(); }, 4000);
}

// ═══════════════════ HAMBURGER MENU ═══════════════════
var hamburger = document.getElementById('hamburger');
var sidebar = document.getElementById('sidebar');
var sidebarOverlay = document.getElementById('sidebar-overlay');

if (hamburger) {
    hamburger.addEventListener('click', function () {
        hamburger.classList.toggle('open');
        sidebar.classList.toggle('open');
        sidebarOverlay.classList.toggle('visible');
    });
}

if (sidebarOverlay) {
    sidebarOverlay.addEventListener('click', function () {
        hamburger.classList.remove('open');
        sidebar.classList.remove('open');
        sidebarOverlay.classList.remove('visible');
    });
}

// ═══════════════════ NAVIGATION ═══════════════════
document.querySelectorAll('.nav-item').forEach(function (item) {
    item.addEventListener('click', async function () {
        document.querySelectorAll('.nav-item').forEach(function (n) { n.classList.remove('active'); });
        item.classList.add('active');
        var screen = item.dataset.screen;
        document.querySelectorAll('.screen').forEach(function (s) { s.classList.remove('active'); });
        document.getElementById('screen-' + screen).classList.add('active');
        // Close mobile sidebar
        if (hamburger) {
            hamburger.classList.remove('open');
            sidebar.classList.remove('open');
            sidebarOverlay.classList.remove('visible');
        }
        // Re-render on switch
        if (screen === 'taskboard') await renderTasks();
        if (screen === 'analytics') await renderAnalytics();
        if (screen === 'pipeline') await renderPipeline();
        if (screen === 'calendar') await renderCalendar();
        if (screen === 'leads') await renderLeads();
        if (screen === 'memory') await renderMemories();
        if (screen === 'team') renderTeam();
        if (screen === 'skills') renderSkillsHub();
        if (screen === 'workflows') renderPipelineRunner();
        if (screen === 'office') renderOffice();
    });
});

// ═══════════════════ THEME TOGGLE ═══════════════════
var themeBtn = document.getElementById('theme-toggle');
if (themeBtn) {
    (function () {
        var saved = localStorage.getItem('orova_theme') || 'dark';
        document.documentElement.setAttribute('data-theme', saved);
        themeBtn.textContent = saved === 'dark' ? '◐' : '◑';
    })();

    themeBtn.addEventListener('click', function () {
        var current = document.documentElement.getAttribute('data-theme');
        var next = current === 'dark' ? 'light' : 'dark';
        document.documentElement.setAttribute('data-theme', next);
        localStorage.setItem('orova_theme', next);
        themeBtn.textContent = next === 'dark' ? '◐' : '◑';
    });
}

// ═══════════════════ MODAL SYSTEM ═══════════════════
var overlay = document.getElementById('modal-overlay');

function openModal(id) {
    overlay.classList.add('visible');
    document.getElementById(id).classList.add('visible');
}

function closeModals() {
    overlay.classList.remove('visible');
    document.querySelectorAll('.modal').forEach(function (m) { m.classList.remove('visible'); });
}

if (overlay) overlay.addEventListener('click', function (e) { if (e.target === overlay) closeModals(); });
document.querySelectorAll('[data-close]').forEach(function (btn) { btn.addEventListener('click', closeModals); });

// ═══════════════════ TASK BOARD ═══════════════════
var editingTaskId = null;

var btnAddTask = document.getElementById('btn-add-task');
if (btnAddTask) {
    btnAddTask.addEventListener('click', function () {
        editingTaskId = null;
        document.getElementById('modal-task-title').textContent = 'New Task';
        document.getElementById('task-title').value = '';
        document.getElementById('task-desc').value = '';
        document.getElementById('task-assignee').value = 'Nova';
        document.getElementById('task-priority').value = 'medium';
        document.getElementById('task-status').value = 'backlog';
        document.getElementById('task-due').value = '';
        openModal('modal-task');
    });
}

var btnSaveTask = document.getElementById('btn-save-task');
if (btnSaveTask) {
    btnSaveTask.addEventListener('click', async function () {
        var title = document.getElementById('task-title').value.trim();
        if (!title) return;
        var tasks = await Store.getTasks();
        var data = {
            title: title,
            desc: document.getElementById('task-desc').value.trim(),
            assignee: document.getElementById('task-assignee').value,
            priority: document.getElementById('task-priority').value,
            status: document.getElementById('task-status').value,
            due: document.getElementById('task-due').value,
        };
        if (editingTaskId) {
            var idx = tasks.findIndex(function (t) { return t.id === editingTaskId; });
            if (idx !== -1) tasks[idx] = Object.assign({}, tasks[idx], data);
        } else {
            tasks.push(Object.assign({ id: uid() }, data));
        }
        await Store.setTasks(tasks);
        closeModals();
        await renderTasks();
    });
}

var taskFilter = 'all';
document.querySelectorAll('.filter-btn').forEach(function (btn) {
    btn.addEventListener('click', function () {
        document.querySelectorAll('.filter-btn').forEach(function (b) { b.classList.remove('active'); });
        btn.classList.add('active');
        taskFilter = btn.dataset.filter;
        renderTasks();
    });
});

async function renderTasks() {
    var tasks = await Store.getTasks();
    var statuses = ['backlog', 'in-progress', 'review', 'done'];
    statuses.forEach(function (status) {
        var col = document.getElementById('col-' + status);
        if (!col) return;
        var filtered = tasks.filter(function (t) { return t.status === status && (taskFilter === 'all' || t.assignee === taskFilter); });
        col.innerHTML = filtered.map(function (t) {
            return '<div class="task-card" draggable="true" data-id="' + t.id + '">'
                + '<div class="task-card-title">' + esc(t.title) + '</div>'
                + (t.desc ? '<div class="task-card-desc">' + esc(t.desc) + '</div>' : '')
                + '<div class="task-card-meta"><span class="task-avatar"><span class="task-avatar-dot ' + (t.assignee === 'Nova' ? 'nova' : 'mark') + '">' + (t.assignee === 'Nova' ? 'N' : 'M') + '</span>' + t.assignee + '</span>'
                + '<span class="task-priority ' + t.priority + '">' + t.priority + '</span></div>'
                + (t.due ? '<div style="font-size:11px;color:var(--text-muted);margin-top:8px;">Due: ' + t.due + '</div>' : '')
                + '<div class="task-card-actions"><button class="task-action-btn" onclick="editTask(\'' + t.id + '\')">Edit</button><button class="task-action-btn delete" onclick="deleteTask(\'' + t.id + '\')">Delete</button></div>'
                + '</div>';
        }).join('');
        var countEl = col.closest('.kanban-column').querySelector('.col-count');
        if (countEl) countEl.textContent = filtered.length;
    });
    initDragDrop('task-card', 'column-cards', async function (cardId, newStatus) {
        var tasks = await Store.getTasks();
        var t = tasks.find(function (x) { return x.id === cardId; });
        if (t) t.status = newStatus;
        await Store.setTasks(tasks);
        await renderTasks();
    });
}

window.editTask = async function (id) {
    var tasks = await Store.getTasks();
    var t = tasks.find(function (x) { return x.id === id; });
    if (!t) return;
    editingTaskId = id;
    document.getElementById('modal-task-title').textContent = 'Edit Task';
    document.getElementById('task-title').value = t.title;
    document.getElementById('task-desc').value = t.desc || '';
    document.getElementById('task-assignee').value = t.assignee;
    document.getElementById('task-priority').value = t.priority;
    document.getElementById('task-status').value = t.status;
    document.getElementById('task-due').value = t.due || '';
    openModal('modal-task');
};

window.deleteTask = async function (id) {
    const tasks = await Store.getTasks();
    await Store.setTasks(tasks.filter(function (t) { return t.id !== id; }));
    await renderTasks();
};

// ═══════════════════ CONTENT PIPELINE ═══════════════════
var editingContentId = null;

var btnAddContent = document.getElementById('btn-add-content');
if (btnAddContent) {
    btnAddContent.addEventListener('click', function () {
        editingContentId = null;
        document.getElementById('modal-content-title').textContent = 'New Content';
        document.getElementById('content-title').value = '';
        document.getElementById('content-type').value = 'instagram';
        document.getElementById('content-stage').value = 'ideation';
        document.getElementById('content-idea').value = '';
        document.getElementById('content-script').value = '';
        document.getElementById('content-image-preview').style.display = 'none';
        openModal('modal-content');
    });
}

var fileArea = document.getElementById('file-upload-area');
var fileInput = document.getElementById('content-image');
if (fileArea && fileInput) {
    fileArea.addEventListener('click', function () { fileInput.click(); });
    fileInput.addEventListener('change', handleImageUpload);
    fileArea.addEventListener('dragover', function (e) { e.preventDefault(); fileArea.style.borderColor = 'var(--accent)'; });
    fileArea.addEventListener('dragleave', function () { fileArea.style.borderColor = ''; });
    fileArea.addEventListener('drop', function (e) {
        e.preventDefault(); fileArea.style.borderColor = '';
        if (e.dataTransfer.files[0]) { fileInput.files = e.dataTransfer.files; handleImageUpload(); }
    });
}

var currentImageData = null;
function handleImageUpload() {
    var file = fileInput.files[0];
    if (!file) return;
    var reader = new FileReader();
    reader.onload = function (e) {
        currentImageData = e.target.result;
        var preview = document.getElementById('content-image-preview');
        preview.src = currentImageData;
        preview.style.display = 'block';
    };
    reader.readAsDataURL(file);
}

var btnSaveContent = document.getElementById('btn-save-content');
if (btnSaveContent) {
    btnSaveContent.addEventListener('click', async function () {
        var title = document.getElementById('content-title').value.trim();
        if (!title) return;
        var items = await Store.getContent();
        var data = {
            title: title,
            type: document.getElementById('content-type').value,
            stage: document.getElementById('content-stage').value,
            idea: document.getElementById('content-idea').value.trim(),
            script: document.getElementById('content-script').value.trim(),
            image: currentImageData || null,
        };
        if (editingContentId) {
            var idx = items.findIndex(function (c) { return c.id === editingContentId; });
            if (idx !== -1) items[idx] = Object.assign({}, items[idx], data);
        } else {
            items.push(Object.assign({ id: uid() }, data));
        }
        await Store.setContent(items);
        currentImageData = null;
        closeModals();
        await renderPipeline();
    });
}

async function renderPipeline() {
    var items = await Store.getContent();
    var stages = ['ideation', 'research', 'script', 'design', 'review', 'published'];
    stages.forEach(function (stage) {
        var container = document.getElementById('stage-' + stage);
        if (!container) return;
        var stageItems = items.filter(function (c) { return c.stage === stage; });
        container.innerHTML = stageItems.map(function (c) {
            return '<div class="content-card" draggable="true" data-id="' + c.id + '">'
                + '<div class="content-card-type">' + c.type + '</div>'
                + '<div class="content-card-title">' + esc(c.title) + '</div>'
                + (c.idea ? '<div class="content-card-snippet">' + esc(c.idea) + '</div>' : '')
                + (c.image ? '<img class="content-card-thumb" src="' + c.image + '" alt="attachment">' : '')
                + '<div class="content-card-actions"><button class="task-action-btn" onclick="editContent(\'' + c.id + '\')">Edit</button><button class="task-action-btn delete" onclick="deleteContent(\'' + c.id + '\')">Del</button></div>'
                + '</div>';
        }).join('');
    });
    initDragDrop('content-card', 'stage-items', async function (cardId, newStage) {
        var items = await Store.getContent();
        var c = items.find(function (x) { return x.id === cardId; });
        if (c) c.stage = newStage;
        await Store.setContent(items);
        await renderPipeline();
    });
}

window.editContent = async function (id) {
    var items = await Store.getContent();
    var c = items.find(function (x) { return x.id === id; });
    if (!c) return;
    editingContentId = id;
    document.getElementById('modal-content-title').textContent = 'Edit Content';
    document.getElementById('content-title').value = c.title;
    document.getElementById('content-type').value = c.type;
    document.getElementById('content-stage').value = c.stage;
    document.getElementById('content-idea').value = c.idea || '';
    document.getElementById('content-script').value = c.script || '';
    var preview = document.getElementById('content-image-preview');
    if (c.image) { preview.src = c.image; preview.style.display = 'block'; currentImageData = c.image; }
    else { preview.style.display = 'none'; currentImageData = null; }
    openModal('modal-content');
};

window.deleteContent = async function (id) {
    const items = await Store.getContent();
    await Store.setContent(items.filter(function (c) { return c.id !== id; }));
    await renderPipeline();
};

// ═══════════════════ CALENDAR ═══════════════════
var calYear = 2026, calMonth = 1;

var btnCalPrev = document.getElementById('cal-prev');
var btnCalNext = document.getElementById('cal-next');

if (btnCalPrev) btnCalPrev.addEventListener('click', async function () { calMonth--; if (calMonth < 0) { calMonth = 11; calYear--; } await renderCalendar(); });
if (btnCalNext) btnCalNext.addEventListener('click', async function () { calMonth++; if (calMonth > 11) { calMonth = 0; calYear++; } await renderCalendar(); });

async function renderCalendar() {
    var months = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
    var label = document.getElementById('cal-month-label');
    if (label) label.textContent = months[calMonth] + ' ' + calYear;
    var grid = document.getElementById('calendar-grid');
    if (!grid) return;
    var days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
    var html = days.map(function (d) { return '<div class="cal-day-header">' + d + '</div>'; }).join('');
    var firstDay = new Date(calYear, calMonth, 1).getDay();
    var daysInMonth = new Date(calYear, calMonth + 1, 0).getDate();
    var prevDays = new Date(calYear, calMonth, 0).getDate();
    var today = new Date();
    for (var i = firstDay - 1; i >= 0; i--) {
        html += '<div class="cal-day other-month"><div class="cal-day-num">' + (prevDays - i) + '</div></div>';
    }
    for (var d = 1; d <= daysInMonth; d++) {
        var date = new Date(calYear, calMonth, d);
        var isToday = date.toDateString() === today.toDateString();
        var isWeekday = date.getDay() > 0 && date.getDay() < 6;
        var events = '';
        CRON_EVENTS.forEach(function (ev) {
            if (ev.repeat === 'daily' || (ev.repeat === 'weekday' && isWeekday)) {
                events += '<div class="cal-event ' + ev.type + '">' + ev.title + '</div>';
            }
        });
        var tasks = await Store.getTasks();
        tasks.forEach(function (t) {
            if (t.due === calYear + '-' + String(calMonth + 1).padStart(2, '0') + '-' + String(d).padStart(2, '0')) {
                events += '<div class="cal-event task">' + t.title.substring(0, 20) + '…</div>';
            }
        });
        html += '<div class="cal-day' + (isToday ? ' today' : '') + '"><div class="cal-day-num">' + d + '</div>' + events + '</div>';
    }
    var totalCells = firstDay + daysInMonth;
    var remaining = (7 - (totalCells % 7)) % 7;
    for (var r = 1; r <= remaining; r++) {
        html += '<div class="cal-day other-month"><div class="cal-day-num">' + r + '</div></div>';
    }
    grid.innerHTML = html;
}

// ═══════════════════ ANALYTICS ═══════════════════
async function renderAnalytics() {
    var data = await apiFetch('/api/metrics');
    if (!data) data = { metrics: {}, leads_found: 0, emails_sent: 0, replies_received: 0, meetings_booked: 0, calls_made: 0, proposals_sent: 0 };
    // Unwrap metrics from data.metrics (backend wraps them)
    var m = data.metrics || {};
    var leads_found = data.leads_found != null ? data.leads_found : (m.leads_found || 0);
    var emails_sent = data.emails_sent != null ? data.emails_sent : (m.emails_sent || 0);
    var replies_received = data.replies_received != null ? data.replies_received : (m.replies_received || 0);
    var meetings_booked = data.meetings_booked != null ? data.meetings_booked : (m.meetings_booked || 0);
    var calls_made = data.calls_made != null ? data.calls_made : (m.calls_made || 0);
    var proposals_sent = data.proposals_sent != null ? data.proposals_sent : (m.proposals_sent || 0);
    var el = (id) => document.getElementById(id);
    if(el('stat-leads')) el('stat-leads').textContent = leads_found || 0;
    if(el('stat-emails')) el('stat-emails').textContent = emails_sent || 0;
    if(el('stat-replies')) el('stat-replies').textContent = replies_received || 0;
    if(el('stat-meetings')) el('stat-meetings').textContent = meetings_booked || 0;
    if(el('stat-calls')) el('stat-calls').textContent = calls_made || 0;
    if(el('stat-proposals')) el('stat-proposals').textContent = proposals_sent || 0;

    // Funnel
    var contacted = emails_sent || 0;
    var replied = replies_received || 0;
    var booked = meetings_booked || 0;
    if(el('funnel-leads')) el('funnel-leads').style.width = '100%';
    if(el('funnel-contacted')) el('funnel-contacted').style.width = Math.min(100, (contacted / Math.max(leads_found, 1)) * 100) + '%';
    if(el('funnel-replied')) el('funnel-replied').style.width = Math.min(100, (replied / Math.max(leads_found, 1)) * 100) + '%';
    if(el('funnel-booked')) el('funnel-booked').style.width = Math.min(100, (booked / Math.max(leads_found, 1)) * 100) + '%';
    if(el('fv-leads')) el('fv-leads').textContent = leads_found;
    if(el('fv-contacted')) el('fv-contacted').textContent = contacted;
    if(el('fv-replied')) el('fv-replied').textContent = replied;
    if(el('fv-booked')) el('fv-booked').textContent = booked;

    // Live Feed
    refreshLiveFeed();
}

async function refreshLiveFeed() {
    var data = await apiFetch('/api/logs');
    var feed = document.getElementById('live-feed');
    if (!feed) return;
    if (!data || !data.logs || data.logs.length === 0) {
        feed.innerHTML = '<div class="feed-empty">Waiting for activity...</div>';
        return;
    }
    feed.innerHTML = data.logs.slice().reverse().map(function (entry) {
        return '<div class="feed-entry"><span class="feed-time">' + esc(entry.ts) + '</span><span class="feed-msg">' + esc(entry.msg) + '</span></div>';
    }).join('');
}

// ═══════════════════ LEAD PIPELINE ═══════════════════
async function renderLeads() {
    var tbody = document.getElementById('leads-tbody');
    if (!tbody) return;
    tbody.innerHTML = '<tr><td colspan="6" class="leads-empty">Loading mission-critical leads...</td></tr>';
    
    var data = await apiFetch('/api/leads');
    if (!data) {
        tbody.innerHTML = '<tr><td colspan="6" class="leads-empty">⚠️ Cannot reach server. Is Nova running?</td></tr>';
        return;
    }
    if (!data.leads || data.leads.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="leads-empty">No leads in pipeline. Click Hunt Leads to start.</td></tr>';
        return;
    }

    tbody.innerHTML = data.leads.map(function (lead) {
        var score = lead.score || 0;
        var scoreClass = score >= 80 ? 'health-ok' : (score >= 50 ? 'health-warn' : 'health-error');
        var statusMap = {
            'New': '🟢', 'Contacted': '🔵', 'Replied': '🟡',
            'Meeting Booked': '🟣', 'Email Sent': '📧', 'Denied': '🔴'
        };
        var statusIcon = statusMap[lead.status] || '⚪';
        return '<tr>'
            + '<td>' + esc(lead.business || '') + '</td>'
            + '<td>' + esc(lead.contact || '') + '</td>'
            + '<td>' + esc(lead.phone || '') + '</td>'
            + '<td>' + esc(lead.vertical || '') + '</td>'
            + '<td><span class="health-value ' + scoreClass + '">' + score + '</span></td>'
            + '<td>' + statusIcon + ' ' + esc(lead.status || 'New') + '</td>'
            + '</tr>';
    }).join('');
}

var btnRefreshLeads = document.getElementById('btn-refresh-leads');
if (btnRefreshLeads) btnRefreshLeads.addEventListener('click', function () { renderLeads(); });

// ═══════════════════ MEMORY BANK ═══════════════════
var memSearch = document.getElementById('memory-search');
if (memSearch) memSearch.addEventListener('input', async () => await renderMemories());

async function renderMemories() {
    var searchEl = document.getElementById('memory-search');
    var query = searchEl ? searchEl.value.toLowerCase() : '';
    const storedMemories = await Store.getMemories();
    var memories = storedMemories.filter(function (m) {
        return !query || m.title.toLowerCase().indexOf(query) > -1 || m.body.toLowerCase().indexOf(query) > -1 || m.tag.indexOf(query) > -1;
    });
    var grid = document.getElementById('memory-grid');
    if (!grid) return;
    grid.innerHTML = memories.map(function (m) {
        return '<div class="memory-card">'
            + '<button class="memory-card-delete" onclick="deleteMemory(\'' + m.id + '\')" title="Delete">✕</button>'
            + '<span class="memory-card-tag ' + m.tag + '">' + m.tag + '</span>'
            + '<div class="memory-card-title">' + esc(m.title) + '</div>'
            + '<div class="memory-card-body">' + esc(m.body) + '</div>'
            + '<div class="memory-card-date">' + m.date + '</div>'
            + '</div>';
    }).join('');
}

window.deleteMemory = async function (id) {
    const memories = await Store.getMemories();
    await Store.setMemories(memories.filter(function (m) { return m.id !== id; }));
    await renderMemories();
};

// ═══════════════════ TEAM STRUCTURE ═══════════════════
function renderTeam() {
    var chart = document.getElementById('org-chart');
    if (!chart) return;
    var depts = { Leadership: [], Engineering: [], Creative: [], Sales: [], Operations: [], Analytics: [], Intelligence: [] };
    AGENTS.forEach(function (a) { if (depts[a.dept]) depts[a.dept].push(a); });

    var html = '<div class="org-tier"><div class="org-tier-label">Leadership</div>' + depts.Leadership.map(function (a) { return agentCard(a, true); }).join('') + '</div>';
    var groups = [
        { label: 'Engineering', agents: depts.Engineering },
        { label: 'Creative', agents: depts.Creative },
        { label: 'Sales', agents: depts.Sales },
        { label: 'Operations', agents: depts.Operations },
        { label: 'Analytics', agents: depts.Analytics },
        { label: 'Intelligence', agents: depts.Intelligence },
    ];
    html += '<div class="org-tier" style="gap:16px"><div class="org-connector"></div>'
        + groups.map(function (g) {
            return '<div style="display:flex;flex-direction:column;align-items:center;gap:12px"><div class="org-tier-label">' + g.label + '</div><div style="display:flex;gap:16px;flex-wrap:wrap;justify-content:center">' + g.agents.map(function (a) { return agentCard(a, false); }).join('') + '</div></div>';
        }).join('') + '</div>';
    chart.innerHTML = html;
}

function agentCard(a, isLeader) {
    return '<div class="agent-card ' + (isLeader ? 'leader' : '') + '">'
        + '<div class="agent-avatar" style="background:' + a.color + '">' + a.initial + '</div>'
        + '<div class="agent-name">' + a.name + '</div>'
        + '<div class="agent-role">' + a.role + '</div>'
        + '<div class="agent-dept">' + a.dept + '</div>'
        + '<div class="agent-desc">' + a.desc + '</div>'
        + '<div class="agent-status-badge ' + a.status + '"><span class="status-dot ' + (a.status === 'working' ? 'online' : '') + '"></span>' + (a.status === 'working' ? 'Working' : 'Idle') + '</div>'
        + '</div>';
}

// ═══════════════════ DIGITAL OFFICE ═══════════════════
async function refreshAgents() {
    var data = await apiFetch('/api/agents');
    if (!data) return;

    // Map backend agent_key -> frontend agent_id
    var keyToId = {
        "Nova":     "nova",
        "Hawk":     "hawk",
        "Closer":   "closer",
        "Quill":    "quill",
        "Sentinel": "sentinel",
        "Oracle":   "oracle"
    };

    var agentData = {};
    Object.keys(data).forEach(function (k) {
        var id = keyToId[k];
        if (id) agentData[id] = data[k];
    });

    AGENTS.forEach(function (agent) {
        var bd = agentData[agent.id];
        if (bd) {
            agent.status = (bd.status === 'active' || bd.status === 'online') ? 'working' : 'idle';
            if (bd.last_action && bd.last_action !== 'Never') {
                agent.task = bd.last_action;
            }
        }
    });

    if (document.getElementById('screen-team').classList.contains('active')) renderTeam();
    if (document.getElementById('screen-office').classList.contains('active')) renderOffice();
}

function renderOffice() {
    var floor = document.getElementById('office-floor');
    if (!floor) return;
    floor.innerHTML = AGENTS.map(function (a) {
        return '<div class="desk-unit ' + a.status + '">'
            + '<div class="desk-person" style="background:' + a.color + '"><div class="desk-status-ring"></div>' + a.initial + '</div>'
            + '<div class="desk-name">' + a.name + '</div>'
            + '<div class="desk-role">' + a.role + '</div>'
            + '<div class="desk-monitor"><div class="desk-monitor-content">' + (a.status === 'working' ? monitorText(a) : '> idle...') + '</div></div>'
            + '<div class="desk-monitor-stand"></div>'
            + '<div class="desk-current-task">' + (a.task || '—') + '</div>'
            + '<div class="desk-status-label ' + a.status + '"><span class="desk-status-indicator"></span>' + (a.status === 'working' ? 'Working' : 'Idle') + '</div>'
            + '</div>';
    }).join('');
}

function monitorText(agent) {
    var lines = {
        nova: '> autonomous brain...\n> overseeing loop\n> state: online',
        atlas: '> static check OK\n> dev env active\n> _',
        pixel: '> render B&W\n> applying filters\n> exporting 1080px',
        quill: '> drafting copy\n> A/B testing...\n> subject line v3',
        hawk: '> lead hunt active\n> query: ' + (agent.task || 'default') + '\n> scraping...',
        closer: '> monitor: agentmail\n> checking replies\n> polling...',
        sentinel: '> sentinel active\n> logs: healthy\n> uptime: 100%',
        echo: '> idle\n> awaiting leads\n> _',
        oracle: '> analytics engine\n> funnel: tracking\n> ROI: calculating...',
        viper: '> stealth mode\n> anti-bot: active\n> proxies: rotating...',
    };
    return lines[agent.id] || '> processing...';
}

// ═══════════════════ QUICK ACTIONS ═══════════════════
var btnHunt = document.getElementById('btn-hunt-leads');
if (btnHunt) {
    btnHunt.addEventListener('click', async function () {
        var btn = this;
        btn.classList.add('loading');
        showToast('🎯 Hunting leads...', 'info');
        var data = await apiFetch('/api/actions/hunt-leads', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}) });
        btn.classList.remove('loading');
        if (data && data.status === 'ok') {
            showToast('✅ Lead hunt complete!', 'success');
        } else {
            showToast('❌ ' + (data ? (data.detail || data.message || 'Lead hunt failed') : 'Network error'), 'error');
        }
    });
}

var btnSendEmails = document.getElementById('btn-send-emails');
if (btnSendEmails) {
    btnSendEmails.addEventListener('click', async function () {
        var btn = this;
        btn.classList.add('loading');
        showToast('📧 Sending email batch...', 'info');
        var data = await apiFetch('/api/actions/send-emails', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}) });
        btn.classList.remove('loading');
        showToast((data && data.status === 'ok') ? (data.message || '✅ Outreach check complete') : '❌ Outreach check failed', 'error');
    });
}

var btnReport = document.getElementById('btn-ceo-report');
if (btnReport) {
    btnReport.addEventListener('click', async function () {
        var btn = this;
        btn.classList.add('loading');
        showToast('📊 Generating CEO report...', 'info');
        var data = await apiFetch('/api/actions/generate-report', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}) });
        btn.classList.remove('loading');
        if (data && data.report) {
            showToast('✅ Report generated! Check Telegram.', 'success');
        } else {
            showToast('❌ ' + (data ? (data.detail || data.message || 'Report failed') : 'Network error'), 'error');
        }
    });
}

// ═══════════════════ NOTIFICATIONS ═══════════════════
var notifBell = document.getElementById('notif-bell');
var notifDropdown = document.getElementById('notif-dropdown');

if (notifBell) {
    notifBell.addEventListener('click', function (e) {
        e.stopPropagation();
        notifDropdown.classList.toggle('visible');
        if (notifDropdown.classList.contains('visible')) refreshNotifications();
    });
}

document.addEventListener('click', function () { if (notifDropdown) notifDropdown.classList.remove('visible'); });
if (notifDropdown) notifDropdown.addEventListener('click', function (e) { e.stopPropagation(); });

var btnReadNotifs = document.getElementById('notif-read-all');
if (btnReadNotifs) {
    btnReadNotifs.addEventListener('click', async function () {
        await apiFetch('/api/notifications/read', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id: 'all' }) });
        refreshNotifications();
    });
}

async function refreshNotifications() {
    var data = await apiFetch('/api/notifications');
    var list = document.getElementById('notif-list');
    var badge = document.getElementById('notif-badge');
    if (!list) return;
    if (!data || !data.notifications || data.notifications.length === 0) {
        list.innerHTML = '<div class="notif-empty">No notifications yet</div>';
        if (badge) badge.style.display = 'none';
        return;
    }
    var unread = data.notifications.filter(function (n) { return !n.read; }).length;
    if (unread > 0 && badge) {
        badge.textContent = unread;
        badge.style.display = 'flex';
    } else if (badge) {
        badge.style.display = 'none';
    }
    list.innerHTML = data.notifications.slice(0, 20).map(function (n) {
        var timeAgo = n.ts ? new Date(n.ts).toLocaleTimeString() : '';
        return '<div class="notif-item ' + (n.read ? '' : 'unread') + '">'
            + '<div class="notif-item-title">' + esc(n.title) + '</div>'
            + '<div class="notif-item-body">' + esc(n.body) + '</div>'
            + '<div class="notif-item-time">' + timeAgo + '</div>'
            + '</div>';
    }).join('');
}

// ═══════════════════ CHAT WIDGET ═══════════════════
var chatBubble = document.getElementById('chat-bubble');
var chatWindow = document.getElementById('chat-window');
var chatClose = document.getElementById('chat-close');
var chatInput = document.getElementById('chat-input');
var chatSend = document.getElementById('chat-send');
var chatMessages = document.getElementById('chat-messages');

if (chatBubble) {
    chatBubble.addEventListener('click', function () {
        chatWindow.classList.toggle('visible');
        if (chatWindow.classList.contains('visible')) chatInput.focus();
    });
}
if (chatClose) chatClose.addEventListener('click', function () { chatWindow.classList.remove('visible'); });

function addChatMessage(text, from) {
    if (!chatMessages) return;
    var div = document.createElement('div');
    div.className = 'chat-msg ' + from;
    div.textContent = text;
    chatMessages.appendChild(div);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

async function sendChat() {
    var msg = chatInput.value.trim();
    if (!msg) return;
    chatInput.value = '';
    addChatMessage(msg, 'user');
    addChatMessage('Thinking...', 'typing');

    var data = await apiFetch('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message: msg }) });

    var typing = chatMessages.querySelector('.typing');
    if (typing) typing.remove();

    if (data && data.response) {
        addChatMessage(data.response, 'nova');
    } else {
        addChatMessage('Sorry, I had trouble processing that. Try again!', 'nova');
    }
}

if (chatSend) chatSend.addEventListener('click', sendChat);
if (chatInput) chatInput.addEventListener('keypress', function (e) { if (e.key === 'Enter') sendChat(); });

// ═══════════════════ DECISION GATEWAY (APPROVALS) ═══════════════════
async function refreshPendingDrafts() {
    var data = await apiFetch('/api/approvals');
    var container = document.getElementById('pending-drafts-list');
    var badge = document.getElementById('draft-count');
    if (!container) return;

    if (!data || Object.keys(data).length === 0) {
        container.innerHTML = '<div class="feed-empty">No actions awaiting approval</div>';
        if (badge) badge.style.display = 'none';
        return;
    }

    const pending = Object.keys(data)
        .map(id => ({ id, ...data[id] }))
        .filter(req => req.status === 'pending');

    if (pending.length === 0) {
        container.innerHTML = '<div class="feed-empty">No actions awaiting approval</div>';
        if (badge) badge.style.display = 'none';
        return;
    }

    if (badge) {
        badge.textContent = pending.length;
        badge.style.display = 'inline';
    }

    container.innerHTML = pending.map(function (d) {
        return '<div class="draft-card" data-draft-id="' + esc(d.id) + '">'
            + '<div class="draft-header">'
            + '<span class="draft-to">#' + esc(d.id) + '</span>'
            + '<span class="draft-company">' + esc(d.action) + '</span>'
            + '</div>'
            + '<div class="draft-body" style="white-space: pre-wrap; font-size: 13px; color: var(--text-muted);">' + esc(d.details) + '</div>'
            + '<div class="draft-actions">'
            + '<button class="draft-btn approve" onclick="approveDraft(\'' + esc(d.id) + '\')">✅ Approve</button>'
            + '<button class="draft-btn deny" onclick="denyDraft(\'' + esc(d.id) + '\')">❌ Deny</button>'
            + '</div>'
            + '</div>';
    }).join('');
}

async function approveDraft(draftId) {
    showToast('✅ Sending email...', 'info');
    try {
        var res = await fetch(API + '/api/actions/approve-email', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id: draftId })
        });
        var data = await res.json();
        if (data.status === 'ok') {
            showToast('📤 ' + data.message, 'success');
            refreshPendingDrafts();
        } else {
            showToast('❌ ' + (data.detail || data.message || 'Failed'), 'error');
        }
    } catch (e) {
        showToast('❌ Network error', 'error');
    }
}

async function denyDraft(draftId) {
    try {
        var res = await fetch(API + '/api/actions/deny-email', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id: draftId })
        });
        var data = await res.json();
        if (data.status === 'ok') {
            showToast('🚫 ' + data.message, 'info');
            refreshPendingDrafts();
        } else {
            showToast('❌ ' + (data.detail || data.message || 'Failed'), 'error');
        }
    } catch (e) {
        showToast('❌ Network error', 'error');
    }
}

// ═══════════════════ SYSTEM HEALTH ═══════════════════
async function refreshHealth() {
    var data = await apiFetch('/api/health');
    if (!data) return;

    var el = function (id) { return document.getElementById(id); };

    if (el('health-uptime')) el('health-uptime').textContent = data.uptime || '—';
    if (el('health-errors')) {
        el('health-errors').textContent = data.errors || 0;
        el('health-errors').className = 'health-value ' + (data.errors > 0 ? 'health-error' : 'health-ok');
    }
    if (el('health-agents')) el('health-agents').textContent = (data.agents_online || 0) + '/4';
    if (el('health-pending')) el('health-pending').textContent = data.pending_emails || 0;

    if (data.scheduler) {
        if (el('health-fast')) el('health-fast').textContent = data.scheduler.fast_lane || '—';
        if (el('health-slow')) el('health-slow').textContent = data.scheduler.slow_lane || '—';
        if (el('health-email')) el('health-email').textContent = data.scheduler.email_drafter || '—';
        if (el('health-reply')) el('health-reply').textContent = data.scheduler.reply_monitor || '—';
    }
}

// ═══════════════════ METRICS SPARKLINE CHART ═══════════════════
async function refreshMetricsChart() {
    var data = await apiFetch('/api/metrics/history');
    if (!data || !data.history || data.history.length === 0) return;

    var canvas = document.getElementById('sparkline-canvas');
    var legend = document.getElementById('chart-legend');
    if (!canvas) return;

    var ctx = canvas.getContext('2d');
    var dpr = window.devicePixelRatio || 1;
    var rect = canvas.parentElement.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    ctx.scale(dpr, dpr);
    var W = rect.width, H = rect.height;

    ctx.clearRect(0, 0, W, H);

    var history = data.history;
    var series = {
        leads: { color: '#6366f1', label: 'Leads', vals: history.map(h => h.leads || 0) },
        emails: { color: '#3b82f6', label: 'Emails', vals: history.map(h => h.emails || 0) },
        replies: { color: '#10b981', label: 'Replies', vals: history.map(h => h.replies || 0) },
        meetings: { color: '#f59e0b', label: 'Meetings', vals: history.map(h => h.meetings || 0) }
    };

    var allVals = [];
    Object.keys(series).forEach(k => allVals = allVals.concat(series[k].vals));
    var maxVal = Math.max.apply(null, allVals) || 1;

    var padding = { top: 10, right: 10, bottom: 25, left: 10 };
    var chartW = W - padding.left - padding.right;
    var chartH = H - padding.top - padding.bottom;
    var n = history.length;

    Object.keys(series).forEach(key => {
        var s = series[key];
        ctx.beginPath();
        ctx.strokeStyle = s.color;
        ctx.lineWidth = 2;
        ctx.lineJoin = 'round';
        for (var i = 0; i < n; i++) {
            var x = padding.left + (i / Math.max(n - 1, 1)) * chartW;
            var y = padding.top + chartH - (s.vals[i] / maxVal) * chartH;
            if (i === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
        }
        ctx.stroke();

        for (var j = 0; j < n; j++) {
            var dx = padding.left + (j / Math.max(n - 1, 1)) * chartW;
            var dy = padding.top + chartH - (s.vals[j] / maxVal) * chartH;
            ctx.beginPath();
            ctx.arc(dx, dy, 3, 0, Math.PI * 2);
            ctx.fillStyle = s.color;
            ctx.fill();
        }
    });

    ctx.fillStyle = getComputedStyle(document.documentElement).getPropertyValue('--text-muted').trim() || '#64748b';
    ctx.font = '10px sans-serif';
    ctx.textAlign = 'center';
    var step = Math.max(1, Math.floor(n / 5));
    for (var i = 0; i < n; i += step) {
        var x = padding.left + (i / Math.max(n - 1, 1)) * chartW;
        var label = history[i].date ? history[i].date.slice(5) : '';
        ctx.fillText(label, x, H - 5);
    }

    if (legend) {
        legend.innerHTML = Object.keys(series).map(k => {
            var s = series[k];
            var latest = s.vals[s.vals.length - 1];
            return '<span style="color:' + s.color + '">● ' + s.label + ': ' + latest + '</span>';
        }).join('');
    }
}

// ═══════════════════ DRAG & DROP ═══════════════════
function initDragDrop(cardClass, containerClass, onDrop) {
    var cards = document.querySelectorAll('.' + cardClass);
    var containers = document.querySelectorAll('.' + containerClass);
    cards.forEach(function (card) {
        card.addEventListener('dragstart', function (e) {
            card.classList.add('dragging');
            e.dataTransfer.setData('text/plain', card.dataset.id);
        });
        card.addEventListener('dragend', function () { card.classList.remove('dragging'); });
    });
    containers.forEach(function (container) {
        container.addEventListener('dragover', function (e) { e.preventDefault(); container.classList.add('drag-over'); });
        container.addEventListener('dragleave', function () { container.classList.remove('drag-over'); });
        container.addEventListener('drop', function (e) {
            e.preventDefault(); container.classList.remove('drag-over');
            var cardId = e.dataTransfer.getData('text/plain');
            var targetStatus = container.id.replace('col-', '').replace('stage-', '');
            onDrop(cardId, targetStatus);
        });
    });
}

// ═══════════════════ HELPERS ═══════════════════
function esc(s) {
    if (!s) return '';
    var d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
}

// ═══════════════════ INIT ═══════════════════
renderTasks();
renderCalendar();
renderAnalytics();
refreshNotifications();
refreshHealth();
renderLeads();
refreshMetricsChart();
refreshPendingDrafts();

// ═══════════════════ SKILLS HUB ═══════════════════
async function renderSkillsHub() {
    var container = document.getElementById('skills-grid');
    if (!container) return;
    var data = await apiFetch('/api/skills');
    if (!data || !data.skills) {
        data = {
            skills: [
                { name: 'find_leads', category: 'Search', status: 'active', agent: 'Hawk' },
                { name: 'stealth_search', category: 'Search', status: 'active', agent: 'Viper' },
                { name: 'stealth_extract', category: 'Search', status: 'active', agent: 'Viper' },
                { name: 'bulk_scrape', category: 'Search', status: 'active', agent: 'Viper' },
                { name: 'deep_research', category: 'Research', status: 'active', agent: 'Hawk' },
                { name: 'run_seo_audit', category: 'Research', status: 'active', agent: 'Hawk' },
                { name: 'analyze_competitor', category: 'Research', status: 'active', agent: 'Hawk' },
                { name: 'send_outreach', category: 'Email', status: 'active', agent: 'Closer' },
                { name: 'create_drip_campaign', category: 'Email', status: 'active', agent: 'Quill' },
                { name: 'write_cold_email', category: 'Copy', status: 'active', agent: 'Quill' },
                { name: 'write_ad_copy', category: 'Copy', status: 'active', agent: 'Quill' },
                { name: 'write_content', category: 'Content', status: 'active', agent: 'Quill' },
                { name: 'create_instagram_post', category: 'Social', status: 'active', agent: 'Pixel' },
                { name: 'generate_ai_image', category: 'Creative', status: 'active', agent: 'Pixel' },
                { name: 'pipeline_report', category: 'Analytics', status: 'active', agent: 'Oracle' },
                { name: 'conversion_analysis', category: 'Analytics', status: 'active', agent: 'Oracle' },
                { name: 'roi_calculator', category: 'Analytics', status: 'active', agent: 'Oracle' },
                { name: 'trigger_retell_call', category: 'Outreach', status: 'active', agent: 'Closer' },
                { name: 'generate_proposal', category: 'Sales', status: 'active', agent: 'Closer' },
                { name: 'run_pipeline', category: 'Orchestration', status: 'active', agent: 'Nova' },
            ]
        };
    }
    container.innerHTML = data.skills.map(function (s) {
        var statusIcon = s.status === 'active' ? '🟢' : '🔴';
        return '<div class="skill-card">'
            + '<div class="skill-card-header">'
            + '<span class="skill-status">' + statusIcon + '</span>'
            + '<span class="skill-name">' + esc(s.name) + '</span>'
            + '</div>'
            + '<div class="skill-meta">'
            + '<span class="skill-category">' + esc(s.category) + '</span>'
            + '<span class="skill-agent">' + esc(s.agent) + '</span>'
            + '</div>'
            + '</div>';
    }).join('');
}

// ═══════════════════ PIPELINE RUNNER ═══════════════════
async function renderPipelineRunner() {
    var container = document.getElementById('pipeline-list');
    if (!container) return;
    var data = await apiFetch('/api/pipelines');
    if (!data || !data.pipelines) {
        data = {
            pipelines: [
                { name: 'full_outreach', label: 'Full Outreach', desc: 'Find → Research → Draft → Approve', steps: 3 },
                { name: 'morning_report', label: 'Morning Report', desc: 'Replies → Analytics → CEO Report', steps: 3 },
                { name: 'competitor_blitz', label: 'Competitor Blitz', desc: 'Find → SEO Audit → Compare', steps: 3 },
                { name: 'lead_enrich', label: 'Lead Enrichment', desc: 'Extract → Research → Save to Sheet', steps: 3 },
            ]
        };
    }
    container.innerHTML = data.pipelines.map(function (p) {
        return '<div class="pipeline-card">'
            + '<div class="pipeline-card-header">'
            + '<span class="pipeline-name">' + esc(p.label) + '</span>'
            + '<span class="pipeline-steps">' + p.steps + ' steps</span>'
            + '</div>'
            + '<div class="pipeline-desc">' + esc(p.desc) + '</div>'
            + '<button class="pipeline-run-btn" onclick="triggerPipeline(\'' + esc(p.name) + '\')">▶ Run</button>'
            + '</div>';
    }).join('');
}

window.triggerPipeline = async function (name) {
    showToast('🔄 Starting pipeline: ' + name + '...', 'info');
    var data = await apiFetch('/api/pipelines/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pipeline: name })
    });
    if (data && data.status === 'ok') {
        showToast('✅ Pipeline started! Check Telegram for results.', 'success');
    } else {
        showToast('❌ ' + (data ? (data.detail || data.message || 'Pipeline failed') : 'Network error'), 'error');
    }
};

// Intervals
setInterval(function () {
    refreshLiveFeed();
    refreshNotifications();
    refreshAgents();
    refreshPendingDrafts();
    refreshHealth();
    renderAnalytics();
}, 15000);

setInterval(function () {
    refreshMetricsChart();
    renderLeads();
}, 60000);

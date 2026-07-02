/* ─────────────────────────────────────────────
   OROVA Mission Control — Application Engine v2
   ───────────────────────────────────────────── */

const API = (window.location.origin === 'null' || window.location.protocol === 'file:')
    ? 'http://localhost:18789'
    : window.location.origin;
let currentClientId = 0; // 0 = OROVA Internal

// ═══════════════════ DATA LAYER ═══════════════════
const Store = {
    async getTasks() {
        const res = await apiFetch('/api/tasks');
        return res ? res.tasks : [];
    },
    async setTasks(tasks) {
        return await apiFetch('/api/tasks', {
            method: 'POST',
            body: JSON.stringify(tasks)
        });
    },
    async getContent() {
        const res = await apiFetch('/api/content');
        return res ? res.content : [];
    },
    async getMemories() {
        const res = await apiFetch('/api/memory');
        return res ? res.memories : [];
    },
    async getChatHistory() {
        const res = await apiFetch('/api/chat/history');
        return res ? res.history : [];
    }
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

// ═══════════════════ DEFAULT TASKS ═══════════════════
// [REMOVED] seedTasks is now handled by backend SQLite migrations.

// ═══════════════════ API HELPER ═══════════════════
const DASHBOARD_SECRET_KEY = 'OROVA_DASHBOARD_SECRET';
const SESSION_TOKEN_KEY = 'OROVA_SESSION_TOKEN';

function getDashboardSecret() {
    return sessionStorage.getItem(DASHBOARD_SECRET_KEY) || localStorage.getItem(DASHBOARD_SECRET_KEY) || '';
}

function setDashboardSecret(secret) {
    if (secret) {
        sessionStorage.setItem(DASHBOARD_SECRET_KEY, secret);
        localStorage.removeItem(DASHBOARD_SECRET_KEY);
    }
}

async function apiFetch(path, opts) {
    try {
        let fetchPath = path;
        opts = opts || {};
        opts.headers = opts.headers || {};

        // Send both credentials when available — a stale session token must
        // never mask a valid secret (tokens expire after 1h)
        const _sess = localStorage.getItem(SESSION_TOKEN_KEY);
        const secret = getDashboardSecret();
        if (_sess) opts.headers['X-Session-Token'] = _sess;
        if (secret) opts.headers['X-Dashboard-Secret'] = secret;

        // Set Content-Type automatically for JSON requests
        if (opts.body && typeof opts.body === 'string') {
            opts.headers['Content-Type'] = 'application/json';
        }

        // Ensure client_id is present
        const separator = fetchPath.includes('?') ? '&' : '?';
        fetchPath += `${separator}client_id=${currentClientId}`;

        let res = await fetch(API + fetchPath, opts);
        if (res.status === 401 || res.status === 403) {
            // A rejected call with a token means the token expired — drop it
            // and retry once with just the secret
            if (_sess) {
                localStorage.removeItem(SESSION_TOKEN_KEY);
                delete opts.headers['X-Session-Token'];
                if (secret) res = await fetch(API + fetchPath, opts);
            }
        }
        if (res.status === 401 || res.status === 403) {
            // Prompt once per page load — dozens of parallel calls fail
            // together and must not stack prompts
            if (!window.__reauthPrompted) {
                window.__reauthPrompted = true;
                const newSecret = prompt("Unauthorized. Paste your DASHBOARD_API_KEY (from Render environment settings):");
                if (newSecret && newSecret.trim()) {
                    setDashboardSecret(newSecret.trim());
                    window.location.reload();
                } else {
                    showToast('Dashboard is locked — click any button to enter your key', 'error');
                    window.__reauthPrompted = false; // allow retry on next click
                }
            }
            return null;
        }
        return await res.json();
    } catch (e) {
        console.warn('API error:', path, e);
        return null;
    }
}

// ═══════════════════ NOVA INTELLIGENCE ═══════════════════
function updateNovaStatus(msg) {
    const el = document.getElementById('nova-status');
    if (el) el.textContent = msg;
}

const NOVA_STATUSES = [
    "Analyzing Business Growth...",
    "Reviewing Client ROI...",
    "Routing Lead Sequences...",
    "Optimizing Ad Spend...",
    "Identifying Offer Gaps...",
    "Drafting CEO Commands..."
];

setInterval(() => {
    if (Math.random() > 0.7) {
        const randomStatus = NOVA_STATUSES[Math.floor(Math.random() * NOVA_STATUSES.length)];
        updateNovaStatus(randomStatus);
    }
}, 8000);

// ═══════════════════ TOAST SYSTEM ═══════════════════
function showToast(message, type) {
    type = type || 'info';
    var container = document.getElementById('toast-container');
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

hamburger.addEventListener('click', function () {
    hamburger.classList.toggle('open');
    sidebar.classList.toggle('open');
    sidebarOverlay.classList.toggle('visible');
});

sidebarOverlay.addEventListener('click', function () {
    hamburger.classList.remove('open');
    sidebar.classList.remove('open');
    sidebarOverlay.classList.remove('visible');
});

// ═══════════════════ NAVIGATION ═══════════════════
document.querySelectorAll('.nav-item').forEach(function (item) {
    item.addEventListener('click', async function () {
        document.querySelectorAll('.nav-item').forEach(function (n) { n.classList.remove('active'); });
        item.classList.add('active');
        var screen = item.dataset.screen;
        document.querySelectorAll('.screen').forEach(function (s) { s.classList.remove('active'); });
        document.getElementById('screen-' + screen).classList.add('active');
        // Close mobile sidebar
        hamburger.classList.remove('open');
        sidebar.classList.remove('open');
        sidebarOverlay.classList.remove('visible');
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
        if (screen === 'ceobrain') renderCEOBrain();
        if (screen === 'proofreader') renderProofreader();
        if (screen === 'improvement') renderImprovement();
        if (screen === 'lanes') renderLanes();
    });
});

// ═══════════════════ THEME TOGGLE ═══════════════════
var themeBtn = document.getElementById('theme-toggle');

// Quick Auth button (request short-lived session token)
var authBtn = document.getElementById('btn-get-session');
if (authBtn) authBtn.addEventListener('click', async function () { showToast('Requesting session token...', 'info'); const t = await window.requestSessionToken(3600); if (t) showToast('Session token saved', 'success'); else showToast('Session token failed', 'error'); });
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

overlay.addEventListener('click', function (e) { if (e.target === overlay) closeModals(); });
document.querySelectorAll('[data-close]').forEach(function (btn) { btn.addEventListener('click', closeModals); });

// ═══════════════════ TASK BOARD ═══════════════════
var editingTaskId = null;

document.getElementById('btn-add-task').addEventListener('click', function () {
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

document.getElementById('btn-save-task').addEventListener('click', async function () {
    var title = document.getElementById('task-title').value.trim();
    if (!title) return;

    var data = {
        id: editingTaskId || uid(),
        title: title,
        description: document.getElementById('task-desc').value.trim(),
        assignee: document.getElementById('task-assignee').value,
        priority: document.getElementById('task-priority').value,
        status: document.getElementById('task-status').value,
        due: document.getElementById('task-due').value,
    };

    showToast('💾 Saving task...', 'info');
    const res = await apiFetch('/api/tasks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    });

    if (res && res.status === 'ok') {
        showToast('✅ Task saved!', 'success');
        closeModals();
        await renderTasks();
    } else {
        showToast('❌ Failed to save task', 'error');
    }
});

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
        col.closest('.kanban-column').querySelector('.col-count').textContent = filtered.length;
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
    if (!confirm('Are you sure you want to delete this task?')) return;
    showToast('🗑️ Deleting task...', 'info');
    const res = await apiFetch('/api/tasks/delete', {
        method: 'POST',
        body: JSON.stringify({ id: id })
    });
    if (res && res.status === 'ok') {
        showToast('✅ Deleted', 'success');
        await renderTasks();
    }
};

// ═══════════════════ CONTENT PIPELINE ═══════════════════
var editingContentId = null;

document.getElementById('btn-add-content').addEventListener('click', function () {
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

var fileArea = document.getElementById('file-upload-area');
var fileInput = document.getElementById('content-image');
fileArea.addEventListener('click', function () { fileInput.click(); });
fileInput.addEventListener('change', handleImageUpload);
fileArea.addEventListener('dragover', function (e) { e.preventDefault(); fileArea.style.borderColor = 'var(--accent)'; });
fileArea.addEventListener('dragleave', function () { fileArea.style.borderColor = ''; });
fileArea.addEventListener('drop', function (e) {
    e.preventDefault(); fileArea.style.borderColor = '';
    if (e.dataTransfer.files[0]) { fileInput.files = e.dataTransfer.files; handleImageUpload(); }
});

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

document.getElementById('btn-save-content').addEventListener('click', async function () {
    var title = document.getElementById('content-title').value.trim();
    if (!title) return;

    var data = {
        id: editingContentId || uid(),
        title: title,
        type: document.getElementById('content-type').value,
        stage: document.getElementById('content-stage').value,
        idea: document.getElementById('content-idea').value.trim(),
        script: document.getElementById('content-script').value.trim(),
        image: currentImageData || null,
    };

    showToast('💾 Saving content...', 'info');
    const res = await apiFetch('/api/content', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    });

    if (res && res.status === 'ok') {
        showToast('✅ Content saved!', 'success');
        currentImageData = null;
        closeModals();
        await renderPipeline();
    } else {
        showToast('❌ Failed to save content', 'error');
    }
});

async function renderPipeline() {
    var items = await Store.getContent();
    var stages = ['ideation', 'research', 'script', 'design', 'review', 'published'];
    stages.forEach(function (stage) {
        var container = document.getElementById('stage-' + stage);
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
        const res = await apiFetch('/api/content', {
            method: 'POST',
            body: JSON.stringify({ id: cardId, stage: newStage })
        });
        if (res && res.status === 'ok') {
            await renderPipeline();
        }
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
    if (!confirm('Are you sure you want to delete this content item?')) return;
    showToast('🗑️ Deleting content...', 'info');
    const res = await apiFetch('/api/content/delete', {
        method: 'POST',
        body: JSON.stringify({ id: id })
    });
    if (res && res.status === 'ok') {
        showToast('✅ Deleted', 'success');
        await renderPipeline();
    }
};

// ═══════════════════ CALENDAR ═══════════════════
var calYear = 2026, calMonth = 1;

document.getElementById('cal-prev').addEventListener('click', async function () { calMonth--; if (calMonth < 0) { calMonth = 11; calYear--; } await renderCalendar(); });
document.getElementById('cal-next').addEventListener('click', async function () { calMonth++; if (calMonth > 11) { calMonth = 0; calYear++; } await renderCalendar(); });

async function renderCalendar() {
    var months = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
    document.getElementById('cal-month-label').textContent = months[calMonth] + ' ' + calYear;
    var grid = document.getElementById('calendar-grid');
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
    document.getElementById('stat-leads').textContent = leads_found || 0;
    document.getElementById('stat-emails').textContent = emails_sent || 0;
    document.getElementById('stat-replies').textContent = replies_received || 0;
    document.getElementById('stat-meetings').textContent = meetings_booked || 0;
    document.getElementById('stat-calls').textContent = calls_made || 0;
    document.getElementById('stat-proposals').textContent = proposals_sent || 0;

    var contacted = emails_sent || 0;
    var replied = replies_received || 0;
    var booked = meetings_booked || 0;
    document.getElementById('funnel-leads').style.width = '100%';
    document.getElementById('funnel-contacted').style.width = Math.min(100, (contacted / Math.max(leads_found, 1)) * 100) + '%';
    document.getElementById('funnel-replied').style.width = Math.min(100, (replied / Math.max(leads_found, 1)) * 100) + '%';
    document.getElementById('funnel-booked').style.width = Math.min(100, (booked / Math.max(leads_found, 1)) * 100) + '%';
    document.getElementById('fv-leads').textContent = leads_found;
    document.getElementById('fv-contacted').textContent = contacted;
    document.getElementById('fv-replied').textContent = replied;
    document.getElementById('fv-booked').textContent = booked;

    refreshLiveFeed();
}

async function refreshLiveFeed() {
    var data = await apiFetch('/api/logs');
    var feed = document.getElementById('live-feed');
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

document.getElementById('btn-refresh-leads').addEventListener('click', function () { renderLeads(); });

// ═══════════════════ MEMORY BANK ═══════════════════
document.getElementById('memory-search').addEventListener('input', async () => await renderMemories());

async function renderMemories() {
    var query = document.getElementById('memory-search').value.toLowerCase();
    const storedMemories = await Store.getMemories();
    var memories = storedMemories.filter(function (m) {
        return !query || m.title.toLowerCase().indexOf(query) > -1 || m.body.toLowerCase().indexOf(query) > -1 || m.tag.indexOf(query) > -1;
    });
    var grid = document.getElementById('memory-grid');
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
    if (!confirm('Are you sure you want to delete this memory?')) return;
    showToast('🗑️ Deleting memory...', 'info');
    const res = await apiFetch('/api/memory/delete', {
        method: 'POST',
        body: JSON.stringify({ id: id })
    });
    if (res && res.status === 'ok') {
        showToast('✅ Deleted', 'success');
        await renderMemories();
    }
};

// ═══════════════════ TEAM STRUCTURE ═══════════════════
function renderTeam() {
    var chart = document.getElementById('org-chart');
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
// ═══════════════════ DIGITAL OFFICE ═══════════════════
async function refreshAgents() {
    var data = await apiFetch('/api/agents');
    if (!data) return;

    // Map backend agent_key -> frontend agent_id
    var keyToId = {
        "Nova": "nova",
        "Hawk": "hawk",
        "Closer": "closer",
        "Quill": "quill",
        "Sentinel": "sentinel",
        "Oracle": "oracle"
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
document.getElementById('btn-hunt-leads').addEventListener('click', async function () {
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

document.getElementById('btn-send-emails').addEventListener('click', async function () {
    var btn = this;
    btn.classList.add('loading');
    showToast('📧 Sending email batch...', 'info');
    var data = await apiFetch('/api/actions/send-emails', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}) });
    btn.classList.remove('loading');
    showToast((data && data.status === 'ok') ? (data.message || '✅ Outreach check complete') : '❌ Outreach check failed', 'error');
});

document.getElementById('btn-ceo-report').addEventListener('click', async function () {
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

// ═══════════════════ NOTIFICATIONS ═══════════════════
var notifBell = document.getElementById('notif-bell');
var notifDropdown = document.getElementById('notif-dropdown');

notifBell.addEventListener('click', function (e) {
    e.stopPropagation();
    notifDropdown.classList.toggle('visible');
    if (notifDropdown.classList.contains('visible')) refreshNotifications();
});

document.addEventListener('click', function () { notifDropdown.classList.remove('visible'); });
notifDropdown.addEventListener('click', function (e) { e.stopPropagation(); });

document.getElementById('notif-read-all').addEventListener('click', async function () {
    await apiFetch('/api/notifications/read', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id: 'all' }) });
    refreshNotifications();
});

async function refreshNotifications() {
    var data = await apiFetch('/api/notifications');
    var list = document.getElementById('notif-list');
    var badge = document.getElementById('notif-badge');
    if (!data || !data.notifications || data.notifications.length === 0) {
        list.innerHTML = '<div class="notif-empty">No notifications yet</div>';
        badge.style.display = 'none';
        return;
    }
    var unread = data.notifications.filter(function (n) { return !n.read; }).length;
    if (unread > 0) {
        badge.textContent = unread;
        badge.style.display = 'flex';
    } else {
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

chatBubble.addEventListener('click', function () {
    chatWindow.classList.toggle('visible');
    if (chatWindow.classList.contains('visible')) chatInput.focus();
});
chatClose.addEventListener('click', function () { chatWindow.classList.remove('visible'); });

function addChatMessage(text, from) {
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

    // Remove typing indicator
    var typing = chatMessages.querySelector('.typing');
    if (typing) typing.remove();

    if (data && data.response) {
        addChatMessage(data.response, 'nova');
    } else {
        addChatMessage('Sorry, I had trouble processing that. Try again!', 'nova');
    }
}

chatSend.addEventListener('click', sendChat);
chatInput.addEventListener('keypress', function (e) { if (e.key === 'Enter') sendChat(); });

// ═══════════════════ PENDING EMAIL DRAFTS ═══════════════════
async function refreshPendingDrafts() {
    var data = await apiFetch('/api/pending-emails');
    var container = document.getElementById('pending-drafts-list');
    var badge = document.getElementById('draft-count');
    if (!container) return;

    if (!data || !data.pending || data.pending.length === 0) {
        container.innerHTML = '<div class="feed-empty">No drafts awaiting approval</div>';
        if (badge) badge.style.display = 'none';
        return;
    }

    if (badge) {
        badge.textContent = data.count;
        badge.style.display = 'inline';
    }

    container.innerHTML = data.pending.map(function (d) {
        return '<div class="draft-card" data-draft-id="' + esc(d.id) + '">'
            + '<div class="draft-header">'
            + '<span class="draft-to">' + esc(d.contact) + '</span>'
            + '<span class="draft-company">' + esc(d.company) + '</span>'
            + '</div>'
            + '<div class="draft-subject">📧 ' + esc(d.subject) + '</div>'
            + '<div class="draft-body">' + esc(d.body) + '</div>'
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
        var data = await apiFetch('/api/actions/approve-email', {
            method: 'POST',
            body: JSON.stringify({ id: draftId })
        });
        if (data && data.status === 'ok') {
            showToast('📤 ' + data.message, 'success');
            refreshPendingDrafts();
        } else {
            showToast('❌ ' + (data ? (data.detail || data.message || 'Failed') : 'Network error'), 'error');
        }
    } catch (e) {
        showToast('❌ Network error', 'error');
    }
}

async function denyDraft(draftId) {
    try {
        var data = await apiFetch('/api/actions/deny-email', {
            method: 'POST',
            body: JSON.stringify({ id: draftId })
        });
        if (data && data.status === 'ok') {
            showToast('🚫 ' + data.message, 'info');
            refreshPendingDrafts();
        } else {
            showToast('❌ ' + (data ? (data.detail || data.message || 'Failed') : 'Network error'), 'error');
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
    if (el('health-agents')) el('health-agents').textContent = (data.agents_online || 0) + '/6';
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
        leads: { color: '#6366f1', label: 'Leads', vals: history.map(function (h) { return h.leads || 0; }) },
        emails: { color: '#3b82f6', label: 'Emails', vals: history.map(function (h) { return h.emails || 0; }) },
        replies: { color: '#10b981', label: 'Replies', vals: history.map(function (h) { return h.replies || 0; }) },
        meetings: { color: '#f59e0b', label: 'Meetings', vals: history.map(function (h) { return h.meetings || 0; }) }
    };

    // Find global max for scaling
    var allVals = [];
    Object.keys(series).forEach(function (k) { allVals = allVals.concat(series[k].vals); });
    var maxVal = Math.max.apply(null, allVals) || 1;

    var padding = { top: 10, right: 10, bottom: 25, left: 10 };
    var chartW = W - padding.left - padding.right;
    var chartH = H - padding.top - padding.bottom;
    var n = history.length;

    // Draw each series line
    Object.keys(series).forEach(function (key) {
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

        // Draw dots at each data point
        for (var j = 0; j < n; j++) {
            var dx = padding.left + (j / Math.max(n - 1, 1)) * chartW;
            var dy = padding.top + chartH - (s.vals[j] / maxVal) * chartH;
            ctx.beginPath();
            ctx.arc(dx, dy, 3, 0, Math.PI * 2);
            ctx.fillStyle = s.color;
            ctx.fill();
        }
    });

    // Draw date labels on x-axis
    ctx.fillStyle = getComputedStyle(document.documentElement).getPropertyValue('--text-muted').trim() || '#64748b';
    ctx.font = '10px sans-serif';
    ctx.textAlign = 'center';
    var step = Math.max(1, Math.floor(n / 5));
    for (var i = 0; i < n; i += step) {
        var x = padding.left + (i / Math.max(n - 1, 1)) * chartW;
        var label = history[i].date ? history[i].date.slice(5) : '';
        ctx.fillText(label, x, H - 5);
    }

    // Update legend
    if (legend) {
        legend.innerHTML = Object.keys(series).map(function (k) {
            var s = series[k];
            var latest = s.vals[s.vals.length - 1];
            return '<span style="color:' + s.color + '">● ' + s.label + ': ' + latest + '</span>';
        }).join('');
    }
}

// ═══════════════════ LEADS TABLE ═══════════════════

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
        if (container.dataset.dragInitialized) return;
        container.dataset.dragInitialized = 'true';
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
// seedTasks(); // Handled by backend SQLite
renderTasks();
renderCalendar();
renderAnalytics();
refreshNotifications();
refreshHealth();
renderLeads();
refreshMetricsChart();
refreshPendingDrafts();

// Wire refresh leads button
var btnRefreshLeads = document.getElementById('btn-refresh-leads');
if (btnRefreshLeads) {
    btnRefreshLeads.addEventListener('click', function () {
        showToast('🔄 Refreshing leads...', 'info');
        renderLeads();
    });
}

// ═══════════════════ SKILLS HUB ═══════════════════
async function renderSkillsHub() {
    var container = document.getElementById('skills-grid');
    if (!container) return;
    var data = await apiFetch('/api/skills');
    if (!data || !data.skills) {
        // Fallback to hardcoded skills list
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

// ═══════════════════ WORKSPACE SWITCHER ═══════════════════
async function loadWorkspaces() {
    try {
        const res = await apiFetch('/api/clients');
        const select = document.getElementById('workspace-switcher');
        if (select && res && res.clients) {
            let html = '<option value="0">OROVA Internal (Lead Gen)</option>';
            res.clients.forEach(c => {
                html += `<option value="${c.id}">${c.name} (${c.niche})</option>`;
            });
            select.innerHTML = html;
            select.value = currentClientId;
        }
    } catch (e) { console.error("Could not load workspaces", e); }
}

// ─── MODAL LOGIC (Agency Hub) ───
document.getElementById('add-client-btn')?.addEventListener('click', () => {
    openModal('modal-add-client');
});

document.getElementById('save-client-btn')?.addEventListener('click', async () => {
    const name = document.getElementById('client-name').value.trim();
    const niche = document.getElementById('client-niche').value.trim();
    const location = document.getElementById('client-location').value.trim();

    if (!name) {
        showToast('❌ Business Name is required', 'error');
        return;
    }

    showToast('🚀 Creating workspace...', 'info');

    try {
        const res = await apiFetch('/api/clients', {
            method: 'POST',
            body: JSON.stringify({ name, niche, location })
        });

        if (res && res.status === 'ok') {
            showToast(`✅ Workspace '${name}' created!`, 'success');
            closeModals();
            // Reset fields
            document.getElementById('client-name').value = '';
            document.getElementById('client-niche').value = '';
            document.getElementById('client-location').value = '';
            await loadWorkspaces();
        } else {
            showToast('❌ Failed to create workspace', 'error');
        }
    } catch (err) {
        showToast('❌ Network error', 'error');
    }
});

document.getElementById('workspace-switcher')?.addEventListener('change', async (e) => {
    currentClientId = parseInt(e.target.value);
    const selectedText = e.target.options[e.target.selectedIndex].text;
    showToast('Switched Workspace context to ' + selectedText);

    // Update active workspace label on the top bar
    const activeLabel = document.getElementById('active-workspace-name');
    if (activeLabel) {
        activeLabel.textContent = selectedText;
    }

    // Force immediate refresh of all components
    showToast('🔄 Synchronizing data...', 'info');
    await Promise.all([
        renderAnalytics(),
        renderLeads(),
        refreshAgents(),
        refreshNotifications(),
        refreshHealth(),
        refreshLiveFeed()
    ]);

    const activeScreen = document.querySelector('.nav-item.active');
    if (activeScreen) activeScreen.click();
});

document.addEventListener('DOMContentLoaded', () => {
    loadWorkspaces();
});

// ═══════════════════ CEO BRAIN ═══════════════════
async function renderCEOBrain() {
    var hc = await apiFetch('/api/health_check');
    if (hc && hc.health_score != null) {
        document.getElementById('cb-health-score').textContent = hc.health_score + '/100';
        document.getElementById('cb-health-score').className = 'stat-value ' + (hc.health_score >= 70 ? 'health-ok' : 'health-error');
    }
    if (hc && hc.alerts && hc.alerts.length > 0) {
        document.getElementById('cb-task-proposals').innerHTML = hc.alerts.map(function (a) {
            return '<div class="feed-entry">⚠️ ' + esc(a) + '</div>';
        }).join('');
    }
}

document.getElementById('btn-morning-brief')?.addEventListener('click', async function () {
    var btn = this; btn.classList.add('loading'); btn.textContent = '☀️ Generating...';
    showToast('☀️ Generating morning brief...', 'info');
    var data = await apiFetch('/api/morning_brief', { method: 'POST', body: '{}' });
    btn.classList.remove('loading'); btn.textContent = '☀️ Morning Brief';
    if (data && data.brief) {
        document.getElementById('cb-brief-output').textContent = data.brief;
        document.getElementById('cb-last-brief').textContent = new Date().toLocaleTimeString();
        showToast('✅ Brief generated!', 'success');
    } else {
        showToast('❌ Brief generation failed', 'error');
    }
});

document.getElementById('btn-health-check')?.addEventListener('click', async function () {
    var btn = this; btn.classList.add('loading');
    showToast('🩺 Running health check...', 'info');
    await renderCEOBrain();
    btn.classList.remove('loading');
    showToast('✅ Health check complete', 'success');
});

// ═══════════════════ PROOFREADER ═══════════════════
async function renderProofreader() {
    var data = await apiFetch('/api/outreach_outcomes?limit=100');
    if (!data || !data.outcomes) return;
    var outcomes = data.outcomes;
    var passed = outcomes.filter(function (o) { return o.result === 'sent' && o.quality_score >= 80; }).length;
    var rewritten = outcomes.filter(function (o) { return o.result === 'sent' && o.quality_score < 80; }).length;
    var rejected = outcomes.filter(function (o) { return o.result === 'rejected'; }).length;
    var scores = outcomes.map(function (o) { return o.quality_score || 0; });
    var avg = scores.length > 0 ? (scores.reduce(function (a, b) { return a + b; }, 0) / scores.length).toFixed(0) : '—';
    document.getElementById('pr-passed').textContent = passed;
    document.getElementById('pr-rewritten').textContent = rewritten;
    document.getElementById('pr-rejected').textContent = rejected;
    document.getElementById('pr-avg-score').textContent = avg;

    var historyEl = document.getElementById('pr-history');
    historyEl.innerHTML = outcomes.slice(0, 20).map(function (o) {
        return '<div class="feed-entry"><span class="feed-time">' + esc(o.recipient || '') + '</span><span class="feed-msg">' + esc(o.result) + ' (score: ' + (o.quality_score || '—') + ')</span></div>';
    }).join('') || '<div class="feed-empty">No proofreads yet</div>';
}

document.getElementById('btn-run-proofread')?.addEventListener('click', async function () {
    var to = document.getElementById('pr-to').value.trim();
    var subject = document.getElementById('pr-subject').value.trim();
    var body = document.getElementById('pr-body').value.trim();
    if (!to || !subject || !body) { showToast('❌ Fill in all fields', 'error'); return; }
    var btn = this; btn.classList.add('loading');
    showToast('🔍 Running proofreader...', 'info');
    var data = await apiFetch('/api/proofread', { method: 'POST', body: JSON.stringify({ to: to, subject: subject, body: body }) });
    btn.classList.remove('loading');
    var resultDiv = document.getElementById('pr-result');
    var verdictEl = document.getElementById('pr-verdict');
    var detailsEl = document.getElementById('pr-details');
    if (data && data.verdict) {
        resultDiv.style.display = 'block';
        var emoji = data.verdict === 'pass' ? '✅' : (data.verdict === 'rewrite' ? '✏️' : '🚫');
        verdictEl.innerHTML = '<strong style="font-size:1.2rem">' + emoji + ' Verdict: ' + data.verdict.toUpperCase() + '</strong> (Score: ' + data.score + '/100)';
        detailsEl.innerHTML = '<p><strong>Fixes:</strong> ' + esc(data.fixes) + '</p>';
        if (data.improved_body) {
            detailsEl.innerHTML += '<p><strong>Improved Body:</strong></p><pre style="background:var(--bg-tertiary);padding:0.5rem;border-radius:4px;font-size:0.8rem">' + esc(data.improved_body) + '</pre>';
        }
        showToast('✅ Proofread complete', 'success');
    } else {
        showToast('❌ Proofreader failed', 'error');
    }
});

// ═══════════════════ SELF-IMPROVEMENT ═══════════════════
async function renderImprovement() {
    var data = await apiFetch('/api/learned_strategies');
    if (!data || !data.strategies) return;
    var strategies = data.strategies;

    // Best framework
    var fw = strategies.find(function (s) { return s.strategy_type === 'email_framework' && s.active === 1; });
    if (fw) {
        document.getElementById('imp-best-framework').textContent = fw.strategy_value.toUpperCase();
        document.getElementById('imp-framework-meta').textContent = 'Win rate: ' + (fw.win_rate * 100).toFixed(0) + '% | n=' + fw.sample_size + ' | ' + fw.confidence;
    }
    // Best timing
    var timing = strategies.find(function (s) { return s.strategy_type === 'send_timing' && s.active === 1; });
    if (timing) {
        document.getElementById('imp-best-timing').textContent = timing.strategy_value + ':00';
        document.getElementById('imp-timing-meta').textContent = 'Win rate: ' + (timing.win_rate * 100).toFixed(0) + '% | n=' + timing.sample_size + ' | ' + timing.confidence;
    }
    // Best niche
    var niche = strategies.find(function (s) { return s.strategy_type === 'niche' && s.active === 1; });
    if (niche) {
        document.getElementById('imp-best-niche').textContent = niche.strategy_value || '—';
        document.getElementById('imp-niche-meta').textContent = 'ROI: ' + (niche.win_rate * 100).toFixed(0) + '% | n=' + niche.sample_size;
    }

    // Table
    var tableEl = document.getElementById('imp-strategies-table');
    tableEl.innerHTML = strategies.length > 0 ? strategies.map(function (s) {
        return '<div class="feed-entry"><span class="feed-time">' + esc(s.strategy_type) + '</span><span class="feed-msg">' + esc(s.strategy_value) + ' — win: ' + (s.win_rate * 100).toFixed(0) + '% (' + s.confidence + ')</span></div>';
    }).join('') : '<div class="feed-empty">No strategies learned yet</div>';
}

document.getElementById('btn-run-improvement')?.addEventListener('click', async function () {
    var btn = this; btn.classList.add('loading'); btn.textContent = '🔄 Running...';
    showToast('🔄 Running improvement loop...', 'info');
    var data = await apiFetch('/api/improvement_loop', { method: 'POST', body: '{}' });
    btn.classList.remove('loading'); btn.textContent = '🔄 Run Improvement';
    if (data && data.status === 'ok') {
        showToast('✅ Improvement loop complete!', 'success');
        await renderImprovement();
    } else {
        showToast('❌ Improvement loop failed', 'error');
    }
});

// ═══════════════════ WORKER LANES ═══════════════════
async function renderLanes() {
    // Each lane card's status is just a placeholder since lanes run on schedule
}

document.querySelectorAll('.lane-trigger').forEach(function (btn) {
    btn.addEventListener('click', async function () {
        var lane = this.dataset.lane;
        var statusEl = document.getElementById('lane-status-' + lane);
        statusEl.textContent = '▶ Running...';
        showToast('⚙️ Triggering Lane ' + lane + '...', 'info');
        var data = await apiFetch('/api/worker/trigger/lane/' + lane, { method: 'POST', body: '{}' });
        if (data && data.status === 'ok') {
            statusEl.textContent = '✅ Triggered';
            showToast('✅ Lane ' + lane + ' triggered!', 'success');
        } else {
            statusEl.textContent = '❌ Failed';
            showToast('❌ Lane trigger failed', 'error');
        }
        setTimeout(function () { statusEl.textContent = '⏳ Pending'; }, 5000);
    });
});

// Auto-refresh live feed, notifications, agents, drafts, health, and chart every 15s
setInterval(function () {
    if (document.hidden) return; // don't hammer the free-tier backend from background tabs
    refreshLiveFeed();
    refreshNotifications();
    refreshAgents();
    refreshPendingDrafts();
    refreshHealth();
    renderAnalytics();
    // Auto-refresh new dashboard screens when active
    if (document.getElementById('screen-ceobrain')?.classList.contains('active')) renderCEOBrain();
    if (document.getElementById('screen-proofreader')?.classList.contains('active')) renderProofreader();
    if (document.getElementById('screen-improvement')?.classList.contains('active')) renderImprovement();
    if (document.getElementById('screen-lanes')?.classList.contains('active')) renderLanes();
}, 15000);

// Refresh chart and leads every 60s (less frequent since data changes slowly)
setInterval(function () {
    if (document.hidden) return;
    refreshMetricsChart();
    renderLeads();
}, 60000);

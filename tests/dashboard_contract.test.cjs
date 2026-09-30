'use strict';

// Exercise production renderers with a minimal DOM; no server or live APIs.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { spawnSync } = require('node:child_process');
const root = path.resolve(__dirname, '..');
const source = fs.readFileSync(path.join(root, 'mission-control/js/app.js'), 'utf8');

function section(start, end) {
    const first = source.indexOf(start);
    const last = source.indexOf(end, first + start.length);
    assert.ok(first >= 0 && last > first, 'production renderer markers must exist');
    return source.slice(first, last);
}

function harness(extra = {}) {
    const nodes = new Map();
    const document = {
        getElementById(id) {
            if (!nodes.has(id)) nodes.set(id, {
                textContent: '', innerHTML: '', title: '', style: {},
                classList: { contains: () => false }
            });
            return nodes.get(id);
        }
    };
    const esc = value => String(value).replace(/[&<>"']/g, ch => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    })[ch]);
    const context = vm.createContext({ document, esc, ...extra });
    return { nodes, context };
}

test('unavailable metrics never become a zero pipeline', async () => {
    for (const response of [null, { status: 'error' },
        { metrics_available: false }, { metrics: { metrics_available: false, leads_found: 0 } }]) {
        const { nodes, context } = harness({ apiFetch: async () => response,
            refreshLiveFeed() { throw new Error('unavailable counts are not success'); } });
        vm.runInContext(section('async function renderAnalytics()', 'async function refreshLiveFeed()'), context);
        await vm.runInContext('renderAnalytics()', context);
        assert.equal(nodes.get('stat-leads').textContent, '—');
        assert.equal(nodes.get('stat-leads').title, 'Counts unavailable');
        assert.equal(nodes.get('fv-booked').textContent, '—');
        assert.equal(nodes.get('funnel-booked').style.width, '0%');
    }
});

test('verified empty and nonempty metrics retain actual values', async () => {
    for (const count of [0, 12]) {
        let feedRefreshes = 0;
        const { nodes, context } = harness({ apiFetch: async () => ({
            status: 'ok', metrics: { metrics_available: true, leads_found: count, emails_sent: count }
        }), refreshLiveFeed() { feedRefreshes++; } });
        vm.runInContext(section('async function renderAnalytics()', 'async function refreshLiveFeed()'), context);
        await vm.runInContext('renderAnalytics()', context);
        assert.equal(nodes.get('stat-leads').textContent, count);
        assert.equal(nodes.get('fv-contacted').textContent, count);
        assert.equal(feedRefreshes, 1);
    }
});

test('calendar reads tasks once and escapes saved titles', async () => {
    let reads = 0;
    const { nodes, context } = harness({ calYear: 2026, calMonth: 8, CRON_EVENTS: [],
        Store: { async getTasks() {
            reads++;
            return [{ due: '2026-09-30', title: '<img src=x>' },
                { due: '2026-09-01', title: 'Client discovery' }];
        } }
    });
    vm.runInContext(section('async function renderCalendar()', 'async function renderAnalytics()'), context);
    await vm.runInContext('renderCalendar()', context);
    assert.equal(reads, 1);
    assert.equal(nodes.get('cal-month-label').textContent, 'September 2026');
    const html = nodes.get('calendar-grid').innerHTML;
    assert.ok(html.includes('&lt;img src=x&gt;'));
    assert.ok(html.includes('Client discovery'));
    assert.ok(!html.includes('<img src=x>'));
    assert.ok(!html.includes('Cold Lead'));
});

test('agent response envelope is unwrapped without inventing execution', async () => {
    const agents = [{ id: 'nova', status: 'unknown', task: '' },
        { id: 'hawk', status: 'working', task: 'stale invented task' },
        { id: 'closer', status: 'unknown', task: '' }];
    let response = { status: 'ok', agents: {
        Nova: { status: 'online', last_action: 'Never' },
        Closer: { status: 'running', last_action: 'Recorded action' }
    } };
    const { context } = harness({ AGENTS: agents, apiFetch: async () => response,
        renderTeam() {}, renderOffice() {} });
    vm.runInContext(section('async function refreshAgents()', 'function renderOffice()'), context);
    await vm.runInContext('refreshAgents()', context);
    assert.equal(agents[0].status, 'available');
    assert.equal(agents[0].task, '');
    assert.equal(agents[1].status, 'unknown');
    assert.equal(agents[1].task, '');
    assert.equal(agents[2].status, 'working');
    assert.equal(agents[2].task, 'Recorded action');
    response = null;
    await vm.runInContext('refreshAgents()', context);
    assert.ok(agents.every(agent => agent.status === 'unknown' && agent.task === ''));
});

test('office labels and monitors display evidence, not fictional activity', () => {
    const { context } = harness();
    vm.runInContext(section('function agentStatusLabel(', 'function agentCard('), context);
    vm.runInContext(section('function monitorText(', '// ═══════════════════ QUICK ACTIONS'), context);
    assert.equal(vm.runInContext("agentStatusLabel('unknown')", context), 'Unverified');
    assert.equal(vm.runInContext("agentStatusLabel('available')", context), 'Configured');
    assert.equal(vm.runInContext("monitorText({status:'unknown',task:''})", context),
        '&gt; status: Unverified<br>&gt; No recorded action');
    assert.ok(vm.runInContext("monitorText({status:'working',task:'<script>'})", context)
        .includes('&lt;script&gt;'));
});

test('all production dashboard scripts parse', () => {
    for (const file of ['app.js', 'session.js', 'agents.js']) {
        const result = spawnSync(process.execPath, ['--check', path.join(root, 'mission-control/js', file)],
            { encoding: 'utf8' });
        assert.equal(result.status, 0, result.stderr);
    }
});

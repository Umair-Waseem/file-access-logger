const assert = require('assert');
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

const root = path.join(__dirname, '..');

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// Build a dashboard page with the real markup and script, using stubbed network calls
function createDashboard() {
    const markup = fs.readFileSync(path.join(root, 'templates', 'index.html'), 'utf8')
        .replace(/\{\{[^}]*\}\}/g, '')
        .replace(/\{%[^%]*%\}/g, '')
        .replace(/<script[^>]*src=[^>]*><\/script>/g, '');

    const dom = new JSDOM(markup, { runScripts: 'outside-only', url: 'http://localhost/' });
    const context = { dom, window: dom.window, statsCalls: 0, clearCalls: 0, handlers: {} };

    context.window.io = () => ({ on: (name, handler) => { context.handlers[name] = handler; } });
    context.window.console = console;
    context.stats = { total_events: 0, recent_events: 0, created: 0, modified: 0, deleted: 0 };
    context.clearOk = true;

    context.window.fetch = async (url) => {
        if (url === '/api/stats') {
            context.statsCalls++;
            if (context.statsFails) throw new Error('stats unavailable');
            if (context.statsDelay) await wait(context.statsDelay);
            return { ok: true, json: async () => context.stats };
        }
        if (url === '/api/initial_events') {
            return { ok: true, json: async () => ({ events: context.initialEvents || [] }) };
        }
        if (url === '/api/clear') {
            context.clearCalls++;
            return { ok: context.clearOk, json: async () => ({ status: 'success' }) };
        }
        throw new Error('unexpected url ' + url);
    };

    context.load = () => context.window.eval(
        fs.readFileSync(path.join(root, 'static', 'dashboard.js'), 'utf8'));
    return context;
}

function makeEvent(index, type) {
    return {
        timestamp: new Date().toISOString(),
        event_type: type,
        file_path: `/data/f${index}.txt`,
        directory: '/data',
        process_name: 'editor',
        pid: 100 + index,
        username: 'user'
    };
}

const tests = [];
const test = (name, fn) => tests.push([name, fn]);

test('newest event appears at the top of the table', async () => {
    const app = createDashboard();
    app.load();
    await wait(20);
    app.handlers['new_event'](makeEvent(1, 'File Created'));
    app.handlers['new_event'](makeEvent(2, 'File Created'));
    const body = app.window.document.getElementById('events-body');
    assert.strictEqual(body.firstElementChild.children[2].textContent, 'f2.txt');
});

test('table never holds more than twenty rows', async () => {
    const app = createDashboard();
    app.load();
    await wait(20);
    for (let i = 0; i < 30; i++) app.handlers['new_event'](makeEvent(i, 'File Created'));
    const body = app.window.document.getElementById('events-body');
    assert.strictEqual(body.children.length, 20);
});

test('row cap survives stray text nodes in the table body', async () => {
    const app = createDashboard();
    app.load();
    await wait(20);
    const body = app.window.document.getElementById('events-body');
    // Start from a table that already holds rows, with no empty-state placeholder left
    body.innerHTML = '';
    for (let i = 0; i < 21; i++) {
        const row = app.window.document.createElement('tr');
        row.appendChild(app.window.document.createElement('td'));
        body.appendChild(row);
    }
    body.appendChild(app.window.document.createTextNode('\n  '));
    app.handlers['new_event'](makeEvent(99, 'File Created'));
    assert.strictEqual(body.children.length, 20);
});

test('event details are rendered as text and never as markup', async () => {
    const app = createDashboard();
    app.load();
    await wait(20);
    app.handlers['new_event']({
        timestamp: new Date().toISOString(),
        event_type: 'File Created',
        file_path: '/data/<img src=x onerror=alert(1)>.txt',
        directory: '/data',
        process_name: '<script>bad()</script>',
        pid: 5,
        username: 'user'
    });
    const row = app.window.document.getElementById('events-body').firstElementChild;
    assert.strictEqual(row.querySelectorAll('img').length, 0);
    assert.strictEqual(row.querySelectorAll('script').length, 0);
    assert.ok(row.children[2].textContent.includes('<img'));
});

test('a burst of events triggers only one stats request', async () => {
    const app = createDashboard();
    app.load();
    await wait(20);
    const before = app.statsCalls;
    for (let i = 0; i < 50; i++) app.handlers['new_event'](makeEvent(i, 'File Created'));
    await wait(800);
    assert.strictEqual(app.statsCalls - before, 1);
});

test('a later burst triggers a further stats request', async () => {
    const app = createDashboard();
    app.load();
    await wait(20);
    for (let i = 0; i < 5; i++) app.handlers['new_event'](makeEvent(i, 'File Created'));
    await wait(800);
    const midpoint = app.statsCalls;
    for (let i = 0; i < 5; i++) app.handlers['new_event'](makeEvent(i, 'File Deleted'));
    await wait(800);
    assert.strictEqual(app.statsCalls - midpoint, 1);
});

test('badge class matches the event type', async () => {
    const app = createDashboard();
    app.load();
    await wait(20);
    app.handlers['new_event'](makeEvent(1, 'File Deleted'));
    app.handlers['new_event'](makeEvent(2, 'File Modified'));
    app.handlers['new_event'](makeEvent(3, 'File Created'));
    const rows = app.window.document.getElementById('events-body').children;
    assert.ok(rows[0].querySelector('.badge').className.includes('created'));
    assert.ok(rows[1].querySelector('.badge').className.includes('modified'));
    assert.ok(rows[2].querySelector('.badge').className.includes('deleted'));
});

test('per-type counts increase as events arrive', async () => {
    const app = createDashboard();
    app.load();
    await wait(20);
    app.handlers['new_event'](makeEvent(1, 'File Created'));
    app.handlers['new_event'](makeEvent(2, 'File Created'));
    app.handlers['new_event'](makeEvent(3, 'File Deleted'));
    const doc = app.window.document;
    assert.strictEqual(doc.getElementById('count-created').textContent, '2');
    assert.strictEqual(doc.getElementById('count-deleted').textContent, '1');
});

test('stats from the server replace the local counts', async () => {
    const app = createDashboard();
    app.stats = { total_events: 7, recent_events: 3, created: 4, modified: 2, deleted: 1 };
    app.load();
    await wait(50);
    const doc = app.window.document;
    assert.strictEqual(doc.getElementById('total-events').textContent, '7');
    assert.strictEqual(doc.getElementById('recent-events').textContent, '3');
    assert.strictEqual(doc.getElementById('count-created').textContent, '4');
});

test('initial events load oldest at the bottom', async () => {
    const app = createDashboard();
    app.initialEvents = [makeEvent(3, 'File Created'), makeEvent(2, 'File Created'),
                         makeEvent(1, 'File Created')];
    app.load();
    await wait(50);
    const body = app.window.document.getElementById('events-body');
    assert.strictEqual(body.firstElementChild.children[2].textContent, 'f3.txt');
    assert.strictEqual(body.lastElementChild.children[2].textContent, 'f1.txt');
});

test('a process without a pid is shown without one', async () => {
    const app = createDashboard();
    app.load();
    await wait(20);
    const event = makeEvent(1, 'File Created');
    event.pid = 0;
    event.process_name = 'Unknown Process';
    app.handlers['new_event'](event);
    const row = app.window.document.getElementById('events-body').firstElementChild;
    assert.strictEqual(row.children[4].textContent, 'Unknown Process');
});

test('clearing empties the table and resets the counts', async () => {
    const app = createDashboard();
    app.load();
    await wait(20);
    for (let i = 0; i < 3; i++) app.handlers['new_event'](makeEvent(i, 'File Created'));
    await app.window.performClear();
    await wait(50);
    const doc = app.window.document;
    assert.ok(doc.getElementById('events-body').querySelector('.empty-state'));
    assert.strictEqual(doc.getElementById('count-created').textContent, '0');
    assert.strictEqual(app.clearCalls, 1);
});

test('a failed clear reports an error and keeps the rows', async () => {
    const app = createDashboard();
    app.clearOk = false;
    app.load();
    await wait(20);
    app.handlers['new_event'](makeEvent(1, 'File Created'));
    await app.window.performClear();
    await wait(50);
    const doc = app.window.document;
    assert.strictEqual(doc.getElementById('events-body').children.length, 1);
    assert.ok(doc.querySelector('.notification'));
});

test('the cap discards the oldest rows and keeps the newest', async () => {
    const app = createDashboard();
    app.load();
    await wait(20);
    for (let i = 0; i < 30; i++) app.handlers['new_event'](makeEvent(i, 'File Created'));
    const body = app.window.document.getElementById('events-body');
    assert.strictEqual(body.firstElementChild.children[2].textContent, 'f29.txt');
    assert.strictEqual(body.lastElementChild.children[2].textContent, 'f10.txt');
});

test('a hostile event type is rendered as text in the badge', async () => {
    const app = createDashboard();
    app.load();
    await wait(20);
    app.handlers['new_event']({
        timestamp: new Date().toISOString(),
        event_type: 'File <img src=x onerror=alert(1)> Created',
        file_path: '/data/a.txt',
        directory: '/data',
        process_name: 'editor',
        pid: 5,
        username: 'user'
    });
    const badge = app.window.document.getElementById('events-body')
        .firstElementChild.querySelector('.badge');
    assert.strictEqual(badge.querySelectorAll('img').length, 0);
    assert.ok(badge.textContent.includes('<img'));
});

test('events spread over time still collapse into one stats request', async () => {
    const app = createDashboard();
    app.load();
    await wait(20);
    const before = app.statsCalls;
    for (let i = 0; i < 5; i++) {
        app.handlers['new_event'](makeEvent(i, 'File Created'));
        await wait(60);
    }
    await wait(700);
    assert.strictEqual(app.statsCalls - before, 1);
});

test('counts show zero immediately after clearing, before stats return', async () => {
    const app = createDashboard();
    app.load();
    await wait(20);
    for (let i = 0; i < 3; i++) app.handlers['new_event'](makeEvent(i, 'File Created'));
    app.stats = { total_events: 3, recent_events: 3, created: 3, modified: 0, deleted: 0 };
    app.statsDelay = 300;

    const pending = app.window.performClear();
    await wait(80);
    assert.strictEqual(app.window.document.getElementById('count-created').textContent, '0');
    await pending;
});

test('counts restart from zero when stats are unavailable after clearing', async () => {
    const app = createDashboard();
    app.stats = { total_events: 3, recent_events: 3, created: 3, modified: 0, deleted: 0 };
    app.load();
    await wait(20);
    for (let i = 0; i < 3; i++) app.handlers['new_event'](makeEvent(i, 'File Created'));
    await wait(700);

    // The dashboard clears while the stats endpoint is failing
    app.statsFails = true;
    app.window.console = { error: () => {}, log: () => {} };
    await app.window.performClear();
    await wait(50);

    app.handlers['new_event'](makeEvent(9, 'File Created'));
    assert.strictEqual(app.window.document.getElementById('count-created').textContent, '1');
});

test('the confirmation dialog opens and closes', async () => {
    const app = createDashboard();
    app.load();
    await wait(20);
    const modal = app.window.document.getElementById('confirmModal');
    app.window.showConfirmModal();
    assert.ok(modal.classList.contains('active'));
    app.window.hideConfirmModal();
    assert.ok(!modal.classList.contains('active'));
});

(async () => {
    let failures = 0;
    for (const [name, fn] of tests) {
        try {
            await fn();
            console.log('  ok   ' + name);
        } catch (error) {
            failures++;
            console.log('  FAIL ' + name + '\n       ' + error.message);
        }
    }
    console.log(`\nRan ${tests.length} tests, ${failures} failed`);
    process.exit(failures ? 1 : 0);
})();

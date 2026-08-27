const socket = io();
let eventCounts = {created:0, modified:0, deleted:0};
let clearButtonLock = false;
let statsTimer = null;

socket.on('new_event', function(eventData) {
    addEventToTable(eventData);
    updateEventCount(eventData.event_type);
    scheduleStatsUpdate();
});

// Collapse a burst of events into a single stats request
function scheduleStatsUpdate() {
    if(statsTimer) return;
    statsTimer = setTimeout(function() {
        statsTimer = null;
        updateStats();
    }, 500);
}

function addEventToTable(event) {
    const tbody = document.getElementById('events-body');

    if(tbody.querySelector('.empty-state')) {
        tbody.innerHTML = '';
    }

    const filePath = String(event.file_path || '');
    const time = new Date(event.timestamp).toLocaleTimeString();
    const filename = filePath.split(/[\\/]/).pop() || filePath;
    const directory = event.directory || '/';
    const eventType = String(event.event_type || '').toLowerCase();
    const processInfo = event.pid > 0 ? 
        `${event.process_name} (${event.pid})` : 
        (event.process_name || 'Unknown');

    let badgeClass = 'created';
    if(eventType.includes('modif')) badgeClass = 'modified';
    else if(eventType.includes('delete')) badgeClass = 'deleted';

    const newRow = document.createElement('tr');
    appendTextCell(newRow, time);
    appendBadgeCell(newRow, event.event_type || 'Unknown', badgeClass);
    appendTextCell(newRow, filename, 'filename');
    appendTextCell(newRow, directory, 'directory', directory);
    appendWrappedCell(newRow, processInfo, 'process');
    appendWrappedCell(newRow, event.username || 'Unknown', 'user');

    tbody.insertBefore(newRow, tbody.firstChild);

    while(tbody.children.length > 20) {
        tbody.removeChild(tbody.lastElementChild);
    }
}

function appendTextCell(row, text, className, title) {
    const cell = document.createElement('td');
    if(className) cell.className = className;
    if(title) cell.title = title;
    cell.textContent = text;
    row.appendChild(cell);
}

function appendBadgeCell(row, text, badgeClass) {
    const cell = document.createElement('td');
    const badge = document.createElement('span');
    badge.className = `badge ${badgeClass}`;
    badge.textContent = text;
    cell.appendChild(badge);
    row.appendChild(cell);
}

function appendWrappedCell(row, text, className) {
    const cell = document.createElement('td');
    const span = document.createElement('span');
    span.className = className;
    span.textContent = text;
    cell.appendChild(span);
    row.appendChild(cell);
}

function updateEventCount(eventType) {
    const type = String(eventType || '').toLowerCase();
    if(type.includes('create')) eventCounts.created++;
    else if(type.includes('modif')) eventCounts.modified++;
    else if(type.includes('delete')) eventCounts.deleted++;

    document.getElementById('count-created').textContent = eventCounts.created;
    document.getElementById('count-modified').textContent = eventCounts.modified;
    document.getElementById('count-deleted').textContent = eventCounts.deleted;
}

async function updateStats() {
    try {
        const response = await fetch('/api/stats');
        const stats = await response.json();
        document.getElementById('total-events').textContent = stats.total_events;
        document.getElementById('recent-events').textContent = stats.recent_events;
        document.getElementById('last-update').textContent = new Date().toLocaleTimeString();

        eventCounts.created = stats.created || 0;
        eventCounts.modified = stats.modified || 0;
        eventCounts.deleted = stats.deleted || 0;

        document.getElementById('count-created').textContent = eventCounts.created;
        document.getElementById('count-modified').textContent = eventCounts.modified;
        document.getElementById('count-deleted').textContent = eventCounts.deleted;
    } catch(error) {
        console.error('Error updating stats:', error);
    }
}

async function loadInitialEvents() {
    try {
        const response = await fetch('/api/initial_events');
        const data = await response.json();

        if(data.events.length > 0) {
            document.getElementById('events-body').innerHTML = '';
            data.events.slice().reverse().forEach(event => {
                addEventToTable(event);
            });
        }

        updateStats();
    } catch(error) {
        console.error('Error loading initial events:', error);
    }
}

// Custom Modal Functions
function showConfirmModal() {
    if(clearButtonLock) return;
    document.getElementById('confirmModal').classList.add('active');
}

function hideConfirmModal() {
    document.getElementById('confirmModal').classList.remove('active');
}

async function performClear() {
    hideConfirmModal();

    if(clearButtonLock) return;

    clearButtonLock = true;
    const btn = document.getElementById('clear-btn');
    const originalText = btn.textContent;

    btn.disabled = true;
    btn.textContent = 'Clearing...';

    try {
        const response = await fetch('/api/clear', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });

        if(response.ok) {
            await response.json();

            // Clear the table
            document.getElementById('events-body').innerHTML = `
                <tr><td colspan="6" class="empty-state">
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor">
                        <path d="M19.5 21a3 3 0 0 0 3-3v-4.5a3 3 0 0 0-3-3h-15a3 3 0 0 0-3 3V18a3 3 0 0 0 3 3h15ZM1.5 10.146V6a3 3 0 0 1 3-3h5.379a2.25 2.25 0 0 1 1.59.659l2.122 2.121c.14.141.331.22.53.22H19.5a3 3 0 0 1 3 3v1.146A4.483 4.483 0 0 0 19.5 9h-15a4.483 4.483 0 0 0-3 1.146Z"/>
                    </svg>
                    <div>All events cleared</div>
                    <div style="font-size:14px;margin-top:8px">Waiting for new file activity...</div>
                </td></tr>
            `;

            // Reset event counts
            eventCounts = {created:0, modified:0, deleted:0};
            document.getElementById('count-created').textContent = '0';
            document.getElementById('count-modified').textContent = '0';
            document.getElementById('count-deleted').textContent = '0';

            // Update stats
            await updateStats();

            showNotification('All events cleared successfully', 'success');
        } else {
            showNotification('Failed to clear events', 'error');
        }
    } catch(error) {
        console.error('Error during clear operation:', error);
        showNotification('Error clearing events: ' + error.message, 'error');
    } finally {
        // Reset button state after 1 second
        setTimeout(() => {
            btn.disabled = false;
            btn.textContent = originalText;
            clearButtonLock = false;
        }, 1000);
    }
}

function showNotification(message, type) {
    // Remove any existing notifications first
    document.querySelectorAll('.notification').forEach(n => n.remove());

    const notification = document.createElement('div');
    notification.className = 'notification';
    notification.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 12px 20px;
        border-radius: 8px;
        background: ${type === 'error' ? '#ef4444' : '#10b981'};
        color: white;
        font-weight: 500;
        z-index: 10000;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        animation: slideIn 0.3s ease;
    `;

    notification.textContent = message;
    document.body.appendChild(notification);

    setTimeout(() => {
        notification.style.animation = 'slideOut 0.3s ease';
        setTimeout(() => notification.remove(), 300);
    }, 3000);

    // Add animation styles if not present
    if (!document.querySelector('#notification-styles')) {
        const style = document.createElement('style');
        style.id = 'notification-styles';
        style.textContent = `
            @keyframes slideIn {
                from { transform: translateX(100%); opacity: 0; }
                to { transform: translateX(0); opacity: 1; }
            }
            @keyframes slideOut {
                from { transform: translateX(0); opacity: 1; }
                to { transform: translateX(100%); opacity: 0; }
            }
        `;
        document.head.appendChild(style);
    }
}

// Close modal when clicking outside
document.getElementById('confirmModal').addEventListener('click', function(e) {
    if(e.target === this) {
        hideConfirmModal();
    }
});

// Close modal with Escape key
document.addEventListener('keydown', function(e) {
    if(e.key === 'Escape') {
        hideConfirmModal();
    }
});

loadInitialEvents();
setInterval(updateStats, 60000);

import os
from html import escape

from flask import jsonify, request
from datetime import datetime, timedelta, timezone
from models import Session, FileEvent
import config


DIRECTORY_COLORS = ("var(--primary-blue)", "var(--success-green)", "#f9ab00")


def serialize_event(event):
    timestamp = event.timestamp or datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)

    file_path = event.file_path or ''

    return {
        'timestamp': timestamp.isoformat(),
        'event_type': event.event_type or 'Unknown',
        'file_path': file_path,
        'directory': os.path.dirname(file_path) or os.path.sep,
        'process_name': event.process_name or 'Unknown',
        'pid': event.pid or 0,
        'username': event.username or 'Unknown',
        'command': event.command or ''
    }


def create_routes(app):
    # Home route serving the dashboard HTML page
    @app.route('/')
    def index():
        directory_items = []
        for index, directory in enumerate(config.MONITOR_DIRS):
            color = DIRECTORY_COLORS[index % len(DIRECTORY_COLORS)]
            directory_items.append(f'''
                            <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
                                <div style="width:12px;height:12px;background:{color};border-radius:2px"></div>
                                <div>{escape(directory)}</div>
                            </div>''')

        directory_list_html = ''.join(directory_items) or '''
                            <div style="color:var(--neutral-text-light)">No directories configured</div>'''

        return '''
        <!DOCTYPE html>
        <html>
        <head>
            <title>File Access Logger</title>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                :root {
                    --primary-blue: #1a73e8;
                    --primary-blue-light: #4285f4;
                    --primary-blue-dark: #0d47a1;
                    --success-green: #34a853;
                    --warning-red: #ea4335;
                    --neutral-bg: #f5f7fa;
                    --neutral-card: #ffffff;
                    --neutral-border: #dadce0;
                    --neutral-text: #202124;
                    --neutral-text-light: #5f6368;
                    --neutral-hover: #f8f9fa;
                }
                *{margin:0;padding:0;box-sizing:border-box}
                body{font-family:'Google Sans',system-ui,-apple-system,sans-serif;background:var(--neutral-bg);color:var(--neutral-text);line-height:1.6}
                .container{max-width:1600px;margin:0 auto;padding:24px}
                .header{background:linear-gradient(135deg,var(--primary-blue-dark),var(--primary-blue));color:white;padding:32px;border-radius:12px;margin-bottom:32px;box-shadow:0 4px 12px rgba(26,115,232,0.15)}
                h1{font-size:32px;font-weight:500;margin-bottom:8px;letter-spacing:-0.5px}
                .subtitle{opacity:0.9;font-size:16px;margin-bottom:20px}
                .status{background:var(--success-green);color:white;padding:6px 16px;border-radius:20px;font-size:14px;font-weight:500;display:inline-flex;align-items:center;gap:6px}
                .status::before{content:'';width:8px;height:8px;background:white;border-radius:50%}
                .grid{display:grid;grid-template-columns:repeat(4,1fr);gap:24px;margin-bottom:32px}
                .card{background:var(--neutral-card);padding:24px;border-radius:12px;box-shadow:0 2px 8px rgba(0,0,0,0.08);border:1px solid var(--neutral-border);transition:transform 0.2s,box-shadow 0.2s}
                .card:hover{transform:translateY(-2px);box-shadow:0 4px 16px rgba(0,0,0,0.12)}
                .card h3{margin-bottom:20px;font-size:18px;font-weight:500;color:var(--primary-blue-dark);display:flex;align-items:center;gap:8px}
                .card h3::before{content:'';width:4px;height:20px;background:var(--primary-blue);border-radius:2px}
                .stats p{margin:12px 0;display:flex;justify-content:space-between;border-bottom:1px dashed var(--neutral-border);padding-bottom:8px}
                .stats strong{font-size:20px;color:var(--primary-blue)}
                .btn{background:var(--primary-blue);color:white;border:none;padding:10px 20px;border-radius:8px;cursor:pointer;font-size:14px;font-weight:500;transition:background 0.2s,transform 0.1s}
                .btn:hover{background:var(--primary-blue-dark);transform:scale(1.02)}
                .btn:active{transform:scale(0.98)}
                .btn:disabled{background:var(--neutral-text-light);cursor:not-allowed;transform:none}
                .btn-danger{background:var(--warning-red)}
                .btn-danger:hover{background:#d23a2e}
                .btn-confirm{background:var(--success-green)}
                .btn-cancel{background:var(--neutral-text-light)}
                table{width:100%;border-collapse:separate;border-spacing:0;margin-top:16px}
                th{background:var(--neutral-hover);padding:16px;text-align:left;font-weight:500;color:var(--neutral-text-light);border-bottom:2px solid var(--neutral-border);position:sticky;top:0}
                td{padding:16px;border-bottom:1px solid var(--neutral-border);transition:background 0.2s}
                tr:hover td{background:var(--neutral-hover)}
                .badge{padding:6px 12px;border-radius:6px;font-size:12px;font-weight:500;display:inline-block;min-width:80px;text-align:center}
                .badge.created{background:#e6f4ea;color:var(--success-green);border:1px solid #c6ecd0}
                .badge.modified{background:#fef7e0;color:#f9ab00;border:1px solid #fde293}
                .badge.deleted{background:#fce8e6;color:var(--warning-red);border:1px solid #f9c9c6}
                .filename{font-weight:500;color:var(--primary-blue)}
                .directory{color:var(--neutral-text-light);font-size:13px;max-width:250px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
                .process{font-family:monospace;font-size:13px;background:var(--neutral-hover);padding:2px 6px;border-radius:4px}
                .user{display:inline-flex;align-items:center;gap:6px;padding:4px 10px;background:#e8f0fe;color:var(--primary-blue);border-radius:12px;font-size:13px}
                .real-time-indicator{display:flex;align-items:center;gap:8px;margin-top:16px;padding:12px;background:#e8f0fe;border-radius:8px;color:var(--primary-blue)}
                .indicator{width:10px;height:10px;background:var(--success-green);border-radius:50%;animation:pulse 2s infinite}
                @keyframes pulse{0%,100%{opacity:1}50%{opacity:0.5}}
                .empty-state{text-align:center;padding:40px;color:var(--neutral-text-light)}
                .empty-state svg{width:64px;height:64px;margin-bottom:16px;opacity:0.5}
                .stat-card{grid-column:span 1}
                .main-card{grid-column:span 4}
                
                /* Custom Modal Styles */
                .modal-overlay {
                    position: fixed;
                    top: 0;
                    left: 0;
                    right: 0;
                    bottom: 0;
                    background: rgba(0, 0, 0, 0.5);
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    z-index: 9999;
                    opacity: 0;
                    visibility: hidden;
                    transition: opacity 0.3s, visibility 0.3s;
                }
                .modal-overlay.active {
                    opacity: 1;
                    visibility: visible;
                }
                .modal {
                    background: white;
                    border-radius: 12px;
                    padding: 32px;
                    max-width: 500px;
                    width: 90%;
                    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
                    transform: translateY(20px);
                    transition: transform 0.3s;
                }
                .modal-overlay.active .modal {
                    transform: translateY(0);
                }
                .modal h3 {
                    margin: 0 0 16px 0;
                    color: var(--neutral-text);
                    font-size: 20px;
                    font-weight: 500;
                }
                .modal p {
                    margin: 0 0 24px 0;
                    color: var(--neutral-text-light);
                    line-height: 1.5;
                }
                .modal-buttons {
                    display: flex;
                    gap: 12px;
                    justify-content: flex-end;
                }
                .modal-icon {
                    width: 48px;
                    height: 48px;
                    background: #fce8e6;
                    border-radius: 50%;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    margin-bottom: 20px;
                    color: var(--warning-red);
                }
                .modal-content {
                    display: flex;
                    gap: 20px;
                    align-items: flex-start;
                }
                .modal-text {
                    flex: 1;
                }
            </style>
        </head>
        <body>
            <!-- Custom Confirmation Modal -->
            <div class="modal-overlay" id="confirmModal">
                <div class="modal">
                    <div class="modal-content">
                        <div class="modal-icon">
                            <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="currentColor">
                                <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z"/>
                            </svg>
                        </div>
                        <div class="modal-text">
                            <h3>Clear All Events</h3>
                            <p>Are you sure you want to clear all logged events? This action cannot be undone and will permanently delete all event history.</p>
                            <div class="modal-buttons">
                                <button class="btn btn-cancel" onclick="hideConfirmModal()">Cancel</button>
                                <button class="btn btn-confirm" onclick="performClear()">Clear All Events</button>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            
            <div class="container">
                <div class="header">
                    <h1>File Access Monitor</h1>
                    <div class="subtitle">Real-time file system activity dashboard</div>
                    <div class="status">Live Monitoring Active</div>
                </div>
                
                <div class="grid">
                    <div class="card stat-card">
                        <h3>Total Events</h3>
                        <div class="stats">
                            <p>All Events: <strong id="total-events">0</strong></p>
                            <p>Last Hour: <strong id="recent-events">0</strong></p>
                            <p>Last Update: <span id="last-update">Just now</span></p>
                        </div>
                    </div>
                    
                    <div class="card stat-card">
                        <h3>Directories</h3>
                        <div style="margin-top:12px">
                            __MONITOR_DIRECTORIES__
                        </div>
                    </div>
                    
                    <div class="card stat-card">
                        <h3>Event Types</h3>
                        <div style="margin-top:12px">
                            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">
                                <span>Created</span>
                                <span class="badge created" id="count-created">0</span>
                            </div>
                            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">
                                <span>Modified</span>
                                <span class="badge modified" id="count-modified">0</span>
                            </div>
                            <div style="display:flex;align-items:center;justify-content:space-between">
                                <span>Deleted</span>
                                <span class="badge deleted" id="count-deleted">0</span>
                            </div>
                        </div>
                    </div>
                    
                    <div class="card stat-card">
                        <h3>Actions</h3>
                        <div style="margin-top:20px">
                            <button class="btn btn-danger" onclick="showConfirmModal()" id="clear-btn">Clear All Events</button>
                        </div>
                        <div class="real-time-indicator">
                            <div class="indicator"></div>
                            <div>Real-time updates active</div>
                        </div>
                    </div>
                </div>
                
                <div class="card main-card">
                    <h3>Recent File Activity</h3>
                    <table>
                        <thead>
                            <tr>
                                <th>Time</th>
                                <th>Event Type</th>
                                <th>File Name</th>
                                <th>Directory</th>
                                <th>Process (PID)</th>
                                <th>User</th>
                            </tr>
                        </thead>
                        <tbody id="events-body">
                            <tr><td colspan="6" class="empty-state">
                                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor">
                                    <path d="M19.5 21a3 3 0 0 0 3-3v-4.5a3 3 0 0 0-3-3h-15a3 3 0 0 0-3 3V18a3 3 0 0 0 3 3h15ZM1.5 10.146V6a3 3 0 0 1 3-3h5.379a2.25 2.25 0 0 1 1.59.659l2.122 2.121c.14.141.331.22.53.22H19.5a3 3 0 0 1 3 3v1.146A4.483 4.483 0 0 0 19.5 9h-15a4.483 4.483 0 0 0-3 1.146Z"/>
                                </svg>
                                <div>Waiting for file activity...</div>
                                <div style="font-size:14px;margin-top:8px">File events will appear here automatically</div>
                            </td></tr>
                        </tbody>
                    </table>
                </div>
            </div>
            
            <script src="https://cdn.socket.io/4.5.4/socket.io.min.js"></script>
            <script>
                const socket = io();
                let eventCounts = {created:0, modified:0, deleted:0};
                let clearButtonLock = false;
                
                socket.on('new_event', function(eventData) {
                    addEventToTable(eventData);
                    updateEventCount(eventData.event_type);
                    updateStats();
                });
                
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
                    
                    if(tbody.children.length > 20) {
                        tbody.removeChild(tbody.lastChild);
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
            </script>
        </body>
        </html>
        '''.replace('__MONITOR_DIRECTORIES__', directory_list_html)
    
    @app.route('/api/stats')
    def stats():
        session = Session()
        try:
            # Count total events and events from the last hour
            total = session.query(FileEvent).count()
            hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
            recent = session.query(FileEvent).filter(FileEvent.timestamp >= hour_ago).count()
            
            # Count events by type
            created = session.query(FileEvent).filter(FileEvent.event_type.like('%Created%')).count()
            modified = session.query(FileEvent).filter(FileEvent.event_type.like('%Modified%')).count()
            deleted = session.query(FileEvent).filter(FileEvent.event_type.like('%Deleted%')).count()
            
            # Return the statistics as JSON
            return jsonify({
                'total_events': total,
                'recent_events': recent,
                'created': created,
                'modified': modified,
                'deleted': deleted
            })
        finally:
            # Close the database session
            session.close()
    
    # API route to get the most recent 20 file events
    @app.route('/api/initial_events')
    def initial_events():
        session = Session()
        try:
            # Fetch the latest 20 events from the database
            events = session.query(FileEvent).order_by(FileEvent.timestamp.desc()).limit(20).all()
            # Format the events as JSON
            return jsonify({'events': [serialize_event(event) for event in events]})
        finally:
            # Close the database session
            session.close()
    
    # API route to clear all file events from the database
    @app.route('/api/clear', methods=['POST'])
    def clear():
        if not request.is_json:
            return jsonify({
                'status': 'error',
                'message': 'Clear requests must use JSON'
            }), 415

        session = Session()
        try:
            # Count the total events
            count = session.query(FileEvent).count()
            if count > 0:
                # Delete all events and commit
                session.query(FileEvent).delete()
                session.commit()
                return jsonify({
                    'status': 'success',
                    'message': f'Cleared {count} events',
                    'cleared': count
                })
            else:
                # No events to clear
                return jsonify({
                    'status': 'info', 
                    'message': 'No events to clear',
                    'cleared': 0
                })
        except Exception as e:
            # Rollback on error and return error response
            session.rollback()
            return jsonify({
                'status': 'error',
                'message': f'Error clearing events: {str(e)}'
            }), 500
        finally:
            # Close the database session
            session.close()

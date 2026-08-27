import os
from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, render_template, request

from models import Session, FileEvent
import config


# Colors cycled through when drawing the monitored-directory legend
DIRECTORY_COLORS = ("var(--primary-blue)", "var(--success-green)", "#f9ab00")

# Blueprint holding the dashboard page and its JSON API
dashboard = Blueprint("dashboard", __name__)


# Convert a FileEvent row into a JSON-serializable dictionary
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


# Build the monitored-directory list with a color for each entry
def _directory_legend():
    return [
        {'path': directory, 'color': DIRECTORY_COLORS[index % len(DIRECTORY_COLORS)]}
        for index, directory in enumerate(config.MONITOR_DIRS)
    ]


# Dashboard page
@dashboard.route('/')
def index():
    return render_template('index.html', directories=_directory_legend())


# Event totals and per-type counts for the stat cards
@dashboard.route('/api/stats')
def stats():
    session = Session()
    try:
        total = session.query(FileEvent).count()
        hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
        recent = session.query(FileEvent).filter(FileEvent.timestamp >= hour_ago).count()

        created = session.query(FileEvent).filter(FileEvent.event_type.like('%Created%')).count()
        modified = session.query(FileEvent).filter(FileEvent.event_type.like('%Modified%')).count()
        deleted = session.query(FileEvent).filter(FileEvent.event_type.like('%Deleted%')).count()

        return jsonify({
            'total_events': total,
            'recent_events': recent,
            'created': created,
            'modified': modified,
            'deleted': deleted
        })
    finally:
        session.close()


# Most recent 20 events used to populate the table on page load
@dashboard.route('/api/initial_events')
def initial_events():
    session = Session()
    try:
        events = session.query(FileEvent).order_by(FileEvent.timestamp.desc()).limit(20).all()
        return jsonify({'events': [serialize_event(event) for event in events]})
    finally:
        session.close()


# Delete every logged event; requires a JSON request as a lightweight CSRF guard
@dashboard.route('/api/clear', methods=['POST'])
def clear():
    if not request.is_json:
        return jsonify({
            'status': 'error',
            'message': 'Clear requests must use JSON'
        }), 415

    session = Session()
    try:
        count = session.query(FileEvent).count()
        if count == 0:
            return jsonify({
                'status': 'info',
                'message': 'No events to clear',
                'cleared': 0
            })

        session.query(FileEvent).delete()
        session.commit()
        return jsonify({
            'status': 'success',
            'message': f'Cleared {count} events',
            'cleared': count
        })
    except Exception as error:
        session.rollback()
        return jsonify({
            'status': 'error',
            'message': f'Error clearing events: {error}'
        }), 500
    finally:
        session.close()

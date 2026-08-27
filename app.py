# Web framework and real-time transport
from flask import Flask
from flask_socketio import SocketIO

# Database model and helpers
from models import init_db, Session, FileEvent

# Dashboard page and API routes
from routes import dashboard

# File monitoring and configuration
import monitor
import config

# Flask application and Socket.IO server
app = Flask(__name__)
socketio = SocketIO(app, async_mode=config.SOCKETIO_ASYNC_MODE)

# Create database tables before any request handler can query them
init_db()

# Attach the dashboard page and API routes to the application
app.register_blueprint(dashboard)


# Start the dashboard and file monitoring
def main():
    print("File Access Logger - Real-Time Dashboard")
    print("========================================")

    # Count events already stored in the database
    session = Session()
    try:
        count = session.query(FileEvent).count()
    finally:
        session.close()

    # Show database path and configured directories
    print(f"Database: {config.DB_PATH}")
    print(f"Existing Events: {count}")
    print("Monitoring Directories:")
    for directory in config.MONITOR_DIRS:
        print(f"  - {directory}")

    # Start monitoring in a background thread
    if monitor.start_monitoring(socketio):
        print("Real-time Monitoring: ACTIVE")
    else:
        print("Monitoring: FAILED")

    # Show the dashboard URL
    print(f"\nDashboard URL: http://{config.HOST}:{config.PORT}")
    print("========================================\n")

    # Run the Flask-SocketIO server
    socketio.run(app, host=config.HOST, port=config.PORT, debug=False, allow_unsafe_werkzeug=True)


if __name__ == '__main__':
    main()

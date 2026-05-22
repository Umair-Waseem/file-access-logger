# Import Flask 
from flask import Flask
from flask_socketio import SocketIO

# Import database 
from models import init_db, Session, FileEvent

# Import the file monitoring module and configuration settings.
import monitor
import config

# Create the Flask application instance.
app = Flask(__name__)

# Initialize Socket.IO with async mode from configuration.
socketio = SocketIO(app, async_mode=config.SOCKETIO_ASYNC_MODE)

# Ensure database tables exist before any request handler can query them.
init_db()

# Import and register all routes for the web application.
from routes import create_routes
create_routes(app)

# Main function to start the dashboard and file monitoring.
def main():
    # Display application banner.
    print("File Access Logger - Real-Time Dashboard")
    print("========================================")
    
    # Count existing events in the database.
    session = Session()
    try:
        count = session.query(FileEvent).count()
    finally:
        session.close()
    
    # Display database path and total number of logged events.
    print(f"Database: {config.DB_PATH}")
    print(f"Existing Events: {count}")
    print("Monitoring Directories:")
    for directory in config.MONITOR_DIRS:
        print(f"  - {directory}")
    
    # Start file monitoring 
    if monitor.start_monitoring(socketio):
        print("Real-time Monitoring: ACTIVE")
    else:
        print("Monitoring: FAILED")
    
    # Show the dashboard URL
    print(f"\nDashboard URL: http://{config.HOST}:{config.PORT}")
    print("========================================\n")
    
    # Run the Flask-SocketIO server with the configured host and port.
    socketio.run(app, host=config.HOST, port=config.PORT, debug=False, allow_unsafe_werkzeug=True)

if __name__ == '__main__':
    main()

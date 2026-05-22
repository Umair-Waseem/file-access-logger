from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime, timezone
from pathlib import Path
import config


Base = declarative_base()

# FileEvent table definition
class FileEvent(Base):
    __tablename__ = 'file_events'
    
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    event_type = Column(String(50))
    file_path = Column(String(500))
    process_name = Column(String(100))
    pid = Column(Integer)
    username = Column(String(50))
    command = Column(Text)

db_path = Path(config.DB_PATH)

# Database engine and session setup.
engine = create_engine(
    f"sqlite:///{db_path.as_posix()}",
    connect_args={"check_same_thread": False}
)
Session = sessionmaker(bind=engine, expire_on_commit=False)

# Create tables if not exist
def init_db():
    db_path.parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)

import os
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, String, Text, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker


CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_PATH = os.path.join(CURRENT_DIR, "tasks.db")
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Task(Base):
    __tablename__ = "tasks"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String, nullable=False)
    description = Column(Text, nullable=False, default="")
    status = Column(String, nullable=False, default="pending", index=True)
    due_date = Column(String, nullable=True, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)


def generate_id() -> str:
    return str(uuid.uuid4())


def init_db() -> None:
    Base.metadata.create_all(bind=engine)

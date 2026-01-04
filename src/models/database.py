from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text, ForeignKey, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime

Base = declarative_base()

class Resume(Base):
    __tablename__ = 'resumes'
    
    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, nullable=False)
    original_path = Column(String, nullable=False)
    parsed_data = Column(JSON, nullable=False)  # Serialized ResumeData
    is_default = Column(Integer, default=0)  # 1 if this is the default resume
    created_at = Column(DateTime, default=datetime.utcnow)
    
    sessions = relationship("Session", back_populates="resume")

class JobDescription(Base):
    __tablename__ = 'job_descriptions'
    
    id = Column(Integer, primary_key=True, index=True)
    source_url = Column(String, nullable=True)
    parsed_data = Column(JSON, nullable=False)  # Serialized JobDescription
    created_at = Column(DateTime, default=datetime.utcnow)
    
    sessions = relationship("Session", back_populates="job_description")

class Session(Base):
    __tablename__ = 'sessions'
    
    id = Column(Integer, primary_key=True, index=True)
    resume_id = Column(Integer, ForeignKey('resumes.id'), nullable=False)
    jd_id = Column(Integer, ForeignKey('job_descriptions.id'), nullable=False)
    current_score = Column(Float, default=0.0)
    current_semantic_fit = Column(String, default='Low')
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    resume = relationship("Resume", back_populates="sessions")
    job_description = relationship("JobDescription", back_populates="sessions")
    suggestions = relationship("Suggestion", back_populates="session")

class Suggestion(Base):
    __tablename__ = 'suggestions'
    
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey('sessions.id'), nullable=False)
    section_type = Column(String, nullable=False)  # 'bullet', 'skill', 'summary'
    section_id = Column(String, nullable=True)
    original_text = Column(Text, nullable=False)
    suggested_text = Column(Text, nullable=False)
    reason = Column(Text, nullable=False)
    expected_score_delta = Column(Float, default=0.0)
    jd_mapping = Column(Text, nullable=True)
    status = Column(String, default='pending')  # 'pending', 'accepted', 'rejected', 'edited'
    edited_text = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    session = relationship("Session", back_populates="suggestions")

class Export(Base):
    __tablename__ = 'exports'
    
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey('sessions.id'), nullable=False)
    filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    fit_summary = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    session = relationship("Session")

# Database setup
def get_database_url():
    return "sqlite:///./database.db"

def create_tables():
    engine = create_engine(get_database_url(), connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return engine

def get_session_local(engine):
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return SessionLocal


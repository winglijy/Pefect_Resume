from pydantic import BaseModel, EmailStr
from typing import Optional, List, Dict, Any
from datetime import datetime

# Resume Models
class PersonalInfo(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    linkedin: Optional[str] = None

class BulletPoint(BaseModel):
    text: str
    formatting: Optional[Dict[str, Any]] = None  # Font, size, style, etc.

class ExperienceEntry(BaseModel):
    company: str
    title: str
    location: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    bullets: List[BulletPoint]

class EducationEntry(BaseModel):
    institution: str
    degree: str
    field: Optional[str] = None
    location: Optional[str] = None
    graduation_date: Optional[str] = None

class ResumeData(BaseModel):
    personal_info: PersonalInfo
    summary: Optional[str] = None
    experience: List[ExperienceEntry] = []
    education: List[EducationEntry] = []
    skills: List[str] = []
    formatting_map: Optional[Dict[str, Any]] = None  # For DOCX regeneration

# Job Description Models - Match-Focused Framework
class JobDescription(BaseModel):
    # Role Summary
    role_title: str
    role_summary: Optional[str] = None  # Brief 1-2 sentence summary of the role
    company: Optional[str] = None
    location: Optional[str] = None
    experience_level: Optional[str] = None  # e.g., "5+ years", "Senior", "Entry-level"
    team_scope: Optional[str] = None  # e.g., "Reports to VP", "Manages 5 engineers"
    industry_domain: Optional[str] = None  # e.g., "B2B SaaS", "Healthcare", "Fintech"
    
    # Requirements (prioritized)
    must_have_requirements: List[str] = []  # Deal breakers - must address
    nice_to_have_requirements: List[str] = []  # Bonus points
    
    # Skills (categorized)
    technical_skills: List[str] = []  # Tools, technologies, languages
    soft_skills: List[str] = []  # Leadership, communication, collaboration
    
    # Keywords for ATS optimization
    keywords_to_include: List[str] = []  # Important terms to mirror in resume
    
    # Legacy fields (for backward compatibility)
    responsibilities: List[str] = []
    requirements: List[str] = []
    preferred_qualifications: List[str] = []
    required_skills: List[str] = []
    preferred_skills: List[str] = []
    keywords: List[str] = []
    raw_text: Optional[str] = None

# Scoring Models
class ScoreBreakdown(BaseModel):
    keyword_score: float
    skill_score: float
    completeness_score: float
    matched_keywords: List[str] = []
    missing_keywords: List[str] = []
    matched_skills: List[str] = []
    missing_skills: List[str] = []
    section_completeness: Dict[str, bool] = {}

class ScoreResponse(BaseModel):
    ats_score: float  # 0-100
    semantic_fit: str  # Low/Medium/High
    semantic_score: float  # 0-1
    breakdown: ScoreBreakdown

# Suggestion Models
class Suggestion(BaseModel):
    id: str
    section_type: str  # 'bullet', 'skill', 'summary', 'keyword'
    section_id: Optional[str] = None  # For bullets: which experience entry
    original_text: str
    suggested_text: str
    reason: str
    expected_score_delta: float
    jd_mapping: Optional[str] = None  # Which JD requirement this addresses
    category: Optional[str] = None  # 'summary', 'experience', 'skills', 'keywords'
    priority: Optional[str] = None  # 'high', 'medium', 'low'

class SuggestionsResponse(BaseModel):
    suggestions: List[Suggestion]
    session_id: Optional[str] = None  # For export functionality
    summary: Optional[str] = None  # AI-generated overview of improvements
    
class RefineSuggestionRequest(BaseModel):
    feedback: str  # User's feedback on the suggestion

# API Request/Response Models
class UploadResumeResponse(BaseModel):
    resume_id: str
    filename: str
    parsed_data: ResumeData

class ParseJDResponse(BaseModel):
    jd_id: str
    parsed_data: JobDescription

class ExportResponse(BaseModel):
    export_id: str
    filename: str
    fit_summary: Optional[str] = None
    top_strengths: List[str] = []
    key_gaps: List[str] = []


from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, Request
from pydantic import BaseModel
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from sqlalchemy.orm import Session
from typing import Optional, Dict, Any
import os
import uuid
from pathlib import Path
import json

from src.models.database import create_tables, get_session_local, Resume as DBResume, JobDescription as DBJobDescription, Session, Suggestion, Export
from src.models.schemas import (
    ResumeData, JobDescription, UploadResumeResponse, ParseJDResponse,
    ScoreResponse, SuggestionsResponse, ExportResponse, Suggestion as SuggestionSchema
)
from src.parsers.resume_parser import ResumeParser
from src.parsers.jd_parser import JobDescriptionParser
from src.scoring.ats_scorer import ATSScorer
from src.scoring.semantic_matcher import SemanticMatcher
from src.suggestions.suggestion_engine import SuggestionEngine
from src.suggestions.simple_suggestion_engine import SimpleSuggestionEngine
from src.regeneration.resume_builder import ResumeBuilder

# Initialize FastAPI app
app = FastAPI(title="Perfect Resume API", version="1.0.0")

# Global exception handler to ensure all errors return JSON
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Ensure all exceptions return JSON responses."""
    import traceback
    error_trace = traceback.format_exc()
    print(f"\n{'='*60}")
    print(f"UNHANDLED EXCEPTION: {exc}")
    print(f"Traceback:\n{error_trace}")
    print(f"{'='*60}\n")
    return JSONResponse(
        status_code=500,
        content={
            "detail": f"Internal server error: {str(exc)}",
            "error": str(exc)
        }
    )

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Ensure HTTPExceptions return JSON."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "error": exc.detail}
    )

# CORS middleware - must be added before routes
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],  # Explicitly include OPTIONS for preflight
    allow_headers=["*"],
    expose_headers=["*"],
)

# Create directories
UPLOAD_DIR = Path("uploads")
EXPORT_DIR = Path("exports")
UPLOAD_DIR.mkdir(exist_ok=True)
EXPORT_DIR.mkdir(exist_ok=True)

# Initialize database
engine = create_tables()
SessionLocal = get_session_local(engine)

# Run migration to add is_default column if needed
try:
    from sqlalchemy import text
    with engine.connect() as conn:
        result = conn.execute(text("PRAGMA table_info(resumes)"))
        columns = [row[1] for row in result]
        if 'is_default' not in columns:
            print("Migrating database: adding is_default column...")
            conn.execute(text("ALTER TABLE resumes ADD COLUMN is_default INTEGER DEFAULT 0"))
            conn.commit()
            print("✓ Migration complete!")
except Exception as e:
    print(f"Note: Database migration check: {e}")

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Initialize parsers and scorers
resume_parser = ResumeParser()
jd_parser = JobDescriptionParser()
ats_scorer = ATSScorer()
semantic_matcher = SemanticMatcher()
suggestion_engine = SuggestionEngine()
simple_suggestion_engine = SimpleSuggestionEngine()  # Use simple engine for reliability
resume_builder = ResumeBuilder()

@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the Perfect Resume frontend."""
    with open("templates/index.html", "r") as f:
        return HTMLResponse(content=f.read())

# Phase 1: Parsing Endpoints
@app.post("/api/upload-resume", response_model=UploadResumeResponse)
async def upload_resume(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Upload and parse a resume file."""
    # Validate file type
    if not file.filename.endswith(('.pdf', '.docx', '.doc')):
        raise HTTPException(status_code=400, detail="Unsupported file format. Please upload PDF or DOCX.")
    
    # Save file
    file_id = str(uuid.uuid4())
    file_extension = Path(file.filename).suffix
    file_path = UPLOAD_DIR / f"{file_id}{file_extension}"
    
    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)
    
    try:
        # Parse resume
        print(f"\n=== Parsing Resume: {file.filename} ===")
        # Parse resume
        print(f"Attempting to parse file: {file_path}")
        print(f"File exists: {Path(file_path).exists()}")
        print(f"File extension: {Path(file_path).suffix}")
        
        try:
            result = resume_parser.parse(str(file_path))
            print(f"Parse successful! Result type: {type(result)}")
            
            # Validate result
            if not isinstance(result, tuple):
                raise ValueError(f"Parser returned {type(result)}, expected tuple")
            if len(result) != 2:
                raise ValueError(f"Parser returned {len(result)} values, expected 2")
            
            resume_data, formatting_map = result
            print(f"Successfully unpacked: resume_data type={type(resume_data)}, formatting_map type={type(formatting_map)}")
            
        except ValueError as ve:
            # Re-raise ValueError as-is (these are user-friendly errors)
            print(f"Resume parse ValueError: {ve}")
            raise
        except Exception as parse_error:
            import traceback
            error_trace = traceback.format_exc()
            print(f"\n{'='*60}")
            print(f"RESUME PARSE ERROR (Full Traceback):")
            print(f"{error_trace}")
            print(f"{'='*60}\n")
            raise ValueError(f"Error parsing resume: {str(parse_error)}")
        
        # Log parsing results
        print(f"Name: {resume_data.personal_info.name}")
        print(f"Email: {resume_data.personal_info.email}")
        print(f"Experience entries: {len(resume_data.experience)}")
        print(f"Education entries: {len(resume_data.education)}")
        print(f"Skills: {len(resume_data.skills)}")
        print("=" * 40 + "\n")
        
        # Ensure is_default column exists (migrate if needed)
        try:
            from sqlalchemy import text, inspect
            inspector = inspect(engine)
            columns = [col['name'] for col in inspector.get_columns('resumes')]
            if 'is_default' not in columns:
                print("Migrating database: adding is_default column...")
                db.execute(text("ALTER TABLE resumes ADD COLUMN is_default INTEGER DEFAULT 0"))
                db.commit()
                print("✓ Migration complete!")
        except Exception as migration_error:
            print(f"Migration check error (may already exist): {migration_error}")
            db.rollback()
        
        # Mark all other resumes as not default
        try:
            from sqlalchemy import text
            db.execute(text("UPDATE resumes SET is_default = 0"))
            db.commit()
        except Exception as e:
            print(f"Note: Could not update is_default: {e}")
            db.rollback()
        
        # Store in database as default resume
        db_resume = DBResume(
            filename=file.filename,
            original_path=str(file_path),
            parsed_data=resume_data.model_dump(),
            is_default=1  # Set as default
        )
        db.add(db_resume)
        db.commit()
        db.refresh(db_resume)
        
        return UploadResumeResponse(
            resume_id=str(db_resume.id),
            filename=file.filename,
            parsed_data=resume_data
        )
    except ValueError as e:
        # Clean up file on error
        if file_path.exists():
            file_path.unlink()
        error_msg = str(e)
        print(f"Resume parse ValueError: {error_msg}")
        raise HTTPException(status_code=400, detail=f"Invalid resume format: {error_msg}")
    except Exception as e:
        # Clean up file on error
        if file_path.exists():
            file_path.unlink()
        import traceback
        error_trace = traceback.format_exc()
        error_msg = str(e)
        print(f"\n{'='*50}")
        print(f"RESUME PARSE ERROR:")
        print(f"Error: {error_msg}")
        print(f"Traceback:\n{error_trace}")
        print(f"{'='*50}\n")
        raise HTTPException(status_code=500, detail=f"Failed to parse resume: {error_msg}")

class JDParseRequest(BaseModel):
    source: str

@app.post("/api/parse-jd", response_model=ParseJDResponse)
async def parse_jd(request: JDParseRequest, db: Session = Depends(get_db)):
    """Parse a job description from URL or text. 
    
    Note: For AI suggestions, we primarily use the raw text. 
    Parsing is mainly for display purposes and basic extraction.
    """
    try:
        source = request.source
        if not source:
            raise HTTPException(status_code=400, detail="Source is required")
        
        print(f"\n=== Processing Job Description ===")
        print(f"Source length: {len(source)} characters")
        print(f"Is URL: {source.startswith('http')}")
        
        # Parse JD (for display/extraction, but we'll use raw text for AI)
        jd_data = jd_parser.parse(source)
        
        # IMPORTANT: Preserve raw text for AI suggestions (more accurate than parsed fields)
        # The LLM will use raw_text directly, parsing is mainly for display
        if not jd_data.raw_text or len(jd_data.raw_text) < len(source) * 0.8:
            jd_data.raw_text = source  # Use original source as raw text
        
        # Log what was extracted (for display purposes)
        print(f"Extracted Role Title: {jd_data.role_title}")
        print(f"Extracted Company: {jd_data.company}")
        print(f"Responsibilities: {len(jd_data.responsibilities)} items")
        print(f"Requirements: {len(jd_data.requirements)} items")
        print(f"Preferred Qualifications: {len(jd_data.preferred_qualifications)} items")
        print(f"Required Skills: {len(jd_data.required_skills)} skills")
        print(f"Preferred Skills: {len(jd_data.preferred_skills)} skills")
        print(f"Keywords: {len(jd_data.keywords)} keywords")
        print(f"Raw text length: {len(jd_data.raw_text)} characters (used for AI suggestions)")
        
        # Ensure we have at least a role title
        if not jd_data.role_title or jd_data.role_title == "Job Position":
            # Try to extract from first line of raw text
            if jd_data.raw_text:
                first_line = jd_data.raw_text.split('\n')[0].strip()
                if first_line and len(first_line) < 100:
                    jd_data.role_title = first_line
                else:
                    jd_data.role_title = "Job Description"  # Default fallback
            else:
                jd_data.role_title = "Job Description"  # Default fallback
        
        # If very little was extracted, try a more aggressive extraction
        if (len(jd_data.responsibilities) < 2 and len(jd_data.requirements) < 2 and 
            len(jd_data.required_skills) < 2):
            print("Warning: Very little extracted. Trying aggressive fallback extraction...")
            import re
            
            # Extract all bullet points (multiple formats)
            bullets = []
            patterns = [
                r'[•\-\*●▪▫]\s*([^\n•\-\*●▪▫]{20,})',  # Standard bullets
                r'^\s*[-]\s+([^\n]{20,})',  # Dash bullets
                r'^\s*\d+[\.\)]\s+([^\n]{20,})',  # Numbered lists
            ]
            for pattern in patterns:
                found = re.findall(pattern, jd_data.raw_text, re.MULTILINE)
                bullets.extend([b.strip() for b in found if len(b.strip()) > 20])
            
            # Remove duplicates
            bullets = list(dict.fromkeys(bullets))
            
            # Categorize bullets - remove duplicates first
            seen_bullets = set()
            unique_bullets = []
            for bullet in bullets:
                bullet_normalized = bullet.lower().strip()
                # Skip if very similar to something we've seen
                is_duplicate = False
                for seen in seen_bullets:
                    # Check if one contains the other (80% overlap)
                    shorter = min(len(bullet_normalized), len(seen))
                    longer = max(len(bullet_normalized), len(seen))
                    if shorter > 0 and longer > 0:
                        if bullet_normalized in seen or seen in bullet_normalized:
                            if shorter / longer > 0.8:
                                is_duplicate = True
                                break
                if not is_duplicate and len(bullet_normalized) > 30:
                    seen_bullets.add(bullet_normalized)
                    unique_bullets.append(bullet)
            
            # Now categorize unique bullets
            for bullet in unique_bullets[:20]:
                bullet_lower = bullet.lower()
                # Responsibilities (action-oriented)
                if any(verb in bullet_lower for verb in ['lead', 'develop', 'manage', 'create', 'design', 'build', 'drive', 'collaborate', 'work', 'implement', 'deliver', 'own', 'execute']):
                    if bullet not in jd_data.responsibilities:
                        jd_data.responsibilities.append(bullet)
                # Requirements (qualification-oriented)
                elif any(kw in bullet_lower for kw in ['experience', 'years', 'degree', 'bachelor', 'master', 'skill', 'knowledge', 'ability', 'proven', 'demonstrated', 'required', 'must']):
                    if bullet not in jd_data.requirements:
                        jd_data.requirements.append(bullet)
                # If not categorized yet, add to requirements as fallback
                elif len(bullet) > 30:
                    if bullet not in jd_data.requirements:
                        jd_data.requirements.append(bullet)
            
            # Also extract skills from the raw text more aggressively
            if len(jd_data.required_skills) < 3:
                # Look for common skill patterns in the text
                skill_patterns = [
                    (r'\b(?:AI|artificial intelligence|machine learning|ML|deep learning)\b', 'AI'),
                    (r'\b(?:python|java|javascript|typescript|react|angular|vue)\b', None),  # Use match as-is
                    (r'\b(?:aws|azure|gcp|docker|kubernetes|k8s)\b', None),
                    (r'\b(?:sql|postgresql|mysql|mongodb|redis)\b', None),
                    (r'\b(?:agile|scrum|kanban|devops)\b', None),
                ]
                found_skills = []
                for pattern, default_name in skill_patterns:
                    matches = re.findall(pattern, jd_data.raw_text, re.IGNORECASE)
                    for m in matches:
                        if default_name:
                            skill_name = default_name
                        else:
                            # Normalize the match
                            m_lower = m.lower()
                            if m_lower == 'ai' or 'artificial intelligence' in m_lower:
                                skill_name = 'AI'
                            elif m_lower == 'ml' or 'machine learning' in m_lower:
                                skill_name = 'Machine Learning'
                            else:
                                skill_name = m.title() if m.islower() else m
                        if skill_name not in found_skills:
                            found_skills.append(skill_name)
                
                # Add unique skills
                for skill in found_skills:
                    if skill not in jd_data.required_skills:
                        jd_data.required_skills.append(skill)
            
            print(f"Fallback extracted: {len(jd_data.responsibilities)} responsibilities, {len(jd_data.requirements)} requirements, {len(jd_data.required_skills)} skills")
        
        print("=" * 40 + "\n")
        
        # Store in database
        db_jd = DBJobDescription(
            source_url=source if source.startswith('http') else None,
            parsed_data=jd_data.model_dump()
        )
        db.add(db_jd)
        db.commit()
        db.refresh(db_jd)
        
        # Log parsing results for debugging
        print(f"\n=== JD Parsing Results ===")
        print(f"Role Title: {jd_data.role_title}")
        print(f"Company: {jd_data.company}")
        print(f"Responsibilities: {len(jd_data.responsibilities)} items")
        print(f"Requirements: {len(jd_data.requirements)} items")
        print(f"Required Skills: {len(jd_data.required_skills)} skills")
        print(f"Preferred Skills: {len(jd_data.preferred_skills)} skills")
        print(f"Keywords: {len(jd_data.keywords)} keywords")
        print("=" * 30 + "\n")
        
        return ParseJDResponse(
            jd_id=str(db_jd.id),
            parsed_data=jd_data
        )
    except ValueError as e:
        # User-friendly error messages
        error_msg = str(e)
        print(f"JD Parse ValueError: {error_msg}")
        raise HTTPException(status_code=400, detail=error_msg)
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        error_msg = str(e)
        print(f"\n{'='*50}")
        print(f"JD PARSE ERROR:")
        print(f"Error: {error_msg}")
        print(f"Traceback:\n{error_trace}")
        print(f"{'='*50}\n")
        raise HTTPException(status_code=500, detail=f"Failed to parse job description: {error_msg}")

@app.get("/api/resume/default")
async def get_default_resume(db: Session = Depends(get_db)):
    """Get the default resume."""
    db_resume = db.query(DBResume).filter(DBResume.is_default == 1).first()
    if not db_resume:
        raise HTTPException(status_code=404, detail="No default resume found. Please upload a resume first.")
    
    resume_data = ResumeData(**db_resume.parsed_data)
    return {
        "resume_id": str(db_resume.id),
        "filename": db_resume.filename,
        "parsed_data": resume_data
    }

@app.delete("/api/resume/default")
async def delete_default_resume(db: Session = Depends(get_db)):
    """Delete the default resume so user can upload a new one."""
    db_resume = db.query(DBResume).filter(DBResume.is_default == 1).first()
    if db_resume:
        db.delete(db_resume)
        db.commit()
        print("=" * 50)
        print("DELETED default resume from database")
        print("=" * 50)
    return {"message": "Default resume deleted"}

@app.get("/api/resume/{resume_id}")
async def get_resume(resume_id: int, db: Session = Depends(get_db)):
    """Get parsed resume data."""
    db_resume = db.query(DBResume).filter(DBResume.id == resume_id).first()
    if not db_resume:
        raise HTTPException(status_code=404, detail="Resume not found")
    
    resume_data = ResumeData(**db_resume.parsed_data)
    return {
        "resume_id": str(db_resume.id),
        "filename": db_resume.filename,
        "parsed_data": resume_data
    }

# Phase 2: Overall Fitting Analysis
@app.post("/api/fitting")
async def get_fitting(resume_id: Optional[int] = None, jd_id: int = None, db: Session = Depends(get_db)):
    """Get overall fitting analysis - replaces scoring with user-friendly summary."""
    # If no resume_id provided, use default resume
    if resume_id is None:
        db_resume = db.query(DBResume).filter(DBResume.is_default == 1).first()
        if not db_resume:
            raise HTTPException(status_code=404, detail="No default resume found. Please upload a resume first.")
        resume_id = db_resume.id
    else:
        db_resume = db.query(DBResume).filter(DBResume.id == resume_id).first()
    
    if not db_resume:
        raise HTTPException(status_code=404, detail="Resume not found")
    
    if jd_id is None:
        raise HTTPException(status_code=400, detail="Job description ID is required")
    
    db_jd = db.query(DBJobDescription).filter(DBJobDescription.id == jd_id).first()
    if not db_jd:
        raise HTTPException(status_code=404, detail="Job description not found")
    
    # Parse data
    resume_data = ResumeData(**db_resume.parsed_data)
    jd_data = JobDescription(**db_jd.parsed_data)
    
    # Calculate scores (for internal use)
    breakdown = ats_scorer.score(resume_data, jd_data)
    ats_score = ats_scorer.calculate_ats_score(breakdown)
    semantic_fit, semantic_score, section_scores = semantic_matcher.calculate_semantic_fit(resume_data, jd_data)
    
    # Generate AI-powered fitting summary
    fit_summary_data = suggestion_engine.generate_fit_summary(
        resume_data,
        jd_data,
        ats_score,
        semantic_fit
    )
    
    # Create or update session
    session = db.query(Session).filter(
        Session.resume_id == resume_id,
        Session.jd_id == jd_id
    ).first()
    
    if not session:
        session = Session(
            resume_id=resume_id,
            jd_id=jd_id,
            current_score=ats_score,
            current_semantic_fit=semantic_fit
        )
        db.add(session)
    else:
        session.current_score = ats_score
        session.current_semantic_fit = semantic_fit
    
    db.commit()
    db.refresh(session)
    
    return {
        "session_id": session.id,
        "role_title": jd_data.role_title,
        "company": jd_data.company,
        "overall_fit": semantic_fit,
        "fit_score": round(semantic_score * 100, 1),
        "ats_score": round(ats_score, 1),
        "summary": fit_summary_data.get('summary', ''),
        "top_strengths": fit_summary_data.get('top_strengths', []),
        "key_gaps": fit_summary_data.get('key_gaps', []),
        "overlaps": fit_summary_data.get('overlaps', []),
        "recommendations": fit_summary_data.get('recommendations', []),
        "matched_skills": breakdown.matched_skills[:10],
        "missing_skills": breakdown.missing_skills[:10],
        "matched_keywords": breakdown.matched_keywords[:15],
        "missing_keywords": breakdown.missing_keywords[:15]
    }

# Keep old scoring endpoint for backward compatibility (hidden from UI)
@app.post("/api/score", response_model=ScoreResponse)
async def score_resume(resume_id: int, jd_id: int, db: Session = Depends(get_db)):
    """Calculate scores for resume + JD pair. Returns session_id for tracking."""
    """Calculate scores for resume + JD pair."""
    # Get resume and JD from database
    db_resume = db.query(DBResume).filter(DBResume.id == resume_id).first()
    db_jd = db.query(DBJobDescription).filter(DBJobDescription.id == jd_id).first()
    
    if not db_resume:
        raise HTTPException(status_code=404, detail="Resume not found")
    if not db_jd:
        raise HTTPException(status_code=404, detail="Job description not found")
    
    # Parse data
    resume_data = ResumeData(**db_resume.parsed_data)
    jd_data = JobDescription(**db_jd.parsed_data)
    
    # Calculate ATS score
    breakdown = ats_scorer.score(resume_data, jd_data)
    ats_score = ats_scorer.calculate_ats_score(breakdown)
    
    # Calculate semantic fit
    semantic_fit, semantic_score, section_scores = semantic_matcher.calculate_semantic_fit(
        resume_data, jd_data
    )
    
    # Create or update session
    session = db.query(Session).filter(
        Session.resume_id == resume_id,
        Session.jd_id == jd_id
    ).first()
    
    if not session:
        session = Session(
            resume_id=resume_id,
            jd_id=jd_id,
            current_score=ats_score,
            current_semantic_fit=semantic_fit
        )
        db.add(session)
    else:
        session.current_score = ats_score
        session.current_semantic_fit = semantic_fit
    
    db.commit()
    db.refresh(session)
    
    response = ScoreResponse(
        ats_score=ats_score,
        semantic_fit=semantic_fit,
        semantic_score=semantic_score,
        breakdown=breakdown
    )
    
    # Add session_id to response (not in model, but needed by frontend)
    response_dict = response.model_dump()
    response_dict['session_id'] = session.id
    
    return response_dict

# Phase 3: Suggestion Endpoints
@app.post("/api/suggestions", response_model=SuggestionsResponse)
async def get_suggestions(resume_id: Optional[int] = None, jd_id: int = None, max_suggestions: int = 10, db: Session = Depends(get_db)):
    """Generate suggestions for resume + JD."""
    # If no resume_id provided, use default resume
    if resume_id is None:
        db_resume = db.query(DBResume).filter(DBResume.is_default == 1).first()
        if not db_resume:
            raise HTTPException(status_code=404, detail="No default resume found. Please upload a resume first.")
        resume_id = db_resume.id
    else:
        db_resume = db.query(DBResume).filter(DBResume.id == resume_id).first()
    
    if not db_resume:
        raise HTTPException(status_code=404, detail="Resume not found")
    
    if jd_id is None:
        raise HTTPException(status_code=400, detail="Job description ID is required")
    
    db_jd = db.query(DBJobDescription).filter(DBJobDescription.id == jd_id).first()
    if not db_jd:
        raise HTTPException(status_code=404, detail="Job description not found")
    
    # Parse data
    resume_data = ResumeData(**db_resume.parsed_data)
    jd_data = JobDescription(**db_jd.parsed_data)
    
    # Get or create session
    session = db.query(Session).filter(
        Session.resume_id == resume_id,
        Session.jd_id == jd_id
    ).first()
    
    if not session:
        # Calculate initial score first
        breakdown = ats_scorer.score(resume_data, jd_data)
        ats_score = ats_scorer.calculate_ats_score(breakdown)
        semantic_fit, _, _ = semantic_matcher.calculate_semantic_fit(resume_data, jd_data)
        
        session = Session(
            resume_id=resume_id,
            jd_id=jd_id,
            current_score=ats_score,
            current_semantic_fit=semantic_fit
        )
        db.add(session)
        db.commit()
        db.refresh(session)
    
    # Generate suggestions - enhanced approach with priority and grouping
    print(f"\n=== Generating Suggestions ===")
    print(f"Resume: {db_resume.filename}")
    print(f"JD: {jd_data.role_title} ({jd_data.company or 'N/A'})")
    print(f"Max suggestions: {max_suggestions}")
    print(f"JD text length: {len(jd_data.raw_text) if jd_data.raw_text else 0} chars")
    
    ai_summary = None
    try:
        # Use enhanced suggestion engine
        result = simple_suggestion_engine.generate_suggestions(
            resume_data, jd_data, max_suggestions=max_suggestions
        )
        
        # Handle both old format (list) and new format (dict with summary)
        if isinstance(result, dict):
            suggestions = result.get('suggestions', [])
            ai_summary = result.get('summary')
        else:
            suggestions = result
        
        if not suggestions:
            print("⚠ No suggestions generated")
            print("  This could mean:")
            print("  - API call succeeded but no valid suggestions returned")
            print("  - All suggestions were filtered out (too similar, etc.)")
            print("  - API returned empty response")
            # Return empty list instead of error - frontend will handle it gracefully
            return SuggestionsResponse(suggestions=[], session_id=str(session.id), summary=ai_summary)
        
        print(f"✓ Generated {len(suggestions)} suggestions")
        if ai_summary:
            print(f"  Summary: {ai_summary[:100]}...")
        for i, sug in enumerate(suggestions[:5], 1):
            priority = getattr(sug, 'priority', 'medium')
            category = getattr(sug, 'category', 'experience')
            print(f"  {i}. [{priority.upper()}] {category}: {sug.original_text[:40]}...")
        print("=" * 40 + "\n")
    except HTTPException:
        raise
    except ValueError as ve:
        # API-related errors
        error_msg = str(ve)
        print(f"✗ API Error: {error_msg}")
        raise HTTPException(
            status_code=500,
            detail=f"API error: {error_msg}. Please check your AI_BUILDER_TOKEN in .env file."
        )
    except Exception as e:
        print(f"✗ Error generating suggestions: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate suggestions: {str(e)}"
        )
    
    # Store suggestions in database
    db_suggestions = []
    for suggestion in suggestions:
        db_suggestion = Suggestion(
            session_id=session.id,
            section_type=suggestion.section_type,
            section_id=suggestion.section_id,
            original_text=suggestion.original_text,
            suggested_text=suggestion.suggested_text,
            reason=suggestion.reason,
            expected_score_delta=suggestion.expected_score_delta,
            jd_mapping=suggestion.jd_mapping,
            status='pending'
        )
        db.add(db_suggestion)
        # Store category and priority as extra info
        db_suggestion._category = getattr(suggestion, 'category', 'experience')
        db_suggestion._priority = getattr(suggestion, 'priority', 'medium')
        db_suggestions.append(db_suggestion)
    
    db.commit()
    
    # Convert database models to Pydantic schemas
    suggestion_schemas = [
        SuggestionSchema(
            id=str(s.id),
            section_type=s.section_type,
            section_id=s.section_id or '',
            original_text=s.original_text or '',
            suggested_text=s.suggested_text or '',
            reason=s.reason or '',
            expected_score_delta=float(s.expected_score_delta) if s.expected_score_delta else 0.0,
            jd_mapping=s.jd_mapping or '',
            category=getattr(s, '_category', 'experience'),
            priority=getattr(s, '_priority', 'medium')
        )
        for s in db_suggestions
    ]
    
    return SuggestionsResponse(suggestions=suggestion_schemas, session_id=str(session.id), summary=ai_summary)

# Phase 4: Control Loop Endpoints
@app.post("/api/suggestions/{suggestion_id}/accept")
async def accept_suggestion(suggestion_id: int, db: Session = Depends(get_db)):
    """Accept a suggestion and update resume."""
    db_suggestion = db.query(Suggestion).filter(Suggestion.id == suggestion_id).first()
    if not db_suggestion:
        raise HTTPException(status_code=404, detail="Suggestion not found")
    
    if db_suggestion.status != 'pending':
        raise HTTPException(status_code=400, detail="Suggestion already processed")
    
    # Get session and resume
    session = db_suggestion.session
    db_resume = db.query(DBResume).filter(DBResume.id == session.resume_id).first()
    resume_data = ResumeData(**db_resume.parsed_data)
    
    # Apply suggestion to resume data
    apply_suggestion_to_resume(resume_data, db_suggestion)
    
    # Update resume in database
    db_resume.parsed_data = resume_data.model_dump()
    
    # Mark suggestion as accepted
    db_suggestion.status = 'accepted'
    
    # Recalculate score
    db_jd = db.query(DBJobDescription).filter(DBJobDescription.id == session.jd_id).first()
    jd_data = JobDescription(**db_jd.parsed_data)
    
    breakdown = ats_scorer.score(resume_data, jd_data)
    new_score = ats_scorer.calculate_ats_score(breakdown)
    semantic_fit, semantic_score, _ = semantic_matcher.calculate_semantic_fit(resume_data, jd_data)
    
    session.current_score = new_score
    session.current_semantic_fit = semantic_fit
    
    db.commit()
    
    return {
        "message": "Suggestion accepted",
        "new_score": new_score,
        "semantic_fit": semantic_fit
    }

@app.post("/api/suggestions/{suggestion_id}/reject")
async def reject_suggestion(suggestion_id: int, db: Session = Depends(get_db)):
    """Reject a suggestion."""
    db_suggestion = db.query(Suggestion).filter(Suggestion.id == suggestion_id).first()
    if not db_suggestion:
        raise HTTPException(status_code=404, detail="Suggestion not found")
    
    db_suggestion.status = 'rejected'
    db.commit()
    
    return {"message": "Suggestion rejected"}

@app.post("/api/suggestions/{suggestion_id}/refine")
async def refine_suggestion(suggestion_id: int, feedback: str, db: Session = Depends(get_db)):
    """Refine a suggestion based on user feedback."""
    from src.models.schemas import Suggestion as SuggestionSchema
    
    db_suggestion = db.query(Suggestion).filter(Suggestion.id == suggestion_id).first()
    if not db_suggestion:
        raise HTTPException(status_code=404, detail="Suggestion not found")
    
    # Get session to access resume and JD
    session = db_suggestion.session
    db_resume = db.query(DBResume).filter(DBResume.id == session.resume_id).first()
    db_jd = db.query(DBJobDescription).filter(DBJobDescription.id == session.jd_id).first()
    
    resume_data = ResumeData(**db_resume.parsed_data)
    jd_data = JobDescription(**db_jd.parsed_data)
    
    # Create a suggestion object from DB data
    original_suggestion = SuggestionSchema(
        id=str(db_suggestion.id),
        section_type=db_suggestion.section_type,
        section_id=db_suggestion.section_id or '',
        original_text=db_suggestion.original_text or '',
        suggested_text=db_suggestion.suggested_text or '',
        reason=db_suggestion.reason or '',
        expected_score_delta=float(db_suggestion.expected_score_delta) if db_suggestion.expected_score_delta else 0.0,
        jd_mapping=db_suggestion.jd_mapping or ''
    )
    
    # Refine the suggestion
    refined = simple_suggestion_engine.refine_suggestion(
        original_suggestion, feedback, resume_data, jd_data
    )
    
    if not refined:
        raise HTTPException(status_code=500, detail="Failed to refine suggestion")
    
    # Update the database suggestion
    db_suggestion.suggested_text = refined.suggested_text
    db_suggestion.reason = refined.reason
    db.commit()
    
    return {
        "id": str(db_suggestion.id),
        "suggested_text": refined.suggested_text,
        "reason": refined.reason,
        "message": "Suggestion refined based on your feedback"
    }

@app.post("/api/suggestions/{suggestion_id}/edit")
async def edit_suggestion(suggestion_id: int, edited_text: str, db: Session = Depends(get_db)):
    """Accept a suggestion with custom edits."""
    db_suggestion = db.query(Suggestion).filter(Suggestion.id == suggestion_id).first()
    if not db_suggestion:
        raise HTTPException(status_code=404, detail="Suggestion not found")
    
    if db_suggestion.status != 'pending':
        raise HTTPException(status_code=400, detail="Suggestion already processed")
    
    # Get session and resume
    session = db_suggestion.session
    db_resume = db.query(DBResume).filter(DBResume.id == session.resume_id).first()
    resume_data = ResumeData(**db_resume.parsed_data)
    
    # Apply edited suggestion
    db_suggestion.suggested_text = edited_text
    db_suggestion.status = 'edited'
    db_suggestion.edited_text = edited_text
    
    # Apply to resume
    apply_suggestion_to_resume(resume_data, db_suggestion, edited_text=edited_text)
    
    # Update resume
    db_resume.parsed_data = resume_data.model_dump()
    
    # Recalculate score
    db_jd = db.query(DBJobDescription).filter(DBJobDescription.id == session.jd_id).first()
    jd_data = JobDescription(**db_jd.parsed_data)
    
    breakdown = ats_scorer.score(resume_data, jd_data)
    new_score = ats_scorer.calculate_ats_score(breakdown)
    semantic_fit, semantic_score, _ = semantic_matcher.calculate_semantic_fit(resume_data, jd_data)
    
    session.current_score = new_score
    session.current_semantic_fit = semantic_fit
    
    db.commit()
    
    return {
        "message": "Suggestion edited and accepted",
        "new_score": new_score,
        "semantic_fit": semantic_fit
    }

def apply_suggestion_to_resume(resume_data: ResumeData, suggestion, edited_text: Optional[str] = None):
    """Helper function to apply suggestion to resume data."""
    new_text = edited_text if edited_text else suggestion.suggested_text
    
    if suggestion.section_type == 'summary':
        resume_data.summary = new_text
    elif suggestion.section_type == 'skill':
        # Extract skill from suggested text (might be comma-separated list)
        skills_to_add = [s.strip() for s in new_text.split(',')]
        for skill in skills_to_add:
            if skill and skill not in resume_data.skills:
                resume_data.skills.append(skill)
    elif suggestion.section_type == 'bullet' and suggestion.section_id:
        # Parse section_id: experience_{idx}_bullet_{bullet_idx}
        parts = suggestion.section_id.split('_')
        if len(parts) >= 4:
            try:
                exp_idx = int(parts[1])
                bullet_idx = int(parts[3])
                if exp_idx < len(resume_data.experience):
                    exp = resume_data.experience[exp_idx]
                    if bullet_idx < len(exp.bullets):
                        exp.bullets[bullet_idx].text = new_text
            except (ValueError, IndexError):
                pass

# Phase 5: Export Endpoints
@app.post("/api/export-pdf")
async def export_resume_pdf(request: Request, db: Session = Depends(get_db)):
    """Generate PDF resume with accepted changes applied."""
    try:
        body = await request.json()
    except:
        body = {}
    
    accepted_changes = body.get('accepted_changes', {})
    
    # Get the default resume
    db_resume = db.query(DBResume).filter(DBResume.is_default == True).first()
    if not db_resume:
        raise HTTPException(status_code=404, detail="No resume found. Please upload a resume first.")
    
    resume_data = ResumeData(**db_resume.parsed_data)
    
    # Create exports directory if it doesn't exist
    EXPORT_DIR.mkdir(exist_ok=True)
    
    # Generate PDF file
    export_id = str(uuid.uuid4())
    filename = f"resume_tailored_{export_id}.pdf"
    output_path = EXPORT_DIR / filename
    
    # Build PDF
    try:
        resume_builder.rebuild_resume_pdf(
            resume_data,
            accepted_changes,
            str(output_path)
        )
    except Exception as e:
        print(f"Error generating PDF: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate PDF: {str(e)}")
    
    # Return file for download
    return FileResponse(
        path=str(output_path),
        filename=f"{resume_data.personal_info.name or 'Resume'}_Tailored.pdf",
        media_type='application/pdf'
    )

@app.post("/api/export-docx")
async def export_resume_docx(request: Request, db: Session = Depends(get_db)):
    """Generate DOCX resume with accepted changes applied - preserves more formatting."""
    try:
        body = await request.json()
    except:
        body = {}
    
    accepted_changes = body.get('accepted_changes', {})
    
    # Get the default resume
    db_resume = db.query(DBResume).filter(DBResume.is_default == True).first()
    if not db_resume:
        raise HTTPException(status_code=404, detail="No resume found. Please upload a resume first.")
    
    resume_data = ResumeData(**db_resume.parsed_data)
    
    # Create exports directory if it doesn't exist
    EXPORT_DIR.mkdir(exist_ok=True)
    
    # Generate DOCX file
    export_id = str(uuid.uuid4())
    filename = f"resume_tailored_{export_id}.docx"
    output_path = EXPORT_DIR / filename
    
    # Try to use original file if it was a DOCX
    original_path = db_resume.original_path
    
    try:
        if original_path and Path(original_path).suffix.lower() == '.docx' and Path(original_path).exists():
            # Rebuild from original DOCX to preserve formatting
            resume_builder.rebuild_resume(
                original_path,
                resume_data,
                accepted_changes,
                str(output_path)
            )
        else:
            # Create new DOCX
            resume_builder._create_new_document(resume_data, str(output_path))
    except Exception as e:
        print(f"Error generating DOCX: {e}")
        # Fallback to creating new document
        resume_builder._create_new_document(resume_data, str(output_path))
    
    # Return file for download
    return FileResponse(
        path=str(output_path),
        filename=f"{resume_data.personal_info.name or 'Resume'}_Tailored.docx",
        media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    )

@app.post("/api/export", response_model=ExportResponse)
async def export_resume(session_id: int, db: Session = Depends(get_db)):
    """Generate final resume with all accepted changes."""
    session = db.query(Session).filter(Session.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Get resume and JD2
    db_resume = db.query(DBResume).filter(DBResume.id == session.resume_id).first()
    db_jd = db.query(DBJobDescription).filter(DBJobDescription.id == session.jd_id).first()
    
    resume_data = ResumeData(**db_resume.parsed_data)
    jd_data = JobDescription(**db_jd.parsed_data)
    
    # Get all accepted suggestions
    accepted_suggestions = db.query(Suggestion).filter(
        Suggestion.session_id == session_id,
        Suggestion.status.in_(['accepted', 'edited'])
    ).all()
    
    # Build accepted changes map
    accepted_changes = {}
    for suggestion in accepted_suggestions:
        text = suggestion.edited_text if suggestion.status == 'edited' else suggestion.suggested_text
        accepted_changes[suggestion.section_id] = text
    
    # Generate resume file
    export_id = str(uuid.uuid4())
    filename = f"resume_tailored_{export_id}.docx"
    output_path = EXPORT_DIR / filename
    
    # Rebuild resume
    try:
        resume_builder.rebuild_resume(
            db_resume.original_path,
            resume_data,
            accepted_changes,
            str(output_path)
        )
    except Exception as e:
        # Fallback to creating new document
        resume_builder._create_new_document(resume_data, str(output_path))
    
    # Generate fit summary
    fit_summary_data = suggestion_engine.generate_fit_summary(
        resume_data,
        jd_data,
        session.current_score,
        session.current_semantic_fit
    )
    
    # Store export record
    db_export = Export(
        session_id=session_id,
        filename=filename,
        file_path=str(output_path),
        fit_summary=json.dumps(fit_summary_data)
    )
    db.add(db_export)
    db.commit()
    db.refresh(db_export)
    
    return ExportResponse(
        export_id=str(db_export.id),
        filename=filename,
        fit_summary=json.dumps(fit_summary_data),
        top_strengths=fit_summary_data.get('top_strengths', []),
        key_gaps=fit_summary_data.get('key_gaps', [])
    )

@app.get("/api/download/{export_id}")
async def download_export(export_id: int, db: Session = Depends(get_db)):
    """Download generated resume file."""
    db_export = db.query(Export).filter(Export.id == export_id).first()
    if not db_export:
        raise HTTPException(status_code=404, detail="Export not found")
    
    file_path = Path(db_export.file_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    return FileResponse(
        path=str(file_path),
        filename=db_export.filename,
        media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    )
@app.get("/api/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "message": "Perfect Resume API is running"}

@app.get("/favicon.ico")
async def favicon():
    """Return empty favicon to suppress 404 errors."""
    from fastapi.responses import Response
    return Response(content=b"", media_type="image/x-icon")

@app.get("/health")
async def health_root():
    """Root health check endpoint."""
    return {"status": "ok", "message": "Perfect Resume API is running"}

if __name__ == "__main__":
    import uvicorn
    # Read PORT from environment variable for deployment (Koyeb sets this)
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)


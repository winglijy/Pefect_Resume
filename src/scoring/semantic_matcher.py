from typing import List, Dict, Tuple
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from ..models.schemas import ResumeData, JobDescription
from ..config import get_embeddings

class SemanticMatcher:
    """Calculate semantic similarity between resume and job description."""
    
    def __init__(self):
        pass
    
    def calculate_semantic_fit(self, resume: ResumeData, jd: JobDescription) -> Tuple[str, float, Dict[str, float]]:
        """
        Calculate semantic fit score.
        
        Args:
            resume: Parsed resume data
            jd: Parsed job description
            
        Returns:
            Tuple of (fit_level, score, section_scores)
        """
        # Extract sections for comparison
        resume_sections = self._extract_resume_sections(resume)
        jd_sections = self._extract_jd_sections(jd)
        
        # Generate embeddings
        resume_texts = list(resume_sections.values())
        jd_texts = list(jd_sections.values())
        
        all_texts = resume_texts + jd_texts
        embeddings = get_embeddings(all_texts)
        
        resume_embeddings = embeddings[:len(resume_texts)]
        jd_embeddings = embeddings[len(resume_texts):]
        
        # Calculate similarity scores for each section
        section_scores = {}
        similarities = []
        
        resume_keys = list(resume_sections.keys())
        jd_keys = list(jd_sections.keys())
        
        # Compare each resume section with each JD section
        for i, resume_emb in enumerate(resume_embeddings):
            max_sim = 0.0
            best_match = None
            
            for j, jd_emb in enumerate(jd_embeddings):
                sim = cosine_similarity([resume_emb], [jd_emb])[0][0]
                if sim > max_sim:
                    max_sim = sim
                    best_match = jd_keys[j]
            
            section_scores[resume_keys[i]] = {
                'score': float(max_sim),
                'matched_with': best_match
            }
            similarities.append(max_sim)
        
        # Calculate overall semantic score (average)
        overall_score = float(np.mean(similarities)) if similarities else 0.0
        
        # Classify fit level
        if overall_score >= 0.7:
            fit_level = "High"
        elif overall_score >= 0.5:
            fit_level = "Medium"
        else:
            fit_level = "Low"
        
        return fit_level, overall_score, section_scores
    
    def _extract_resume_sections(self, resume: ResumeData) -> Dict[str, str]:
        """Extract text sections from resume for semantic comparison."""
        sections = {}
        
        # Summary section
        if resume.summary:
            sections['summary'] = resume.summary
        
        # Experience sections
        for i, exp in enumerate(resume.experience):
            exp_text = f"{exp.title} at {exp.company}. "
            exp_text += " ".join([bullet.text for bullet in exp.bullets])
            sections[f'experience_{i}'] = exp_text
        
        # Skills section
        if resume.skills:
            sections['skills'] = ", ".join(resume.skills)
        
        # Education section
        for i, edu in enumerate(resume.education):
            edu_text = f"{edu.degree} from {edu.institution}"
            if edu.field:
                edu_text += f" in {edu.field}"
            sections[f'education_{i}'] = edu_text
        
        return sections
    
    def _extract_jd_sections(self, jd: JobDescription) -> Dict[str, str]:
        """Extract text sections from job description for semantic comparison."""
        sections = {}
        
        # Role description
        sections['role'] = jd.role_title
        if jd.company:
            sections['role'] += f" at {jd.company}"
        
        # Responsibilities
        if jd.responsibilities:
            sections['responsibilities'] = " ".join(jd.responsibilities)
        
        # Requirements
        if jd.requirements:
            sections['requirements'] = " ".join(jd.requirements)
        
        # Preferred qualifications
        if jd.preferred_qualifications:
            sections['preferred'] = " ".join(jd.preferred_qualifications)
        
        # Skills
        if jd.required_skills:
            sections['required_skills'] = ", ".join(jd.required_skills)
        if jd.preferred_skills:
            sections['preferred_skills'] = ", ".join(jd.preferred_skills)
        
        return sections


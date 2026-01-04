from typing import List, Dict, Set, Tuple
from ..models.schemas import ResumeData, JobDescription, ScoreBreakdown

class ATSScorer:
    """Calculate ATS-style score for resume against job description."""
    
    def __init__(self):
        pass
    
    def score(self, resume: ResumeData, jd: JobDescription) -> ScoreBreakdown:
        """
        Calculate ATS score breakdown.
        
        Args:
            resume: Parsed resume data
            jd: Parsed job description
            
        Returns:
            ScoreBreakdown with detailed scoring information
        """
        # Extract all text from resume
        resume_text = self._extract_resume_text(resume).lower()
        jd_text = self._extract_jd_text(jd).lower()
        
        # Keyword matching
        keyword_score, matched_keywords, missing_keywords = self._calculate_keyword_score(
            resume_text, jd
        )
        
        # Skill matching
        skill_score, matched_skills, missing_skills = self._calculate_skill_score(
            resume, jd
        )
        
        # Section completeness
        completeness_score, section_completeness = self._calculate_completeness_score(
            resume
        )
        
        return ScoreBreakdown(
            keyword_score=keyword_score,
            skill_score=skill_score,
            completeness_score=completeness_score,
            matched_keywords=matched_keywords,
            missing_keywords=missing_keywords,
            matched_skills=matched_skills,
            missing_skills=missing_skills,
            section_completeness=section_completeness
        )
    
    def calculate_ats_score(self, breakdown: ScoreBreakdown) -> float:
        """
        Calculate final ATS score (0-100) from breakdown.
        
        Formula: keyword_score * 40% + skill_score * 40% + completeness_score * 20%
        """
        return (
            breakdown.keyword_score * 0.4 +
            breakdown.skill_score * 0.4 +
            breakdown.completeness_score * 0.2
        )
    
    def _extract_resume_text(self, resume: ResumeData) -> str:
        """Extract all text content from resume."""
        texts = []
        
        if resume.summary:
            texts.append(resume.summary)
        
        for exp in resume.experience:
            texts.append(f"{exp.title} {exp.company}")
            for bullet in exp.bullets:
                texts.append(bullet.text)
        
        for edu in resume.education:
            texts.append(f"{edu.degree} {edu.institution}")
        
        texts.extend(resume.skills)
        
        return " ".join(texts)
    
    def _extract_jd_text(self, jd: JobDescription) -> str:
        """Extract all text content from job description."""
        texts = []
        
        texts.append(jd.role_title)
        texts.extend(jd.responsibilities)
        texts.extend(jd.requirements)
        texts.extend(jd.preferred_qualifications)
        texts.extend(jd.required_skills)
        texts.extend(jd.preferred_skills)
        texts.extend(jd.keywords)
        
        return " ".join(texts)
    
    def _calculate_keyword_score(self, resume_text: str, jd: JobDescription) -> Tuple[float, List[str], List[str]]:
        """Calculate keyword overlap score."""
        # Collect all keywords from JD
        all_keywords = set()
        
        # Add explicit keywords
        all_keywords.update([kw.lower() for kw in jd.keywords])
        
        # Extract keywords from requirements and responsibilities
        for req in jd.requirements + jd.responsibilities:
            # Extract important words (nouns, technical terms)
            words = req.lower().split()
            # Filter for meaningful keywords (length > 3, not common words)
            important_words = [w for w in words if len(w) > 3 and w not in self._get_stop_words()]
            all_keywords.update(important_words)
        
        # Check which keywords appear in resume
        matched_keywords = []
        missing_keywords = []
        
        for keyword in all_keywords:
            # Check for exact match or variations
            if self._keyword_match(keyword, resume_text):
                matched_keywords.append(keyword)
            else:
                missing_keywords.append(keyword)
        
        # Calculate score (percentage of matched keywords)
        if len(all_keywords) == 0:
            score = 100.0
        else:
            score = (len(matched_keywords) / len(all_keywords)) * 100.0
        
        return score, matched_keywords[:20], missing_keywords[:20]  # Limit to top 20
    
    def _keyword_match(self, keyword: str, text: str) -> bool:
        """Check if keyword matches in text (with variations)."""
        keyword_lower = keyword.lower()
        text_lower = text.lower()
        
        # Exact match
        if keyword_lower in text_lower:
            return True
        
        # Check for variations (plural, past tense, etc.)
        variations = [
            keyword_lower + 's',  # plural
            keyword_lower + 'ed',  # past tense
            keyword_lower + 'ing',  # gerund
            keyword_lower[:-1] if keyword_lower.endswith('s') else None,  # singular
        ]
        
        for variation in variations:
            if variation and variation in text_lower:
                return True
        
        return False
    
    def _calculate_skill_score(self, resume: ResumeData, jd: JobDescription) -> Tuple[float, List[str], List[str]]:
        """Calculate skill matching score."""
        resume_skills = set([s.lower() for s in resume.skills])
        
        # Also extract skills from experience bullets
        for exp in resume.experience:
            for bullet in exp.bullets:
                bullet_lower = bullet.text.lower()
                # Check if any JD skill is mentioned in bullet
                for skill in jd.required_skills + jd.preferred_skills:
                    if skill.lower() in bullet_lower:
                        resume_skills.add(skill.lower())
        
        required_skills = set([s.lower() for s in jd.required_skills])
        preferred_skills = set([s.lower() for s in jd.preferred_skills])
        
        # Match required skills
        matched_required = resume_skills.intersection(required_skills)
        missing_required = required_skills - resume_skills
        
        # Match preferred skills
        matched_preferred = resume_skills.intersection(preferred_skills)
        
        # Calculate score: 70% weight on required, 30% on preferred
        if len(required_skills) == 0 and len(preferred_skills) == 0:
            score = 100.0
        elif len(required_skills) == 0:
            # Only preferred skills
            score = (len(matched_preferred) / len(preferred_skills)) * 100.0 if preferred_skills else 100.0
        else:
            required_score = (len(matched_required) / len(required_skills)) * 70.0
            preferred_score = (len(matched_preferred) / len(preferred_skills)) * 30.0 if preferred_skills else 0.0
            score = required_score + preferred_score
        
        matched_skills = list(matched_required) + list(matched_preferred)
        missing_skills = list(missing_required)
        
        return score, matched_skills[:20], missing_skills[:20]
    
    def _calculate_completeness_score(self, resume: ResumeData) -> Tuple[float, Dict[str, bool]]:
        """Calculate section completeness score."""
        completeness = {}
        
        # Check required sections
        completeness['personal_info'] = bool(resume.personal_info.name and resume.personal_info.email)
        completeness['summary'] = bool(resume.summary and len(resume.summary) > 50)
        completeness['experience'] = len(resume.experience) > 0
        completeness['education'] = len(resume.education) > 0
        completeness['skills'] = len(resume.skills) > 0
        
        # Check experience quality
        completeness['experience_detailed'] = any(
            len(exp.bullets) >= 2 for exp in resume.experience
        )
        
        # Calculate score (percentage of complete sections)
        total_sections = len(completeness)
        complete_sections = sum(1 for v in completeness.values() if v)
        score = (complete_sections / total_sections) * 100.0
        
        return score, completeness
    
    def _get_stop_words(self) -> Set[str]:
        """Get common stop words to filter out."""
        return {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
            'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'be',
            'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
            'would', 'should', 'could', 'may', 'might', 'must', 'can', 'this',
            'that', 'these', 'those', 'i', 'you', 'he', 'she', 'it', 'we', 'they'
        }


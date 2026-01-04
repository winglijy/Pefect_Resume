"""
Job Scraper using Adzuna API
Finds recently posted jobs matching user's resume with intelligent matching
"""

import os
import re
import json
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Set, Tuple
from pathlib import Path
import sqlite3


class JobScraper:
    """Scrapes jobs from Adzuna API and matches against resume"""
    
    BASE_URL = "https://api.adzuna.com/v1/api/jobs"
    
    # High-value keywords for Product Management roles (customize as needed)
    PM_KEYWORDS = {
        "product manager", "product management", "product owner", "pm", "apm",
        "senior product manager", "lead product manager", "director of product",
        "group product manager", "principal product manager", "vp product",
        "technical product manager", "tpm", "platform product manager"
    }
    
    # Common tech skills with weights (higher = more important for matching)
    SKILL_WEIGHTS = {
        # PM Tools
        "jira": 3, "confluence": 3, "aha": 3, "productboard": 3, "asana": 2,
        "monday": 2, "trello": 2, "notion": 2, "miro": 2, "figma": 3,
        # Analytics
        "amplitude": 3, "mixpanel": 3, "tableau": 3, "looker": 3, "pendo": 3,
        "google analytics": 2, "ga4": 2, "sql": 4, "python": 3,
        # Technical
        "api": 3, "rest": 2, "graphql": 2, "aws": 3, "azure": 2, "gcp": 2,
        "machine learning": 3, "ml": 3, "ai": 3, "data science": 3,
        # Methodology
        "agile": 3, "scrum": 3, "kanban": 2, "lean": 2, "okr": 2,
        "a/b testing": 3, "experimentation": 3, "roadmap": 3,
        # Soft skills (lower weight)
        "leadership": 1, "communication": 1, "stakeholder": 2, "strategy": 2
    }
    
    def __init__(self, app_id: str = None, app_key: str = None, db_path: str = None):
        self.app_id = app_id or os.getenv("ADZUNA_APP_ID", "c61d61a1")
        self.app_key = app_key or os.getenv("ADZUNA_APP_KEY", "0ee75cef7e6277ce60aedec939de81cd")
        
        # Setup cache database
        if db_path is None:
            db_path = Path(__file__).parent.parent.parent / "data" / "jobs_cache.db"
        self.db_path = str(db_path)
        self._init_db()
    
    def _init_db(self):
        """Initialize SQLite database for caching jobs"""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                title TEXT,
                company TEXT,
                location TEXT,
                description TEXT,
                salary_min REAL,
                salary_max REAL,
                url TEXT,
                posted_date TEXT,
                fetched_date TEXT,
                search_query TEXT,
                match_score REAL DEFAULT 0,
                is_viewed INTEGER DEFAULT 0,
                is_applied INTEGER DEFAULT 0,
                is_hidden INTEGER DEFAULT 0
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS api_calls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                call_date TEXT,
                query TEXT,
                results_count INTEGER
            )
        """)
        
        conn.commit()
        conn.close()
    
    def get_api_usage(self) -> Dict:
        """Get API usage stats for current month"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        today = datetime.now()
        first_of_month = today.replace(day=1).strftime("%Y-%m-%d")
        
        cursor.execute("""
            SELECT COUNT(*) FROM api_calls 
            WHERE call_date >= ?
        """, (first_of_month,))
        
        calls_this_month = cursor.fetchone()[0]
        conn.close()
        
        return {
            "calls_this_month": calls_this_month,
            "limit": 250,
            "remaining": 250 - calls_this_month,
            "month": today.strftime("%B %Y")
        }
    
    def search_jobs(
        self,
        keywords: List[str],
        location: str = "",
        country: str = "us",
        max_days_old: int = 7,
        results_per_page: int = 50,
        page: int = 1,
        salary_min: int = None,
        remote_only: bool = False,
        category: str = None
    ) -> Dict:
        """
        Search for jobs matching keywords with improved query construction
        """
        
        # Build simple, effective search query
        # Keep it simple - just the main keywords
        clean_keywords = []
        for kw in keywords[:4]:  # Max 4 keywords
            # Clean each keyword
            kw_clean = kw.strip()
            if len(kw_clean) > 2 and len(kw_clean) < 50:
                clean_keywords.append(kw_clean)
        
        if not clean_keywords:
            clean_keywords = ["Product Manager"]
        
        # Simple OR query works best with Adzuna
        query = " OR ".join(clean_keywords)
        
        if remote_only:
            query += " remote"
        
        # Build API URL
        url = f"{self.BASE_URL}/{country}/search/{page}"
        
        params = {
            "app_id": self.app_id,
            "app_key": self.app_key,
            "what": query,
            "results_per_page": min(results_per_page, 50),
            "max_days_old": max_days_old,
            "sort_by": "relevance",  # Changed from date to relevance for better matches
            "content-type": "application/json"
        }
        
        # Add location filter
        if location and location.lower() not in ["usa", "us", "united states", "", "all"]:
            params["where"] = location
        
        # Add salary filter
        if salary_min:
            params["salary_min"] = salary_min
        
        # Add category filter for better targeting
        if category:
            params["category"] = category
        
        try:
            response = requests.get(url, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()
            
            # Log API call
            self._log_api_call(query, data.get("count", 0))
            
            # Process results
            jobs = self._process_results(data, query)
            
            return {
                "success": True,
                "total_count": data.get("count", 0),
                "page": page,
                "jobs": jobs,
                "query": query,
                "api_usage": self.get_api_usage()
            }
            
        except requests.RequestException as e:
            return {
                "success": False,
                "error": str(e),
                "jobs": [],
                "api_usage": self.get_api_usage()
            }
    
    def _is_job_title(self, keyword: str) -> bool:
        """Check if keyword looks like a job title"""
        keyword_lower = keyword.lower()
        title_indicators = [
            "manager", "director", "lead", "head", "vp", "chief",
            "engineer", "developer", "analyst", "designer", "specialist",
            "owner", "coordinator", "associate", "senior", "junior", "principal"
        ]
        return any(ind in keyword_lower for ind in title_indicators)
    
    def _process_results(self, data: Dict, query: str) -> List[Dict]:
        """Process and cache job results"""
        jobs = []
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        for result in data.get("results", []):
            job = {
                "id": str(result.get("id", "")),
                "title": result.get("title", ""),
                "company": result.get("company", {}).get("display_name", "Unknown"),
                "location": result.get("location", {}).get("display_name", ""),
                "description": result.get("description", ""),
                "salary_min": result.get("salary_min"),
                "salary_max": result.get("salary_max"),
                "url": result.get("redirect_url", ""),
                "posted_date": result.get("created", ""),
                "category": result.get("category", {}).get("label", "")
            }
            
            # Cache the job
            try:
                cursor.execute("""
                    INSERT OR REPLACE INTO jobs 
                    (id, title, company, location, description, salary_min, salary_max, url, posted_date, fetched_date, search_query)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    job["id"], job["title"], job["company"], job["location"],
                    job["description"], job["salary_min"], job["salary_max"],
                    job["url"], job["posted_date"], datetime.now().isoformat(), query
                ))
            except sqlite3.Error:
                pass
            
            jobs.append(job)
        
        conn.commit()
        conn.close()
        
        return jobs
    
    def _log_api_call(self, query: str, results_count: int):
        """Log API call for tracking usage"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO api_calls (call_date, query, results_count)
            VALUES (?, ?, ?)
        """, (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), query, results_count))
        
        conn.commit()
        conn.close()
    
    def match_jobs_to_resume(self, jobs: List[Dict], resume_data: Dict) -> List[Dict]:
        """
        Advanced job matching using weighted scoring
        
        Scoring breakdown:
        - Title match: 40 points max
        - Skills match: 35 points max  
        - Experience level match: 15 points max
        - Description relevance: 10 points max
        """
        
        # Extract resume data for matching
        resume_titles = self._extract_job_titles(resume_data)
        resume_skills = self._extract_skills(resume_data)
        resume_experience_years = self._estimate_experience_years(resume_data)
        resume_keywords = self._extract_all_keywords(resume_data)
        
        for job in jobs:
            score = 0
            matched_items = []
            
            job_title_lower = job.get("title", "").lower()
            job_desc_lower = job.get("description", "").lower()
            job_text = f"{job_title_lower} {job_desc_lower}"
            
            # 1. Title Match (40 points max)
            title_score, title_matches = self._score_title_match(
                job_title_lower, resume_titles
            )
            score += title_score
            matched_items.extend(title_matches)
            
            # 2. Skills Match (35 points max)
            skills_score, skill_matches = self._score_skills_match(
                job_text, resume_skills
            )
            score += skills_score
            matched_items.extend(skill_matches)
            
            # 3. Experience Level Match (15 points max)
            exp_score = self._score_experience_match(
                job_title_lower, job_desc_lower, resume_experience_years
            )
            score += exp_score
            
            # 4. Description Keyword Relevance (10 points max)
            desc_score, desc_matches = self._score_description_match(
                job_desc_lower, resume_keywords
            )
            score += desc_score
            matched_items.extend(desc_matches)
            
            # Ensure score is 0-100
            job["match_score"] = min(100, max(0, int(score)))
            job["matched_keywords"] = list(set(matched_items))[:10]
            
            # Add match breakdown for debugging
            job["match_breakdown"] = {
                "title": title_score,
                "skills": skills_score,
                "experience": exp_score,
                "description": desc_score
            }
        
        # Sort by match score (highest first)
        jobs.sort(key=lambda x: x.get("match_score", 0), reverse=True)
        
        return jobs
    
    def _extract_job_titles(self, resume_data: Dict) -> List[str]:
        """Extract job titles from resume experience"""
        titles = []
        for exp in resume_data.get("experience", []):
            if not isinstance(exp, dict):
                continue
            title = exp.get("title", "")
            if title and isinstance(title, str):
                titles.append(title.lower())
                # Also add common variations
                if "product manager" in title.lower():
                    titles.extend(["pm", "product", "product manager"])
                if "senior" in title.lower():
                    titles.append("senior")
                if "lead" in title.lower():
                    titles.append("lead")
        return list(set(titles))
    
    def _extract_skills(self, resume_data: Dict) -> Dict[str, int]:
        """Extract skills with weights from resume"""
        skills = {}
        
        # Get skills from resume
        for skill in resume_data.get("skills", []):
            if isinstance(skill, str):
                skill_lower = skill.lower().strip()
                # Use predefined weight or default to 2
                weight = self.SKILL_WEIGHTS.get(skill_lower, 2)
                skills[skill_lower] = weight
        
        # Also extract from summary and experience
        text_sources = []
        summary = resume_data.get("summary", "")
        if isinstance(summary, str):
            text_sources.append(summary)
        
        for exp in resume_data.get("experience", []):
            if isinstance(exp, dict):
                bullets = exp.get("bullets", [])
                for bullet in bullets:
                    if isinstance(bullet, str):
                        text_sources.append(bullet)
                    elif isinstance(bullet, dict):
                        # Handle case where bullet is a dict with text
                        text_sources.append(str(bullet.get("text", "")))
        
        full_text = " ".join(text_sources).lower()
        
        # Find known skills in text
        for skill, weight in self.SKILL_WEIGHTS.items():
            if skill in full_text and skill not in skills:
                skills[skill] = weight
        
        return skills
    
    def _estimate_experience_years(self, resume_data: Dict) -> int:
        """Estimate total years of experience from resume"""
        total_years = 0
        
        for exp in resume_data.get("experience", []):
            if not isinstance(exp, dict):
                continue
            dates = exp.get("dates", "")
            if not isinstance(dates, str):
                dates = ""
            # Try to extract year range
            years = re.findall(r'20\d{2}', dates)
            if len(years) >= 2:
                try:
                    diff = int(years[-1]) - int(years[0])
                    total_years += max(0, diff)
                except:
                    total_years += 2  # Default assumption
            elif "present" in dates.lower() or "current" in dates.lower():
                total_years += 2
        
        return min(total_years, 20)  # Cap at 20 years
    
    def _extract_all_keywords(self, resume_data: Dict) -> Set[str]:
        """Extract all meaningful keywords from resume"""
        keywords = set()
        
        # Skills
        for skill in resume_data.get("skills", []):
            if isinstance(skill, str):
                keywords.add(skill.lower())
        
        # Summary words
        summary = resume_data.get("summary", "")
        if isinstance(summary, str):
            for word in re.findall(r'\b[a-zA-Z]{4,}\b', summary.lower()):
                if word not in {"that", "this", "with", "from", "have", "been", "were", "their"}:
                    keywords.add(word)
        
        # Experience bullets - extract key terms
        for exp in resume_data.get("experience", []):
            if isinstance(exp, dict):
                for bullet in exp.get("bullets", []):
                    bullet_text = bullet if isinstance(bullet, str) else str(bullet.get("text", "") if isinstance(bullet, dict) else "")
                    # Extract capitalized terms (often important)
                    for match in re.findall(r'[A-Z][a-zA-Z]+', bullet_text):
                        if len(match) > 3:
                            keywords.add(match.lower())
        
        return keywords
    
    def _score_title_match(self, job_title: str, resume_titles: List[str]) -> Tuple[float, List[str]]:
        """Score how well job title matches resume titles (0-40 points)"""
        score = 0
        matches = []
        
        for resume_title in resume_titles:
            # Exact match
            if resume_title in job_title:
                score = max(score, 40)
                matches.append(f"Title: {resume_title}")
            # Partial match
            elif any(word in job_title for word in resume_title.split() if len(word) > 3):
                score = max(score, 25)
                matches.append(f"Similar: {resume_title}")
        
        # Check for PM-specific titles
        if any(pm_title in job_title for pm_title in self.PM_KEYWORDS):
            if any(pm_title in " ".join(resume_titles) for pm_title in self.PM_KEYWORDS):
                score = max(score, 35)
                matches.append("PM Role Match")
        
        return score, matches
    
    def _score_skills_match(self, job_text: str, resume_skills: Dict[str, int]) -> Tuple[float, List[str]]:
        """Score skills match (0-35 points)"""
        total_weight = sum(resume_skills.values()) or 1
        matched_weight = 0
        matches = []
        
        for skill, weight in resume_skills.items():
            if skill in job_text:
                matched_weight += weight
                matches.append(skill)
        
        # Calculate percentage and scale to 35 points
        match_ratio = matched_weight / total_weight
        score = match_ratio * 35
        
        return score, matches
    
    def _score_experience_match(self, job_title: str, job_desc: str, resume_years: int) -> float:
        """Score experience level match (0-15 points)"""
        
        # Determine required experience from job
        required_years = 0
        
        # Check title for level
        if any(word in job_title for word in ["senior", "sr.", "lead", "principal", "staff"]):
            required_years = 5
        elif any(word in job_title for word in ["junior", "jr.", "associate", "entry"]):
            required_years = 1
        elif "director" in job_title or "vp" in job_title or "head" in job_title:
            required_years = 8
        else:
            required_years = 3  # Mid-level default
        
        # Check description for explicit requirements
        year_matches = re.findall(r'(\d+)\+?\s*(?:years?|yrs?)', job_desc)
        if year_matches:
            try:
                required_years = max(int(y) for y in year_matches)
            except:
                pass
        
        # Score based on how well experience matches
        if resume_years >= required_years:
            return 15  # Full points if qualified
        elif resume_years >= required_years - 2:
            return 10  # Close enough
        elif resume_years >= required_years - 4:
            return 5   # Stretch
        else:
            return 0   # Under-qualified
    
    def _score_description_match(self, job_desc: str, resume_keywords: Set[str]) -> Tuple[float, List[str]]:
        """Score description keyword overlap (0-10 points)"""
        matches = []
        
        for keyword in resume_keywords:
            if keyword in job_desc:
                matches.append(keyword)
        
        # Cap at 10 matches for scoring
        match_count = min(len(matches), 10)
        score = match_count  # 1 point per match, max 10
        
        return score, matches[:5]  # Return top 5 for display
    
    def extract_search_keywords(self, resume_data: Dict) -> List[str]:
        """Extract optimal search keywords from resume - focused and clean"""
        keywords = []
        
        # Valid job title keywords (to filter against)
        valid_title_words = {
            "manager", "director", "lead", "head", "vp", "chief", "senior", "junior",
            "engineer", "developer", "analyst", "designer", "specialist", "associate",
            "product", "project", "program", "technical", "software", "data", "marketing",
            "operations", "business", "sales", "customer", "support", "quality"
        }
        
        # Priority 1: Extract core job title (simplified)
        for exp in resume_data.get("experience", []):
            if not isinstance(exp, dict):
                continue
            title = exp.get("title", "")
            if title and isinstance(title, str):
                # Clean the title - remove company info, dates, parenthetical details
                clean_title = title.split("|")[0].strip()
                clean_title = clean_title.split(",")[0].strip()
                clean_title = re.sub(r'\([^)]*\)', '', clean_title).strip()
                clean_title = re.sub(r'\s+', ' ', clean_title).strip()
                
                # Validate it looks like a job title (contains valid title words)
                title_words = set(clean_title.lower().split())
                if clean_title and len(clean_title) < 40 and title_words & valid_title_words:
                    if clean_title not in keywords:
                        keywords.append(clean_title)
        
        # Always include "Product Manager" if we found PM-related titles
        if any("product" in kw.lower() for kw in keywords):
            if "Product Manager" not in keywords:
                keywords.insert(0, "Product Manager")
        
        # Ensure we have at least some keywords
        if not keywords:
            keywords = ["Product Manager"]
        
        return keywords[:4]  # Return top 4 for focused search
    
    def get_cached_jobs(self, days: int = 7, min_score: int = 0) -> List[Dict]:
        """Get jobs from cache"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        
        cursor.execute("""
            SELECT id, title, company, location, description, salary_min, salary_max, 
                   url, posted_date, match_score, is_viewed, is_applied
            FROM jobs 
            WHERE fetched_date >= ? AND match_score >= ? AND is_hidden = 0
            ORDER BY match_score DESC, posted_date DESC
            LIMIT 100
        """, (cutoff, min_score))
        
        jobs = []
        for row in cursor.fetchall():
            jobs.append({
                "id": row[0],
                "title": row[1],
                "company": row[2],
                "location": row[3],
                "description": row[4],
                "salary_min": row[5],
                "salary_max": row[6],
                "url": row[7],
                "posted_date": row[8],
                "match_score": row[9] or 0,
                "is_viewed": bool(row[10]),
                "is_applied": bool(row[11])
            })
        
        conn.close()
        return jobs
    
    def mark_job_viewed(self, job_id: str):
        """Mark a job as viewed"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("UPDATE jobs SET is_viewed = 1 WHERE id = ?", (job_id,))
        conn.commit()
        conn.close()
    
    def mark_job_applied(self, job_id: str):
        """Mark a job as applied"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("UPDATE jobs SET is_applied = 1 WHERE id = ?", (job_id,))
        conn.commit()
        conn.close()
    
    def hide_job(self, job_id: str):
        """Hide a job from results"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("UPDATE jobs SET is_hidden = 1 WHERE id = ?", (job_id,))
        conn.commit()
        conn.close()
    
    def update_job_score(self, job_id: str, score: float):
        """Update cached job score"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("UPDATE jobs SET match_score = ? WHERE id = ?", (score, job_id))
        conn.commit()
        conn.close()


# Quick test
if __name__ == "__main__":
    scraper = JobScraper()
    
    result = scraper.search_jobs(
        keywords=["Product Manager", "SQL", "Agile"],
        location="San Francisco",
        max_days_old=7
    )
    
    print(f"Found {result['total_count']} jobs")
    print(f"API Usage: {result['api_usage']}")
    
    for job in result["jobs"][:5]:
        print(f"- {job['title']} at {job['company']} (Score: {job.get('match_score', 'N/A')})")

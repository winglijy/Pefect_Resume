"""
LinkedIn Job Scraper using JSearch (RapidAPI)
Finds jobs specifically from LinkedIn
"""

import os
import re
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Set
from pathlib import Path
import sqlite3


class LinkedInScraper:
    """Scrapes LinkedIn jobs via JSearch API"""
    
    BASE_URL = "https://jsearch.p.rapidapi.com/search"
    
    # Skill weights for matching
    SKILL_WEIGHTS = {
        "jira": 3, "confluence": 3, "aha": 3, "figma": 3, "miro": 2,
        "amplitude": 3, "mixpanel": 3, "tableau": 3, "sql": 4, "python": 3,
        "api": 3, "aws": 3, "agile": 3, "scrum": 3, "a/b testing": 3,
        "roadmap": 3, "okr": 2, "product": 2, "strategy": 2
    }
    
    def __init__(self, api_key: str = None, db_path: str = None):
        self.api_key = api_key or os.getenv(
            "RAPIDAPI_KEY", 
            "9a6bc3e45amshe2142117f94ac63p13571djsn1bdd288e922f"
        )
        self.headers = {
            "X-RapidAPI-Key": self.api_key,
            "X-RapidAPI-Host": "jsearch.p.rapidapi.com"
        }
        
        # Setup cache database
        if db_path is None:
            db_path = Path(__file__).parent.parent.parent / "data" / "linkedin_jobs.db"
        self.db_path = str(db_path)
        self._init_db()
    
    def _init_db(self):
        """Initialize SQLite database for caching"""
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
                url TEXT,
                posted_date TEXT,
                fetched_date TEXT,
                match_score REAL DEFAULT 0,
                is_viewed INTEGER DEFAULT 0,
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
            "limit": 100,  # JSearch free tier
            "remaining": max(0, 100 - calls_this_month),
            "month": today.strftime("%B %Y")
        }
    
    def search_jobs(
        self,
        keywords: List[str],
        location: str = "",
        date_posted: str = "week",
        remote_only: bool = False,
        num_results: int = 10
    ) -> Dict:
        """
        Search for LinkedIn jobs
        
        Args:
            keywords: Search terms (e.g., ["Product Manager"])
            location: Location (e.g., "San Francisco, CA")
            date_posted: "today", "3days", "week", "month"
            remote_only: Filter for remote jobs
            num_results: Number of results (max 10 per call)
        """
        
        # Build query string
        query_parts = keywords.copy()
        if location:
            query_parts.append(f"in {location}")
        if remote_only:
            query_parts.append("remote")
        
        query = " ".join(query_parts)
        
        params = {
            "query": query,
            "page": "1",
            "num_pages": "1",
            "date_posted": date_posted,
            "site_name": "linkedin.com"  # LinkedIn only!
        }
        
        try:
            response = requests.get(
                self.BASE_URL, 
                headers=self.headers, 
                params=params,
                timeout=15
            )
            response.raise_for_status()
            data = response.json()
            
            # Log API call
            self._log_api_call(query, len(data.get("data", [])))
            
            # Process results
            jobs = self._process_results(data, query)
            
            return {
                "success": True,
                "total_count": len(jobs),
                "jobs": jobs,
                "query": query,
                "source": "LinkedIn via JSearch",
                "api_usage": self.get_api_usage()
            }
            
        except requests.RequestException as e:
            error_msg = str(e)
            if "429" in error_msg:
                error_msg = "Rate limit exceeded. Please wait a moment."
            elif "401" in error_msg or "403" in error_msg:
                error_msg = "API key invalid or expired."
            
            return {
                "success": False,
                "error": error_msg,
                "jobs": [],
                "api_usage": self.get_api_usage()
            }
    
    def _process_results(self, data: Dict, query: str) -> List[Dict]:
        """Process JSearch API results - only keep LinkedIn jobs"""
        jobs = []
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        for item in data.get("data", []):
            # Get all possible URLs
            apply_link = item.get("job_apply_link", "")
            google_link = item.get("job_google_link", "")
            
            # Prioritize LinkedIn URL
            url = ""
            if "linkedin.com" in apply_link:
                url = apply_link
            elif "linkedin.com" in google_link:
                url = google_link
            else:
                # Skip non-LinkedIn jobs
                continue
            
            job = {
                "id": item.get("job_id", ""),
                "title": item.get("job_title", ""),
                "company": item.get("employer_name", "Unknown"),
                "location": self._format_location(item),
                "description": item.get("job_description", "")[:500],  # Truncate
                "url": url,
                "posted_date": item.get("job_posted_at_datetime_utc", ""),
                "employment_type": item.get("job_employment_type", ""),
                "is_remote": item.get("job_is_remote", False),
                "salary_min": item.get("job_min_salary"),
                "salary_max": item.get("job_max_salary"),
                "logo": item.get("employer_logo", "")
            }
            
            # Cache job
            try:
                cursor.execute("""
                    INSERT OR REPLACE INTO jobs 
                    (id, title, company, location, description, url, posted_date, fetched_date)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    job["id"], job["title"], job["company"], job["location"],
                    job["description"], job["url"], job["posted_date"],
                    datetime.now().isoformat()
                ))
            except sqlite3.Error:
                pass
            
            jobs.append(job)
        
        conn.commit()
        conn.close()
        
        return jobs
    
    def _format_location(self, item: Dict) -> str:
        """Format location from JSearch data"""
        city = item.get("job_city", "")
        state = item.get("job_state", "")
        country = item.get("job_country", "")
        
        parts = [p for p in [city, state] if p]
        location = ", ".join(parts)
        
        if item.get("job_is_remote"):
            location = f"{location} (Remote)" if location else "Remote"
        
        return location or "Location not specified"
    
    def _log_api_call(self, query: str, results_count: int):
        """Log API call for tracking"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO api_calls (call_date, query, results_count)
            VALUES (?, ?, ?)
        """, (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), query, results_count))
        
        conn.commit()
        conn.close()
    
    def match_jobs_to_resume(self, jobs: List[Dict], resume_data: Dict) -> List[Dict]:
        """Score jobs based on resume match"""
        
        # Extract resume data
        resume_titles = self._extract_titles(resume_data)
        resume_skills = self._extract_skills(resume_data)
        resume_keywords = self._extract_keywords(resume_data)
        
        for job in jobs:
            score = 0
            matched = []
            
            job_text = f"{job.get('title', '')} {job.get('description', '')}".lower()
            job_title = job.get('title', '').lower()
            
            # Title match (40 points)
            for title in resume_titles:
                if title in job_title:
                    score += 40
                    matched.append(f"Title: {title}")
                    break
                elif any(word in job_title for word in title.split() if len(word) > 3):
                    score += 25
                    matched.append(f"Similar: {title}")
                    break
            
            # Skills match (35 points)
            skill_matches = 0
            for skill, weight in resume_skills.items():
                if skill in job_text:
                    skill_matches += weight
                    matched.append(skill)
            skill_score = min(35, skill_matches * 3)
            score += skill_score
            
            # Keywords (15 points)
            keyword_matches = sum(1 for kw in resume_keywords if kw in job_text)
            score += min(15, keyword_matches * 2)
            
            # Remote bonus if mentioned in resume
            if job.get('is_remote') and 'remote' in str(resume_data).lower():
                score += 5
            
            job["match_score"] = min(100, score)
            job["matched_keywords"] = matched[:8]
        
        # Sort by score
        jobs.sort(key=lambda x: x.get("match_score", 0), reverse=True)
        
        return jobs
    
    def _extract_titles(self, resume_data: Dict) -> List[str]:
        """Extract job titles from resume"""
        titles = []
        for exp in resume_data.get("experience", []):
            if isinstance(exp, dict):
                title = exp.get("title", "")
                if isinstance(title, str) and title:
                    # Clean title
                    clean = title.split("|")[0].split(",")[0].strip().lower()
                    if clean and len(clean) < 50:
                        titles.append(clean)
        return titles
    
    def _extract_skills(self, resume_data: Dict) -> Dict[str, int]:
        """Extract skills with weights"""
        skills = {}
        for skill in resume_data.get("skills", []):
            if isinstance(skill, str):
                skill_lower = skill.lower().strip()
                weight = self.SKILL_WEIGHTS.get(skill_lower, 1)
                skills[skill_lower] = weight
        return skills
    
    def _extract_keywords(self, resume_data: Dict) -> Set[str]:
        """Extract keywords from resume"""
        keywords = set()
        
        # Skills
        for skill in resume_data.get("skills", []):
            if isinstance(skill, str):
                keywords.add(skill.lower())
        
        # From experience
        for exp in resume_data.get("experience", []):
            if isinstance(exp, dict):
                for bullet in exp.get("bullets", []):
                    if isinstance(bullet, str):
                        # Extract capitalized words
                        for word in re.findall(r'\b[A-Z][a-z]+\b', bullet):
                            if len(word) > 3:
                                keywords.add(word.lower())
        
        return keywords
    
    def hide_job(self, job_id: str):
        """Hide a job"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("UPDATE jobs SET is_hidden = 1 WHERE id = ?", (job_id,))
        conn.commit()
        conn.close()
    
    def mark_viewed(self, job_id: str):
        """Mark job as viewed"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("UPDATE jobs SET is_viewed = 1 WHERE id = ?", (job_id,))
        conn.commit()
        conn.close()


# Test
if __name__ == "__main__":
    scraper = LinkedInScraper()
    result = scraper.search_jobs(
        keywords=["Product Manager"],
        location="San Francisco",
        date_posted="week"
    )
    
    print(f"Success: {result['success']}")
    print(f"Found: {result['total_count']} jobs")
    print(f"API Usage: {result['api_usage']}")
    
    for job in result.get("jobs", [])[:3]:
        print(f"  - {job['title']} at {job['company']}")


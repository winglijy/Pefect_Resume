import requests
from bs4 import BeautifulSoup
from typing import Optional, List, Tuple
import re
import json
from ..models.schemas import JobDescription
from ..config import generate_chat_completion

class JobDescriptionParser:
    """Parse job descriptions from URLs or raw text."""
    
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        self.use_llm = True  # Use LLM for parsing by default
    
    def parse(self, source: str) -> JobDescription:
        """
        Parse job description from URL or raw text.
        
        Args:
            source: URL or raw text content
            
        Returns:
            JobDescription object
        """
        # Check if it's a URL
        if source.startswith('http://') or source.startswith('https://'):
            return self._parse_url(source)
        else:
            return self._parse_text(source)
    
    def _parse_url(self, url: str) -> JobDescription:
        """Parse job description from URL."""
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            html = response.text
            return self._parse_html(html, url)
        except Exception as e:
            # Fallback to manual paste
            raise ValueError(f"Failed to parse URL: {e}. Please paste the job description text directly.")
    
    def _parse_html(self, html: str, url: str) -> JobDescription:
        """Parse HTML content to extract job description."""
        soup = BeautifulSoup(html, 'html.parser')
        
        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.decompose()
        
        # Try to find job description content
        # LinkedIn job posting structure
        if 'linkedin.com/jobs' in url:
            return self._parse_linkedin(soup, url)
        else:
            # Generic company career page
            return self._parse_generic(soup, url)
    
    def _parse_linkedin(self, soup: BeautifulSoup, url: str) -> JobDescription:
        """Parse LinkedIn job posting."""
        jd = JobDescription(role_title="", raw_text="")
        
        # Extract title
        title_selectors = [
            'h1.job-details-jobs-unified-top-card__job-title',
            'h1[data-test-id="job-title"]',
            'h1.top-card-layout__title'
        ]
        for selector in title_selectors:
            title_elem = soup.select_one(selector)
            if title_elem:
                jd.role_title = title_elem.get_text(strip=True)
                break
        
        # Extract company
        company_selectors = [
            'a.job-details-jobs-unified-top-card__company-name',
            'a[data-test-id="job-company"]',
            'a.top-card-layout__company-name'
        ]
        for selector in company_selectors:
            company_elem = soup.select_one(selector)
            if company_elem:
                jd.company = company_elem.get_text(strip=True)
                break
        
        # Extract description
        desc_selectors = [
            'div.job-details-jobs-unified-top-card__job-description',
            'div[data-test-id="job-description"]',
            'div.description__text'
        ]
        description_text = ""
        for selector in desc_selectors:
            desc_elem = soup.select_one(selector)
            if desc_elem:
                description_text = desc_elem.get_text(separator='\n', strip=True)
                break
        
        if not description_text:
            # Fallback: get all text content
            description_text = soup.get_text(separator='\n', strip=True)
        
        jd.raw_text = description_text
        return self._parse_text(description_text, jd)
    
    def _parse_generic(self, soup: BeautifulSoup, url: str) -> JobDescription:
        """Parse generic company career page."""
        # Extract main content
        main_content = soup.find('main') or soup.find('article') or soup.find('body')
        if main_content:
            text = main_content.get_text(separator='\n', strip=True)
        else:
            text = soup.get_text(separator='\n', strip=True)
        
        jd = JobDescription(role_title="", raw_text=text)
        
        # Try to extract title from h1
        h1 = soup.find('h1')
        if h1:
            jd.role_title = h1.get_text(strip=True)
        
        return self._parse_text(text, jd)
    
    def _parse_text_with_llm(self, text: str) -> JobDescription:
        """Parse job description using LLM with Match-Focused Framework."""
        print("  Using LLM for JD parsing (Match-Focused Framework)...")
        
        # Limit text to avoid token issues
        text_limited = text[:8000] if len(text) > 8000 else text
        
        prompt = f"""Analyze this job description using a Match-Focused Framework for resume tailoring.

JOB DESCRIPTION:
{text_limited}

Extract the following information and return as JSON:
{{
    "role_title": "The job title (e.g., 'Senior Product Manager')",
    "role_summary": "A brief 1-2 sentence summary capturing the essence of this role - what makes it unique, the core mission, and key focus areas. Write it as if describing to a job seeker what this role is really about.",
    "company": "Company name if mentioned, or null",
    "location": "Location/remote status if mentioned, or null",
    "experience_level": "Experience level required (e.g., '5+ years', 'Senior', 'Mid-level', 'Entry-level')",
    "team_scope": "Team/reporting context (e.g., 'Reports to VP of Product', 'Leads team of 5', 'Cross-functional role')",
    "industry_domain": "Industry or domain focus (e.g., 'B2B SaaS', 'Healthcare Tech', 'E-commerce', 'AI/ML')",
    
    "must_have_requirements": ["CRITICAL requirements - deal breakers that candidate MUST address in resume. Include years of experience, required degrees, certifications, must-have experience"],
    "nice_to_have_requirements": ["BONUS requirements - nice-to-have items that strengthen the application"],
    
    "technical_skills": ["Technical/hard skills: programming languages, tools, technologies, platforms, methodologies (e.g., Python, AWS, SQL, Agile, Jira)"],
    "soft_skills": ["Soft skills mentioned: leadership, communication, collaboration, problem-solving, stakeholder management"],
    
    "keywords_to_include": ["Important keywords and phrases to include in resume for ATS optimization - extract key terms that appear multiple times or are emphasized"],
    
    "responsibilities": ["Key responsibilities/duties - what the person will DO daily"]
}}

EXTRACTION RULES:
1. must_have_requirements: Look for words like "required", "must have", "minimum", "essential", "X+ years"
2. nice_to_have_requirements: Look for "preferred", "nice to have", "bonus", "plus", "ideally"
3. technical_skills: Specific technologies, tools, platforms, languages, frameworks
4. soft_skills: Leadership, communication, collaboration, stakeholder management, problem-solving
5. keywords_to_include: Terms that appear frequently, are in bold, or are clearly emphasized
6. experience_level: Look for "X+ years", "senior", "junior", "lead", "principal", "staff"
7. industry_domain: Look for industry mentions like SaaS, healthcare, fintech, B2B, enterprise

Be thorough - extract ALL relevant items. If a field is not found, use null for strings or [] for arrays.

Return ONLY the JSON object, no other text."""

        messages = [
            {"role": "system", "content": "You are an expert job description parser. Extract structured information accurately and completely. Return only valid JSON."},
            {"role": "user", "content": prompt}
        ]
        
        try:
            response_text = generate_chat_completion(messages, model='grok-4-fast', json_mode=True)
            
            if not response_text:
                print("  ✗ Empty response from LLM, falling back to regex")
                return None
            
            # Clean response
            response_text = response_text.strip()
            if response_text.startswith('```json'):
                response_text = response_text[7:]
            if response_text.startswith('```'):
                response_text = response_text[3:]
            if response_text.endswith('```'):
                response_text = response_text[:-3]
            response_text = response_text.strip()
            
            # Parse JSON
            data = json.loads(response_text)
            
            # Create JobDescription object with new Match-Focused fields
            jd = JobDescription(
                # Role Summary
                role_title=data.get('role_title', 'Job Position') or 'Job Position',
                role_summary=data.get('role_summary'),
                company=data.get('company'),
                location=data.get('location'),
                experience_level=data.get('experience_level'),
                team_scope=data.get('team_scope'),
                industry_domain=data.get('industry_domain'),
                
                # New Match-Focused fields
                must_have_requirements=data.get('must_have_requirements', []) or [],
                nice_to_have_requirements=data.get('nice_to_have_requirements', []) or [],
                technical_skills=data.get('technical_skills', []) or [],
                soft_skills=data.get('soft_skills', []) or [],
                keywords_to_include=data.get('keywords_to_include', []) or [],
                
                # Legacy fields (populated for backward compatibility)
                responsibilities=data.get('responsibilities', []) or [],
                requirements=data.get('must_have_requirements', []) or [],  # Map to must_have
                preferred_qualifications=data.get('nice_to_have_requirements', []) or [],  # Map to nice_to_have
                required_skills=data.get('technical_skills', []) or [],  # Map to technical
                preferred_skills=data.get('soft_skills', []) or [],  # Map soft skills here for display
                keywords=data.get('keywords_to_include', []) or [],
                raw_text=text
            )
            
            print(f"  ✓ LLM extracted:")
            print(f"    - Experience: {jd.experience_level or 'N/A'} | Domain: {jd.industry_domain or 'N/A'}")
            print(f"    - Must-Have: {len(jd.must_have_requirements)} | Nice-to-Have: {len(jd.nice_to_have_requirements)}")
            print(f"    - Technical Skills: {len(jd.technical_skills)} | Soft Skills: {len(jd.soft_skills)}")
            print(f"    - Keywords: {len(jd.keywords_to_include)} | Responsibilities: {len(jd.responsibilities)}")
            return jd
            
        except json.JSONDecodeError as e:
            print(f"  ✗ JSON parse error: {e}")
            print(f"  Response preview: {response_text[:300] if response_text else 'N/A'}")
            return None
        except Exception as e:
            print(f"  ✗ LLM parsing error: {e}")
            return None
    
    def _parse_text(self, text: str, jd: Optional[JobDescription] = None) -> JobDescription:
        """Parse raw text to extract structured job description.
        
        Note: The raw_text field is preserved and used directly by AI for suggestions.
        Uses LLM for accurate parsing when available.
        """
        if not text or not text.strip():
            raise ValueError("Job description text is empty")
        
        # Try LLM parsing first (more accurate)
        if self.use_llm:
            llm_result = self._parse_text_with_llm(text)
            if llm_result:
                return llm_result
            print("  Falling back to regex parsing...")
        
        # Fallback to regex parsing
        if jd is None:
            jd = JobDescription(role_title="", raw_text=text)
        else:
            # Ensure raw_text is always set
            if not jd.raw_text:
                jd.raw_text = text
        
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        
        if not lines:
            raise ValueError("No content found in job description")
        
        # Extract role title if not set - improved logic
        if not jd.role_title and lines:
            # Common patterns that indicate NOT a job title
            not_title_patterns = [
                r'^(we are|about|welcome|join|looking for|seeking)',
                r'^(the|our|this|a|an)\s+',
                r'company|corporation|inc\.|llc',
                r'^http',
                r'^\d+',
            ]
            
            # Job title indicators
            title_keywords = [
                'engineer', 'developer', 'manager', 'analyst', 'specialist', 
                'director', 'lead', 'architect', 'consultant', 'coordinator',
                'administrator', 'executive', 'officer', 'associate', 'assistant',
                'designer', 'scientist', 'researcher', 'programmer', 'technician'
            ]
            
            # Try to find title in first few lines
            for i, line in enumerate(lines[:10]):
                line_lower = line.lower().strip()
                
                # Skip if it matches "not title" patterns
                if any(re.search(pattern, line_lower) for pattern in not_title_patterns):
                    continue
                
                # Skip very long lines (likely descriptions)
                if len(line) > 80:
                    continue
                
                # Skip lines that are all caps (often headers/company names)
                if line.isupper() and len(line) > 15:
                    continue
                
                # Good candidate if it contains job title keywords
                if any(keyword in line_lower for keyword in title_keywords):
                    # Additional check: should be reasonably short
                    if len(line.split()) <= 8:
                        jd.role_title = line.strip()
                        break
                
                # If first line is short and doesn't match exclusion patterns, might be title
                if i == 0 and len(line.split()) <= 6 and len(line) < 60:
                    # Double check it's not a greeting
                    if not any(greeting in line_lower for greeting in ['we', 'welcome', 'about', 'join']):
                        jd.role_title = line.strip()
                        break
            
            # If still no title, try looking for patterns like "Position: Title" or "Role: Title"
            if not jd.role_title or jd.role_title == "Job Position":
                for line in lines[:15]:
                    # Look for patterns like "Position:", "Role:", "Title:", "Job:"
                    match = re.search(r'(?:position|role|title|job|opening)[:\-]\s*(.+?)(?:\n|$)', line, re.IGNORECASE)
                    if match:
                        potential_title = match.group(1).strip()
                        if len(potential_title.split()) <= 8 and len(potential_title) < 80:
                            jd.role_title = potential_title
                            break
                
                # Last resort: use first reasonable line
                if not jd.role_title or jd.role_title == "Job Position":
                    for line in lines[:5]:
                        line = line.strip()
                        # Must be short, not a greeting, and contain at least one job-related word
                        if (len(line.split()) <= 6 and len(line) < 60 and 
                            not any(greeting in line.lower() for greeting in ['we', 'welcome', 'about', 'join', 'the', 'our']) and
                            (any(word in line.lower() for word in title_keywords) or len(line.split()) <= 3)):
                            jd.role_title = line
                            break
                    
                    # Final fallback
                    if not jd.role_title or jd.role_title == "Job Position":
                        jd.role_title = "Job Position"
        
        # Extract responsibilities - try multiple approaches
        jd.responsibilities = self._extract_section(text, [
            'responsibilities', 'what you will do', 'key responsibilities',
            'duties', 'what you\'ll do', 'you will', 'you\'ll be responsible',
            'key duties', 'main responsibilities', 'role', 'about the role',
            'what you\'ll be doing', 'you\'ll', 'you will be'
        ])
        
        # If no responsibilities found, try extracting from common patterns
        if not jd.responsibilities:
            jd.responsibilities = self._extract_by_patterns(text, [
                r'(?:you will|you\'ll|responsibilities include|duties include|you\'ll be|you will be)[:\s]*(.+?)(?=\n\s*\n|\n(?:requirements|qualifications|skills|$))',
            ])
        
        # Aggressive fallback: extract action-oriented bullet points as responsibilities
        if len(jd.responsibilities) < 3:
            all_bullets = self._extract_all_bullet_points(text)
            # Filter for responsibility-like content (action verbs, tasks)
            responsibility_bullets = [
                b for b in all_bullets 
                if any(verb in b.lower() for verb in ['lead', 'develop', 'manage', 'create', 'design', 'build', 'drive', 'collaborate', 'work', 'implement', 'deliver', 'own', 'execute'])
                and len(b) > 20  # Meaningful length
                and b not in jd.requirements  # Don't duplicate requirements
            ]
            if responsibility_bullets:
                jd.responsibilities.extend(responsibility_bullets[:10])  # Add up to 10 more
                jd.responsibilities = list(dict.fromkeys(jd.responsibilities))  # Remove duplicates
        
        # Extract requirements
        jd.requirements = self._extract_section(text, [
            'requirements', 'qualifications', 'required qualifications',
            'must have', 'required', 'minimum requirements', 'we require',
            'you must have', 'you need', 'essential', 'mandatory', 'what we need',
            'candidates must', 'candidate must', 'you should have'
        ])
        
        # If no requirements found, try extracting bullet points that look like requirements
        if not jd.requirements:
            jd.requirements = self._extract_bullet_points(text, keywords=['experience', 'years', 'degree', 'bachelor', 'master', 'proven', 'ability', 'skill', 'knowledge', 'familiar'])
        
        # Aggressive fallback: extract ALL meaningful bullet points as requirements
        if len(jd.requirements) < 3:
            all_bullets = self._extract_all_bullet_points(text)
            # Filter for requirement-like content
            requirement_bullets = [
                b for b in all_bullets 
                if any(kw in b.lower() for kw in ['experience', 'years', 'degree', 'bachelor', 'master', 'skill', 'knowledge', 'ability', 'proven', 'demonstrated', 'required', 'must'])
                and len(b) > 20  # Meaningful length
            ]
            if requirement_bullets:
                jd.requirements.extend(requirement_bullets[:10])  # Add up to 10 more
                jd.requirements = list(dict.fromkeys(jd.requirements))  # Remove duplicates
        
        # Extract preferred qualifications
        jd.preferred_qualifications = self._extract_section(text, [
            'preferred', 'nice to have', 'preferred qualifications',
            'bonus', 'pluses', 'desired', 'would be nice'
        ])
        
        # Extract skills - try to find skills section first
        skills_section = self._extract_section(text, [
            'skills', 'technical skills', 'competencies', 'technologies', 'technologies we use',
            'required skills', 'preferred skills', 'qualifications', 'tools', 'software'
        ], return_text=True)
        
        if skills_section:
            jd.required_skills, jd.preferred_skills = self._extract_skills_from_text(skills_section)
        else:
            # Extract skills from entire text
            jd.required_skills, jd.preferred_skills = self._extract_skills_from_text(text)
        
        # If no skills found, try extracting from requirements section
        if not jd.required_skills and not jd.preferred_skills:
            req_text = ' '.join(jd.requirements)
            if req_text:
                jd.required_skills, jd.preferred_skills = self._extract_skills_from_text(req_text)
        
        # Aggressive fallback: extract skills from all bullet points
        if len(jd.required_skills) < 3:
            all_bullets = self._extract_all_bullet_points(text)
            bullet_text = ' '.join(all_bullets)
            if bullet_text:
                additional_required, additional_preferred = self._extract_skills_from_text(bullet_text)
                # Merge without duplicates
                for skill in additional_required:
                    if skill not in jd.required_skills:
                        jd.required_skills.append(skill)
                for skill in additional_preferred:
                    if skill not in jd.preferred_skills:
                        jd.preferred_skills.append(skill)
        
        # Extract keywords (common tech terms, methodologies, etc.)
        jd.keywords = self._extract_keywords(text)
        
        return jd
    
    def _extract_section(self, text: str, keywords: List[str], return_text: bool = False):
        """Extract bullet points from a section identified by keywords.
        
        Returns:
            List[str] if return_text=False, str if return_text=True
        """
        text_lower = text.lower()
        items = []
        
        for keyword in keywords:
            # More flexible pattern - look for keyword followed by content
            # Try multiple patterns
            patterns = [
                rf'(?i){re.escape(keyword)}[:\s]*\n(.+?)(?=\n\s*\n|\n[A-Z][^:]+:|\Z)',  # Keyword: followed by content
                rf'(?i){re.escape(keyword)}[:\s]+(.+?)(?=\n\s*\n[A-Z]|\Z)',  # Keyword: content (no newline after colon)
                rf'(?i){re.escape(keyword)}\s*\n(.+?)(?=\n\s*\n|\n[A-Z][a-z]+:|\Z)',  # Keyword\ncontent
            ]
            
            for pattern in patterns:
                match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
                if match:
                    section_text = match.group(1).strip()
                    if return_text:
                        return section_text
                    
                    # Extract bullet points - try multiple formats
                    # Split by bullet markers
                    bullets = re.split(r'\n(?=[•\-\*●▪▫]\s|\d+[\.\)]\s|[-]\s)', section_text)
                    
                    # Also try splitting by lines that look like bullets
                    if len(bullets) == 1 or (len(bullets) == 1 and bullets[0] == section_text):
                        # Try splitting by lines that start with common bullet patterns
                        lines = section_text.split('\n')
                        bullets = []
                        for line in lines:
                            line = line.strip()
                            if line and (line.startswith(('•', '-', '*', '●')) or 
                                       re.match(r'^\d+[\.\)]\s', line) or
                                       (len(line) > 20 and not line.endswith(':'))):
                                bullets.append(line)
                    
                    for bullet in bullets:
                        # Clean up bullet markers
                        bullet = re.sub(r'^[•\-\*●▪▫]\s+', '', bullet)
                        bullet = re.sub(r'^\d+[\.\)]\s+', '', bullet)
                        bullet = re.sub(r'^[-]\s+', '', bullet)
                        bullet = bullet.strip()
                        # Normalize whitespace
                        bullet = re.sub(r'\s+', ' ', bullet)
                        # Remove trailing ellipsis
                        bullet = re.sub(r'\.\.\.+$', '', bullet).strip()
                        # Only keep complete sentences or reasonably long items
                        if bullet and len(bullet) > 15:
                            # Prefer complete sentences (end with punctuation) or long items
                            if bullet[-1] in '.!?' or len(bullet) > 40:
                                items.append(bullet)
                    
                    if items:  # If we found items, return them
                        break
                
                if items:
                    break
        
        return items
    
    def _extract_by_patterns(self, text: str, patterns: List[str]) -> List[str]:
        """Extract items using regex patterns."""
        items = []
        for pattern in patterns:
            matches = re.finditer(pattern, text, re.DOTALL | re.IGNORECASE)
            for match in matches:
                content = match.group(1).strip()
                # Split by newlines or bullets
                lines = re.split(r'\n|•|[-*]', content)
                for line in lines:
                    line = line.strip()
                    if line and len(line) > 10:
                        items.append(line)
                if items:
                    break
            if items:
                break
        return items[:10]  # Limit to 10 items
    
    def _extract_bullet_points(self, text: str, keywords: List[str] = None) -> List[str]:
        """Extract bullet points that might be requirements."""
        items = []
        # Find all bullet points - multiple patterns
        patterns = [
            r'[•\-\*●▪▫]\s*([^\n•\-\*●▪▫]+)',  # Standard bullets
            r'^\s*[-]\s+([^\n]+)',  # Dash bullets (line start)
            r'^\s*\d+[\.\)]\s+([^\n]+)',  # Numbered lists
        ]
        
        for pattern in patterns:
            bullets = re.findall(pattern, text, re.MULTILINE)
            for bullet in bullets:
                bullet = bullet.strip()
                if len(bullet) > 15:  # Meaningful length
                    # If keywords provided, check if bullet contains them
                    if keywords:
                        bullet_lower = bullet.lower()
                        if any(kw.lower() in bullet_lower for kw in keywords):
                            items.append(bullet)
                    else:
                        items.append(bullet)
        
        return items[:15]  # Limit to 15 items
    
    def _extract_all_bullet_points(self, text: str) -> List[str]:
        """Extract ALL bullet points from text, regardless of context."""
        items = []
        # Multiple patterns to catch different formats
        patterns = [
            r'[•\-\*●▪▫]\s*([^\n•\-\*●▪▫]{30,}?)(?=\n[•\-\*●▪▫]|\n\s*\n|\n\d+[\.\)]|\Z)',  # Standard bullets (non-greedy, stop at next bullet)
            r'^\s*[-]\s+([^\n]{30,}?)(?=\n\s*[-]|\n\s*\n|\Z)',  # Dash bullets
            r'^\s*\d+[\.\)]\s+([^\n]{30,}?)(?=\n\s*\d+[\.\)]|\n\s*\n|\Z)',  # Numbered lists
        ]
        
        for pattern in patterns:
            bullets = re.findall(pattern, text, re.MULTILINE | re.DOTALL)
            for bullet in bullets:
                bullet = bullet.strip()
                # Clean up common prefixes and trailing whitespace
                bullet = re.sub(r'^[•\-\*●▪▫]\s*', '', bullet)
                bullet = re.sub(r'^\d+[\.\)]\s+', '', bullet)
                bullet = re.sub(r'\s+', ' ', bullet)  # Normalize whitespace
                # Only keep complete sentences (ends with punctuation) or reasonably long items
                if len(bullet) > 30 and (bullet[-1] in '.!?' or len(bullet) > 50):
                    # Remove trailing ellipsis
                    bullet = re.sub(r'\.\.\.+$', '', bullet).strip()
                    if len(bullet) > 30:
                        items.append(bullet)
        
        # Remove duplicates and similar items while preserving order
        seen = set()
        unique_items = []
        for item in items:
            item_lower = item.lower().strip()
            # Check for duplicates and very similar items (80% similarity)
            is_duplicate = False
            for seen_item in seen:
                # Simple similarity check - if one contains the other (80% overlap)
                shorter = min(len(item_lower), len(seen_item))
                longer = max(len(item_lower), len(seen_item))
                if shorter > 0 and longer > 0:
                    # Check if shorter is mostly contained in longer
                    if item_lower in seen_item or seen_item in item_lower:
                        if shorter / longer > 0.8:
                            is_duplicate = True
                            break
            
            if not is_duplicate and len(item_lower) > 30:
                seen.add(item_lower)
                unique_items.append(item)
        
        return unique_items[:30]  # Return up to 30 items
    
    def _extract_skills_from_text(self, text: str) -> Tuple[List[str], List[str]]:
        """Extract required and preferred skills from text."""
        required_skills = []
        preferred_skills = []
        
        # Expanded list of technical skills patterns (case-insensitive matching)
        skill_keywords = [
            # Programming languages
            'python', 'java', 'javascript', 'typescript', 'c++', 'c#', 'go', 'rust', 'ruby', 'php', 'swift', 'kotlin',
            # Frontend
            'react', 'angular', 'vue', 'vue.js', 'next.js', 'nuxt', 'svelte', 'jquery', 'html', 'css', 'sass', 'less',
            # Backend frameworks
            'node.js', 'nodejs', 'django', 'flask', 'fastapi', 'spring', 'express', 'nest.js', 'laravel', 'rails',
            # Databases
            'sql', 'postgresql', 'mysql', 'mongodb', 'redis', 'cassandra', 'elasticsearch', 'dynamodb', 'oracle',
            # Cloud & DevOps
            'aws', 'azure', 'gcp', 'google cloud', 'docker', 'kubernetes', 'k8s', 'terraform', 'ansible', 'jenkins',
            'git', 'ci/cd', 'github actions', 'gitlab', 'circleci', 'travis ci',
            # ML/AI
            'machine learning', 'ml', 'ai', 'artificial intelligence', 'deep learning', 'tensorflow', 'pytorch', 'keras',
            'scikit-learn', 'pandas', 'numpy', 'data science',
            # Other
            'agile', 'scrum', 'kanban', 'devops', 'microservices', 'rest api', 'graphql', 'gRPC',
            # Tools
            'jira', 'confluence', 'slack', 'figma', 'adobe', 'photoshop', 'illustrator'
        ]
        
        text_lower = text.lower()
        
        # Extract skills with better matching
        for skill in skill_keywords:
            skill_lower = skill.lower()
            # Use word boundaries to avoid partial matches
            pattern = r'\b' + re.escape(skill_lower) + r'\b'
            if re.search(pattern, text_lower):
                # Check if it's in preferred section
                skill_context = self._get_context_around(text_lower, skill_lower, 300)
                context_lower = skill_context.lower()
                
                # Check for preferred indicators
                is_preferred = any(word in context_lower for word in [
                    'preferred', 'nice to have', 'nice-to-have', 'bonus', 'plus', 
                    'would be nice', 'optional', 'desired but not required'
                ])
                
                # Check for required indicators
                is_required = any(word in context_lower for word in [
                    'required', 'must have', 'must-have', 'essential', 'mandatory', 
                    'need', 'needed', 'requirement'
                ])
                
                # Normalize skill name
                if skill.lower() == 'ai':
                    skill_title = 'AI'
                elif skill.lower() == 'ml':
                    skill_title = 'Machine Learning'
                elif '/' in skill:
                    # Handle cases like "AI/ML" - split and add both
                    parts = [p.strip().title() for p in skill.split('/')]
                    skill_title = '/'.join(parts)
                else:
                    skill_title = skill.title() if skill.islower() else skill
                
                if is_preferred and not is_required:
                    if skill_title not in preferred_skills:
                        preferred_skills.append(skill_title)
                else:
                    if skill_title not in required_skills:
                        required_skills.append(skill_title)
        
        # Also extract skills mentioned as bullet points or in lists
        bullets = re.findall(r'[•\-\*●▪▫]\s*([^•\-\*●▪▫\n]+)', text)
        for bullet in bullets:
            bullet_lower = bullet.lower()
            for skill in skill_keywords:
                skill_lower = skill.lower()
                pattern = r'\b' + re.escape(skill_lower) + r'\b'
                if re.search(pattern, bullet_lower):
                    skill_title = skill.title() if skill.islower() else skill
                    if skill_title not in required_skills and skill_title not in preferred_skills:
                        if any(word in bullet_lower for word in ['preferred', 'nice', 'bonus', 'optional']):
                            preferred_skills.append(skill_title)
                        else:
                            required_skills.append(skill_title)
        
        # Remove duplicates and sort
        return sorted(list(set(required_skills))), sorted(list(set(preferred_skills)))
    
    def _extract_keywords(self, text: str) -> List[str]:
        """Extract important keywords from job description."""
        keywords = []
        text_lower = text.lower()
        
        # Common keywords to look for
        keyword_patterns = [
            r'\b\d+\+?\s*years?\b',  # Experience years
            r'\b(bachelor|master|phd|degree)\b',  # Education
            r'\b(remote|hybrid|onsite|full-time|part-time|contract)\b',  # Work type
            r'\b(lead|senior|junior|mid-level|entry)\b',  # Level
        ]
        
        for pattern in keyword_patterns:
            matches = re.findall(pattern, text_lower)
            keywords.extend(matches)
        
        # Extract capitalized phrases (often important terms)
        capitalized = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', text)
        keywords.extend([kw for kw in capitalized if len(kw) > 3 and kw not in ['The', 'This', 'That', 'With', 'From']])
        
        return list(set(keywords))[:50]  # Limit to 50 keywords
    
    def _get_context_around(self, text: str, keyword: str, chars: int) -> str:
        """Get context around a keyword."""
        index = text.lower().find(keyword.lower())
        if index == -1:
            return ""
        start = max(0, index - chars)
        end = min(len(text), index + len(keyword) + chars)
        return text[start:end]


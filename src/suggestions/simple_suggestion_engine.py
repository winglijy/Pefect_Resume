"""
Enhanced suggestion engine with actionable frameworks and priority ranking.
"""
import json
import uuid
from typing import List, Dict, Optional
from ..models.schemas import ResumeData, JobDescription, Suggestion
from ..config import generate_chat_completion


class SimpleSuggestionEngine:
    """Enhanced suggestion engine with actionable frameworks."""
    
    def generate_suggestions(
        self,
        resume: ResumeData,
        jd: JobDescription,
        max_suggestions: int = 12,
        feedback: Optional[str] = None
    ) -> Dict:
        """
        Generate prioritized, grouped suggestions.
        
        Returns dict with:
        - summary: Quick overview of improvements
        - suggestions: List of Suggestion objects with priority and category
        """
        print(f"\n=== Generating Suggestions (Enhanced) ===")
        print(f"Resume: {len(resume.experience)} experiences, {len(resume.skills)} skills")
        print(f"JD: {jd.role_title}")
        if feedback:
            print(f"User feedback: {feedback[:100]}...")
        
        # Prepare resume summary
        resume_summary = self._prepare_resume_summary(resume)
        
        # Get JD text - prefer structured data
        jd_text = self._prepare_jd_for_matching(jd)
        
        # Limit lengths
        jd_text = jd_text[:6000] if len(jd_text) > 6000 else jd_text
        
        # Build the enhanced prompt
        prompt = self._build_enhanced_prompt(resume_summary, jd_text, max_suggestions, feedback)
        
        messages = [
            {
                "role": "system",
                "content": """You are an expert resume consultant who helps candidates tailor their resumes to specific job descriptions.

Your expertise includes:
- STAR method (Situation, Task, Action, Result) for impactful bullet points
- ATS optimization and keyword matching
- Quantifying achievements with metrics
- Highlighting transferable skills
- Strategic positioning of experience

Always provide specific, actionable suggestions that can be immediately applied."""
            },
            {"role": "user", "content": prompt}
        ]
        
        try:
            print("Calling API with enhanced prompt...")
            response_text = generate_chat_completion(messages, model='grok-4-fast', json_mode=True)
            
            if not response_text:
                print("✗ Empty response from API")
                return {"summary": None, "suggestions": []}
            
            # Clean and parse response
            response_data = self._parse_response(response_text)
            
            if not response_data:
                return {"summary": None, "suggestions": []}
            
            # Extract summary
            summary = response_data.get('summary', '')
            
            # Process suggestions
            suggestions = self._process_suggestions(response_data.get('suggestions', []))
            
            # Sort by priority
            priority_order = {'high': 0, 'medium': 1, 'low': 2}
            suggestions.sort(key=lambda s: (priority_order.get(getattr(s, 'priority', 'medium'), 1), -s.expected_score_delta))
            
            print(f"✓ Generated {len(suggestions)} suggestions")
            return {
                "summary": summary,
                "suggestions": suggestions[:max_suggestions]
            }
            
        except Exception as e:
            print(f"✗ Error: {e}")
            import traceback
            traceback.print_exc()
            return {"summary": None, "suggestions": []}
    
    def refine_suggestion(
        self,
        original_suggestion: Suggestion,
        user_feedback: str,
        resume: ResumeData,
        jd: JobDescription
    ) -> Optional[Suggestion]:
        """
        Refine a single suggestion based on user feedback.
        """
        print(f"\n=== Refining Suggestion ===")
        print(f"Feedback: {user_feedback[:100]}...")
        
        prompt = f"""A user wants to refine a resume suggestion based on their feedback.

ORIGINAL TEXT:
{original_suggestion.original_text}

CURRENT SUGGESTION:
{original_suggestion.suggested_text}

REASON FOR SUGGESTION:
{original_suggestion.reason}

USER FEEDBACK:
{user_feedback}

JOB REQUIREMENTS CONTEXT:
{original_suggestion.jd_mapping or 'General improvement'}

Please provide a refined suggestion that:
1. Addresses the user's feedback
2. Maintains the improvement for JD match
3. Sounds natural and authentic to the candidate's experience

Return JSON:
{{
    "suggested_text": "The refined suggestion incorporating user feedback",
    "reason": "Updated explanation of why this version works better"
}}"""

        messages = [
            {"role": "system", "content": "You are an expert resume writer. Refine suggestions based on user feedback while maintaining ATS optimization."},
            {"role": "user", "content": prompt}
        ]
        
        try:
            response_text = generate_chat_completion(messages, model='grok-4-fast', json_mode=True)
            
            if not response_text:
                return None
            
            data = self._parse_response(response_text)
            if not data:
                return None
            
            # Create refined suggestion
            refined = Suggestion(
                id=str(uuid.uuid4()),
                section_type=original_suggestion.section_type,
                section_id=original_suggestion.section_id,
                original_text=original_suggestion.original_text,
                suggested_text=data.get('suggested_text', original_suggestion.suggested_text),
                reason=data.get('reason', original_suggestion.reason),
                expected_score_delta=original_suggestion.expected_score_delta,
                jd_mapping=original_suggestion.jd_mapping
            )
            
            # Preserve category and priority
            refined.category = getattr(original_suggestion, 'category', 'experience')
            refined.priority = getattr(original_suggestion, 'priority', 'medium')
            
            return refined
            
        except Exception as e:
            print(f"✗ Error refining: {e}")
            return None
    
    def _build_enhanced_prompt(
        self,
        resume_summary: str,
        jd_text: str,
        max_suggestions: int,
        feedback: Optional[str]
    ) -> str:
        """Build the enhanced prompt with actionable framework."""
        
        feedback_section = ""
        if feedback:
            feedback_section = f"""
PREVIOUS FEEDBACK FROM USER:
{feedback}
Please incorporate this feedback into your suggestions.
"""
        
        return f"""Analyze this resume against the job description and provide {max_suggestions} concise, actionable suggestions.

JOB DESCRIPTION:
{jd_text}

RESUME:
{resume_summary}
{feedback_section}
CRITICAL PRINCIPLES:

1. **STAY TRUE TO THEIR EXPERIENCE**
   - Only enhance what they ACTUALLY did - never invent new achievements
   - Use their existing metrics, just highlight them better
   - If they managed a team, keep it. If they didn't, don't add it.
   - Rephrase to emphasize JD-relevant aspects of their REAL work

2. **KEEP IT CONCISE**
   - Each bullet should be 1-2 lines MAX (under 25 words ideal)
   - Remove filler words: "Responsible for", "Helped to", "Worked on"
   - Start with strong action verbs: Led, Drove, Launched, Built, Optimized
   - One clear achievement per bullet, not multiple

3. **ENHANCE, DON'T FABRICATE**
   GOOD: "Managed product roadmap" → "Drove product roadmap for 3 B2B features, aligning with enterprise customer needs"
   BAD: "Managed product roadmap" → "Led cross-functional team of 15 to deliver $5M revenue" (if not mentioned)

4. **MIRROR JD LANGUAGE**
   - Use exact keywords from JD (e.g., "stakeholder management" not "working with people")
   - Match their terminology for skills and tools

SUGGESTION TYPES:
- **EXPERIENCE**: Rewrite bullets to be concise + JD-aligned (MOST IMPORTANT)
- **SUMMARY**: Tighten and add 1-2 key JD keywords
- **SKILLS**: Add JD skills they likely have based on experience

PRIORITY:
- HIGH: Their experience matches JD but wording doesn't show it
- MEDIUM: Could add JD keywords naturally
- LOW: Minor polish

Return JSON:
{{
    "summary": "2-3 sentences: What are the TOP 3 quick wins to improve match? Be specific about which experience to highlight.",
    "suggestions": [
        {{
            "category": "experience|summary|skills",
            "priority": "high|medium|low",
            "section_type": "bullet|summary|skill",
            "section_id": "experience_0_bullet_1",
            "original_text": "EXACT text from resume (one bullet only, keep it short)",
            "suggested_text": "Concise improved version (MAX 25 words, same core achievement)",
            "reason": "Brief: why this helps + which JD requirement",
            "expected_score_delta": 3.0,
            "jd_mapping": "Specific JD requirement addressed"
        }}
    ]
}}

RULES:
1. suggested_text must be SHORTER or same length as original (never longer)
2. Keep the SAME core achievement, just reframe for JD
3. Focus 70% of suggestions on EXPERIENCE bullets
4. Reason should be 1 sentence max"""
    
    def _prepare_resume_summary(self, resume: ResumeData) -> str:
        """Prepare a clean summary of the resume."""
        parts = []
        
        if resume.summary:
            parts.append(f"=== SUMMARY ===\n{resume.summary}\n")
        
        parts.append("=== EXPERIENCE ===")
        for i, exp in enumerate(resume.experience[:5]):
            parts.append(f"\n[{i}] {exp.title} at {exp.company}")
            if exp.start_date:
                parts.append(f"    ({exp.start_date} - {exp.end_date or 'Present'})")
            for j, bullet in enumerate(exp.bullets):
                parts.append(f"    [{i}_bullet_{j}] {bullet.text}")
        
        if resume.skills:
            parts.append(f"\n=== SKILLS ===\n{', '.join(resume.skills[:30])}")
        
        if resume.education:
            parts.append("\n=== EDUCATION ===")
            for edu in resume.education[:3]:
                parts.append(f"  • {edu.degree} - {edu.institution}")
        
        return "\n".join(parts)
    
    def _prepare_jd_for_matching(self, jd: JobDescription) -> str:
        """Prepare JD with structured data for better matching."""
        parts = [f"ROLE: {jd.role_title}"]
        
        if jd.company:
            parts.append(f"COMPANY: {jd.company}")
        
        if jd.role_summary:
            parts.append(f"\nROLE SUMMARY: {jd.role_summary}")
        
        # Use new Match-Focused fields if available
        must_have = jd.must_have_requirements if jd.must_have_requirements else jd.requirements
        nice_to_have = jd.nice_to_have_requirements if jd.nice_to_have_requirements else jd.preferred_qualifications
        
        if must_have:
            parts.append(f"\n🚨 MUST-HAVE REQUIREMENTS:")
            parts.extend([f"  • {r}" for r in must_have[:10]])
        
        if nice_to_have:
            parts.append(f"\n⭐ NICE-TO-HAVE:")
            parts.extend([f"  • r" for r in nice_to_have[:8]])
        
        tech_skills = jd.technical_skills if jd.technical_skills else jd.required_skills
        if tech_skills:
            parts.append(f"\n🔧 TECHNICAL SKILLS: {', '.join(tech_skills[:15])}")
        
        if jd.soft_skills:
            parts.append(f"\n💬 SOFT SKILLS: {', '.join(jd.soft_skills[:10])}")
        
        keywords = jd.keywords_to_include if jd.keywords_to_include else jd.keywords
        if keywords:
            parts.append(f"\n🔑 KEY TERMS: {', '.join(keywords[:15])}")
        
        if jd.responsibilities:
            parts.append(f"\n📝 RESPONSIBILITIES:")
            parts.extend([f"  • {r}" for r in jd.responsibilities[:8]])
        
        return "\n".join(parts)
    
    def _parse_response(self, response_text: str) -> Optional[Dict]:
        """Parse and clean API response."""
        response_text = response_text.strip()
        
        # Remove markdown code blocks
        if response_text.startswith('```json'):
            response_text = response_text[7:]
        if response_text.startswith('```'):
            response_text = response_text[3:]
        if response_text.endswith('```'):
            response_text = response_text[:-3]
        response_text = response_text.strip()
        
        try:
            return json.loads(response_text)
        except json.JSONDecodeError as e:
            print(f"✗ JSON parse error: {e}")
            # Try to extract JSON
            import re
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                try:
                    return json.loads(json_match.group(0))
                except:
                    pass
            return None
    
    def _process_suggestions(self, suggestions_list: List[Dict]) -> List[Suggestion]:
        """Process raw suggestion data into Suggestion objects."""
        suggestions = []
        seen_originals = set()  # Track seen original texts to prevent duplicates
        
        for i, sug_data in enumerate(suggestions_list):
            if not isinstance(sug_data, dict):
                continue
            
            original = sug_data.get('original_text', '').strip()
            suggested = sug_data.get('suggested_text', '').strip()
            
            if not original or not suggested or original == suggested:
                continue
            
            # Check for duplicates - normalize original text for comparison
            original_normalized = original.lower().strip()[:100]  # Use first 100 chars for comparison
            if original_normalized in seen_originals:
                print(f"  ⚠ Skipping duplicate suggestion: {original[:50]}...")
                continue
            seen_originals.add(original_normalized)
            
            # Limit length
            if len(original) > 500:
                original = original[:500] + "..."
            if len(suggested) > 500:
                suggested = suggested[:500] + "..."
            
            try:
                suggestion = Suggestion(
                    id=str(uuid.uuid4()),
                    section_type=sug_data.get('section_type', 'bullet'),
                    section_id=sug_data.get('section_id', 'unknown'),
                    original_text=original,
                    suggested_text=suggested,
                    reason=sug_data.get('reason', 'Improves match to job description'),
                    expected_score_delta=float(sug_data.get('expected_score_delta', 2.0)),
                    jd_mapping=sug_data.get('jd_mapping', '')
                )
                
                # Add extra attributes for grouping/priority
                suggestion.category = sug_data.get('category', 'experience')
                suggestion.priority = sug_data.get('priority', 'medium')
                
                suggestions.append(suggestion)
                print(f"  ✓ [{suggestion.priority.upper()}] {suggestion.category}: {original[:50]}...")
                
            except Exception as e:
                print(f"  ✗ Suggestion {i+1}: Error - {e}")
                continue
        
        return suggestions

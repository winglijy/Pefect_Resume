import json
import uuid
from typing import List, Dict, Any
from ..models.schemas import ResumeData, JobDescription, Suggestion
from ..config import generate_chat_completion

class SuggestionEngine:
    """Generate AI-powered suggestions for resume improvement."""
    
    def __init__(self):
        self.system_prompt = """You are an expert resume writer and career coach. Your job is to help job seekers rewrite their resume to match a specific job description.

YOUR TASK:
Compare the resume with the job description and provide SPECIFIC, ACTIONABLE rewrite suggestions.

CRITICAL RULES:
1. NEVER fabricate experience - only improve existing content
2. Be VERY SPECIFIC - provide exact text to replace, not vague advice
3. Match keywords from the JD naturally (don't force them)
4. Add quantification (numbers, percentages, metrics) when realistic
5. Focus on IMPACT and RESULTS, not just responsibilities
6. Each suggestion must address a SPECIFIC requirement from the JD
7. Make suggestions PRACTICAL and IMPLEMENTABLE

QUALITY STANDARDS:
- Each suggestion should significantly improve the match
- Original and suggested text should be clearly different
- Explain WHY each change helps (which JD requirement)
- Prioritize high-impact changes (keywords, skills, achievements)

Return ONLY valid JSON in this exact format:
{
  "suggestions": [
    {
      "section_type": "bullet",
      "section_id": "experience_0_bullet_1",
      "original_text": "exact current text from resume",
      "suggested_text": "rewritten version with improvements",
      "reason": "Specific explanation: This matches JD requirement X because Y",
      "expected_score_delta": 3.5,
      "jd_mapping": "Exact JD requirement: e.g., '5+ years product management experience with AI/ML products'"
    }
  ]
}"""
    
    def generate_suggestions(
        self,
        resume: ResumeData,
        jd: JobDescription,
        max_suggestions: int = 10
    ) -> List[Suggestion]:
        """
        Generate suggestions for improving resume match to job description.
        Simplified approach: Compare JD with resume and get rewrite suggestions.
        """
        print(f"\n=== Generating Suggestions ===")
        print(f"Resume: {len(resume.experience)} experiences, {len(resume.skills)} skills")
        print(f"JD: {jd.role_title}")
        
        # Use a simpler, batch approach - generate all suggestions at once
        all_suggestions = self._generate_batch_suggestions(resume, jd, max_suggestions)
        
        # Also add skill suggestions (these are simple and don't need AI)
        skill_suggestions = self._suggest_skill_additions(resume, jd)
        all_suggestions.extend(skill_suggestions)
        
        # Sort by expected score delta (highest impact first)
        all_suggestions.sort(key=lambda x: x.expected_score_delta, reverse=True)
        
        print(f"Generated {len(all_suggestions)} total suggestions")
        return all_suggestions[:max_suggestions]
    
    def _generate_batch_suggestions(
        self,
        resume: ResumeData,
        jd: JobDescription,
        max_suggestions: int
    ) -> List[Suggestion]:
        """Generate suggestions in batch - simpler and more reliable."""
        suggestions = []
        
        # Prepare resume content
        resume_content = []
        resume_content.append(f"RESUME SUMMARY: {resume.summary or 'No summary'}")
        resume_content.append(f"\nEXPERIENCE:")
        for i, exp in enumerate(resume.experience[:5]):  # Top 5 experiences
            resume_content.append(f"\n{i+1}. {exp.title} at {exp.company} ({exp.start_date} - {exp.end_date or 'Present'})")
            for j, bullet in enumerate(exp.bullets[:3]):  # Top 3 bullets per experience
                resume_content.append(f"   - {bullet.text}")
        resume_content.append(f"\nSKILLS: {', '.join(resume.skills[:20])}")
        resume_text = "\n".join(resume_content)
        
        # Get JD text
        jd_text = jd.raw_text if jd.raw_text else self._create_jd_summary(jd)
        jd_text_limited = jd_text[:4000] if len(jd_text) > 4000 else jd_text
        
        user_prompt = f"""TASK: Compare this resume with the job description and provide SPECIFIC rewrite suggestions.

JOB DESCRIPTION:
{jd_text_limited}

RESUME:
{resume_text}

CRITICAL INSTRUCTIONS:
1. For each suggestion, ONLY include the SPECIFIC TEXT being changed, NOT the entire resume
2. For bullet points: include ONLY that one bullet point text
3. For skills: include ONLY the skills section (comma-separated list)
4. For summary: include ONLY the summary text
5. DO NOT include education, certifications, or other sections unless specifically changing them

ANALYSIS STEPS:
1. Read the job description - identify key requirements, skills, and keywords
2. Read the resume - identify what matches and what's missing
3. For each resume bullet point, ask: "How can I rewrite this to better match the JD?"
4. Focus on the TOP {max_suggestions} most impactful changes

WHAT TO SUGGEST:
- Rewrite bullet points to include JD keywords naturally
- Add quantification (numbers, percentages, metrics) where realistic
- Emphasize skills/experience that match JD requirements
- Improve summary to highlight relevant experience
- Make language match the JD's tone and level

QUALITY REQUIREMENTS:
- Each suggestion must be SPECIFIC (exact text to change - NOT the whole resume)
- Each suggestion must be ACTIONABLE (clear improvement)
- Each suggestion must address a SPECIFIC JD requirement
- Original and suggested text should be clearly different
- Prioritize high-impact changes (keywords, required skills, key experience)

EXAMPLE OF GOOD SUGGESTION:
{{
  "section_type": "bullet",
  "section_id": "experience_0_bullet_1",
  "original_text": "Worked on product features",
  "suggested_text": "Led development of 3 AI-powered product features, increasing user engagement by 25% and reducing churn by 15%",
  "reason": "Matches JD requirement for 'AI/ML product experience' and 'proven track record of driving user engagement'",
  "expected_score_delta": 4.0,
  "jd_mapping": "5+ years product management experience with AI/ML products"
}}

IMPORTANT: In "original_text" and "suggested_text", include ONLY the specific text being changed (one bullet, skills list, or summary), NOT the entire resume.

Return JSON with {max_suggestions} high-quality, specific suggestions."""
        
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        try:
            print("Generating batch suggestions...")
            response_text = generate_chat_completion(messages, model='gpt-4', json_mode=True)
            
            if not response_text:
                print("✗ Empty response from API")
                return []
            
            # Check if response is an error message
            response_text = response_text.strip()
            if response_text.startswith(('Error:', 'Internal', 'Failed', 'Exception', 'API')):
                print(f"✗ API returned error: {response_text[:200]}")
                raise ValueError(f"API error: {response_text[:200]}")
            
            # Clean response - remove markdown code blocks
            if response_text.startswith('```json'):
                response_text = response_text[7:]
            elif response_text.startswith('```'):
                response_text = response_text[3:]
            if response_text.endswith('```'):
                response_text = response_text[:-3]
            response_text = response_text.strip()
            
            # Try to parse JSON
            try:
                response_data = json.loads(response_text)
            except json.JSONDecodeError as json_err:
                print(f"✗ JSON parse error: {json_err}")
                print(f"  Response preview: {response_text[:500]}")
                # Try to extract JSON from the response if it's wrapped in text
                import re
                json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                if json_match:
                    try:
                        response_data = json.loads(json_match.group(0))
                        print("  ✓ Extracted JSON from response")
                    except:
                        raise json_err
                else:
                    raise json_err
            
            if 'suggestions' in response_data and len(response_data['suggestions']) > 0:
                print(f"  Processing {len(response_data['suggestions'])} suggestions from API")
                for i, sug_data in enumerate(response_data['suggestions']):
                    suggested_text = sug_data.get('suggested_text', '').strip()
                    original_text = sug_data.get('original_text', '').strip()
                    
                    # Filter out suggestions that include too much content (likely entire resume)
                    # For skill suggestions, limit to 300 chars
                    # For bullet suggestions, limit to 200 chars
                    # For summary, limit to 500 chars
                    section_type = sug_data.get('section_type', 'bullet')
                    max_length = 500 if section_type == 'summary' else (300 if section_type == 'skill' else 200)
                    
                    if len(original_text) > max_length * 2:  # Too long, likely includes extra content
                        # Try to extract just the relevant part
                        if section_type == 'skill' and 'SKILLS' in original_text.upper():
                            # Extract skills section
                            import re
                            skills_match = re.search(r'(?:SKILLS|skills)[:\s]*(.+?)(?:\n\n|\n[A-Z]{2,}|$)', original_text, re.IGNORECASE | re.DOTALL)
                            if skills_match:
                                original_text = skills_match.group(1).strip()[:max_length]
                        elif section_type == 'bullet':
                            # Take first sentence or first 200 chars
                            first_sentence = original_text.split('.')[0] + '.' if '.' in original_text else original_text
                            original_text = first_sentence[:max_length]
                    
                    if len(suggested_text) > max_length * 2:
                        # Apply same filtering
                        if section_type == 'skill' and 'SKILLS' in suggested_text.upper():
                            import re
                            skills_match = re.search(r'(?:SKILLS|skills)[:\s]*(.+?)(?:\n\n|\n[A-Z]{2,}|$)', suggested_text, re.IGNORECASE | re.DOTALL)
                            if skills_match:
                                suggested_text = skills_match.group(1).strip()[:max_length]
                        elif section_type == 'bullet':
                            first_sentence = suggested_text.split('.')[0] + '.' if '.' in suggested_text else suggested_text
                            suggested_text = first_sentence[:max_length]
                    
                    if not suggested_text or not original_text:
                        print(f"    ✗ Suggestion {i+1}: Missing text (original: {bool(original_text)}, suggested: {bool(suggested_text)})")
                        continue
                    
                    if suggested_text == original_text:
                        print(f"    ✗ Suggestion {i+1}: No change detected")
                        continue
                    
                    # Find the actual section_id from resume
                    section_id = sug_data.get('section_id', 'unknown')
                    
                    try:
                        suggestion = Suggestion(
                            id=str(uuid.uuid4()),
                            section_type=section_type,
                            section_id=section_id,
                            original_text=original_text[:max_length],  # Enforce limit
                            suggested_text=suggested_text[:max_length],  # Enforce limit
                            reason=sug_data.get('reason', 'Improves match to job description') or 'Improves match to job description',
                            expected_score_delta=float(sug_data.get('expected_score_delta', 2.0)),
                            jd_mapping=sug_data.get('jd_mapping', '') or ''
                        )
                        suggestions.append(suggestion)
                        print(f"    ✓ Suggestion {i+1}: {section_type} - {original_text[:50]}...")
                    except Exception as e:
                        print(f"    ✗ Suggestion {i+1}: Error creating suggestion object: {e}")
                        continue
            else:
                print(f"  ✗ No suggestions in response or empty list")
                if 'suggestions' in response_data:
                    print(f"    Response has 'suggestions' key but it's empty or invalid")
                else:
                    print(f"    Response missing 'suggestions' key")
                print(f"    Response keys: {list(response_data.keys()) if isinstance(response_data, dict) else 'Not a dict'}")
            
            print(f"✓ Generated {len(suggestions)} suggestions from batch")
            return suggestions
            
        except json.JSONDecodeError as e:
            print(f"JSON decode error: {e}")
            print(f"Response preview: {response_text[:500] if 'response_text' in locals() else 'N/A'}")
            return []
        except Exception as e:
            print(f"Error generating batch suggestions: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def _suggest_bullet_improvements(
        self,
        resume: ResumeData,
        jd: JobDescription
    ) -> List[Suggestion]:
        """Generate suggestions for improving experience bullets."""
        suggestions = []
        
        # Use raw JD text directly - LLM can extract what it needs
        jd_text = jd.raw_text if jd.raw_text else self._create_jd_summary(jd)
        
        # Batch process bullets to reduce API calls and improve context
        # Focus on most relevant experiences first
        relevant_experiences = resume.experience[:5]  # Top 5 experiences
        
        for exp_idx, exp in enumerate(relevant_experiences):
            # Process up to 3 bullets per experience to focus on quality
            bullets_to_process = exp.bullets[:3]
            
            for bullet_idx, bullet in enumerate(bullets_to_process):
                section_id = f"experience_{exp_idx}_bullet_{bullet_idx}"
                
                # Limit JD text to avoid token limits
                jd_text_limited = jd_text[:3000] if len(jd_text) > 3000 else jd_text
                user_prompt = f"""JOB DESCRIPTION:
{jd_text_limited}

RESUME BULLET POINT TO IMPROVE:
"{bullet.text}"

CONTEXT:
- Job Title: {exp.title}
- Company: {exp.company}
- Duration: {exp.start_date} - {exp.end_date or 'Present'}

TASK: Improve this bullet point to better match the job description.

RULES:
1. Keep it truthful - only improve existing content
2. Match keywords from the JD naturally
3. Add numbers/metrics if realistic
4. Focus on impact and results
5. Specify which JD requirement it addresses

Return JSON with ONE suggestion in the exact format specified."""
                
                messages = [
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": user_prompt}
                ]
                
                try:
                    print(f"  Generating suggestion for: {bullet.text[:50]}...")
                    response_text = generate_chat_completion(messages, model='gpt-4', json_mode=True)
                    
                    if not response_text:
                        print(f"  Empty response for bullet {section_id}")
                        continue
                    
                    # Clean response - remove markdown code blocks if present
                    response_text = response_text.strip()
                    if response_text.startswith('```json'):
                        response_text = response_text[7:]
                    if response_text.startswith('```'):
                        response_text = response_text[3:]
                    if response_text.endswith('```'):
                        response_text = response_text[:-3]
                    response_text = response_text.strip()
                    
                    response_data = json.loads(response_text)
                    
                    if 'suggestions' in response_data and len(response_data['suggestions']) > 0:
                        suggestion_data = response_data['suggestions'][0]
                        suggested_text = suggestion_data.get('suggested_text', '').strip()
                        
                        # Only add if there's a meaningful improvement
                        if suggested_text and suggested_text != bullet.text and len(suggested_text) > 10:
                            suggestion = Suggestion(
                                id=str(uuid.uuid4()),
                                section_type='bullet',
                                section_id=section_id,
                                original_text=bullet.text,
                                suggested_text=suggested_text,
                                reason=suggestion_data.get('reason', 'Improves match to job description'),
                                expected_score_delta=float(suggestion_data.get('expected_score_delta', 2.0)),
                                jd_mapping=suggestion_data.get('jd_mapping', '')
                            )
                            suggestions.append(suggestion)
                            print(f"  ✓ Generated suggestion")
                        else:
                            print(f"  ✗ Suggestion not meaningful enough")
                    else:
                        print(f"  ✗ No suggestions in response")
                        
                except json.JSONDecodeError as e:
                    print(f"  ✗ JSON decode error for bullet {section_id}: {e}")
                    print(f"  Response preview: {response_text[:200] if 'response_text' in locals() else 'N/A'}")
                    continue
                except Exception as e:
                    # Skip this bullet if LLM call fails
                    print(f"  ✗ Error generating suggestion for bullet {section_id}: {e}")
                    import traceback
                    traceback.print_exc()
                    continue
        
        return suggestions
    
    def _suggest_skill_additions(
        self,
        resume: ResumeData,
        jd: JobDescription
    ) -> List[Suggestion]:
        """Suggest adding missing skills - only if they're actually missing."""
        suggestions = []
        
        if not resume.skills:
            return suggestions
        
        # Normalize skills for comparison (handle variations)
        resume_skills_lower = [s.lower().strip() for s in resume.skills]
        
        # Check for missing required skills
        missing_required = []
        for jd_skill in jd.required_skills:
            jd_skill_lower = jd_skill.lower().strip()
            # Check if skill or a variation exists
            found = False
            for resume_skill in resume_skills_lower:
                # Check exact match or if one contains the other
                if jd_skill_lower == resume_skill or jd_skill_lower in resume_skill or resume_skill in jd_skill_lower:
                    found = True
                    break
            if not found:
                missing_required.append(jd_skill)
        
        # Check for missing preferred skills
        missing_preferred = []
        for jd_skill in jd.preferred_skills:
            jd_skill_lower = jd_skill.lower().strip()
            found = False
            for resume_skill in resume_skills_lower:
                if jd_skill_lower == resume_skill or jd_skill_lower in resume_skill or resume_skill in jd_skill_lower:
                    found = True
                    break
            if not found:
                missing_preferred.append(jd_skill)
        
        # Only suggest skills that are actually missing and meaningful
        # Suggest adding required skills first (limit to top 2 most important)
        for skill in missing_required[:2]:
            # Format: show current skills (limited) and suggested addition
            current_skills_display = ', '.join(resume.skills[:10])  # Show first 10 skills
            if len(resume.skills) > 10:
                current_skills_display += f", ... ({len(resume.skills) - 10} more)"
            
            suggested_skills = resume.skills + [skill]
            suggested_display = ', '.join(suggested_skills[:10])
            if len(suggested_skills) > 10:
                suggested_display += f", ... ({len(suggested_skills) - 10} more)"
            
            suggestion = Suggestion(
                id=str(uuid.uuid4()),
                section_type='skill',
                section_id='skills_section',
                original_text=current_skills_display,
                suggested_text=suggested_display,
                reason=f"Add required skill '{skill}' from job description to improve keyword match",
                expected_score_delta=5.0,  # Required skills have higher impact
                jd_mapping=f"Required skill: {skill}"
            )
            suggestions.append(suggestion)
        
        # Suggest adding preferred skills (limit to top 1)
        for skill in missing_preferred[:1]:
            current_skills_display = ', '.join(resume.skills[:10])
            if len(resume.skills) > 10:
                current_skills_display += f", ... ({len(resume.skills) - 10} more)"
            
            suggested_skills = resume.skills + [skill]
            suggested_display = ', '.join(suggested_skills[:10])
            if len(suggested_skills) > 10:
                suggested_display += f", ... ({len(suggested_skills) - 10} more)"
            
            suggestion = Suggestion(
                id=str(uuid.uuid4()),
                section_type='skill',
                section_id='skills_section',
                original_text=current_skills_display,
                suggested_text=suggested_display,
                reason=f"Add preferred skill '{skill}' to strengthen application",
                expected_score_delta=2.0,
                jd_mapping=f"Preferred skill: {skill}"
            )
            suggestions.append(suggestion)
        
        return suggestions
    
    def _suggest_summary_improvements(
        self,
        resume: ResumeData,
        jd: JobDescription
    ) -> List[Suggestion]:
        """Suggest improvements to professional summary."""
        suggestions = []
        
        # Use raw JD text directly
        jd_text = jd.raw_text if jd.raw_text else self._create_jd_summary(jd)
        current_summary = resume.summary or "No summary provided."
        
        # Limit JD text to avoid token limits
        jd_text_limited = jd_text[:3000] if len(jd_text) > 3000 else jd_text
        user_prompt = f"""JOB DESCRIPTION:
{jd_text_limited}

CURRENT RESUME SUMMARY:
{current_summary}

TASK: Improve this summary to better match the job description.

RULES:
1. Keep it truthful - only use existing experience
2. Match keywords from JD naturally
3. Be concise (2-3 sentences)
4. Highlight relevant experience

Return JSON with ONE suggestion in the exact format specified."""
        
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        try:
            print("Generating summary suggestion...")
            response_text = generate_chat_completion(messages, model='gpt-4', json_mode=True)
            
            if not response_text:
                print("Empty response for summary")
                return suggestions
            
            # Clean response
            response_text = response_text.strip()
            if response_text.startswith('```json'):
                response_text = response_text[7:]
            if response_text.startswith('```'):
                response_text = response_text[3:]
            if response_text.endswith('```'):
                response_text = response_text[:-3]
            response_text = response_text.strip()
            
            response_data = json.loads(response_text)
            
            if 'suggestions' in response_data and len(response_data['suggestions']) > 0:
                suggestion_data = response_data['suggestions'][0]
                suggested_text = suggestion_data.get('suggested_text', '').strip()
                
                if suggested_text and suggested_text != current_summary:
                    suggestion = Suggestion(
                        id=str(uuid.uuid4()),
                        section_type='summary',
                        section_id='summary_section',
                        original_text=current_summary,
                        suggested_text=suggested_text,
                        reason=suggestion_data.get('reason', 'Improves alignment with job requirements'),
                        expected_score_delta=float(suggestion_data.get('expected_score_delta', 3.0)),
                        jd_mapping=suggestion_data.get('jd_mapping', 'Overall job match')
                    )
                    suggestions.append(suggestion)
                    print("✓ Generated summary suggestion")
        except json.JSONDecodeError as e:
            print(f"JSON decode error for summary: {e}")
            print(f"Response was: {response_text[:200] if 'response_text' in locals() else 'N/A'}")
        except Exception as e:
            print(f"Error generating summary suggestion: {e}")
            import traceback
            traceback.print_exc()
        
        return suggestions
    
    def generate_fit_summary(
        self,
        resume: ResumeData,
        jd: JobDescription,
        ats_score: float,
        semantic_fit: str
    ) -> Dict[str, Any]:
        """Generate comprehensive fit summary with strengths, gaps, and overall assessment."""
        # Build experience summary
        exp_summary = []
        for exp in resume.experience[:3]:  # Top 3 experiences
            exp_summary.append(f"{exp.title} at {exp.company}")
        
        # Use raw JD text directly - LLM can extract what it needs
        jd_text = jd.raw_text if jd.raw_text else self._create_jd_summary(jd)
        
        # Build resume summary
        resume_summary_parts = []
        if resume.summary:
            resume_summary_parts.append(f"Summary: {resume.summary}")
        resume_summary_parts.append(f"Experience: {len(resume.experience)} positions")
        if resume.experience:
            resume_summary_parts.append("Top roles:")
            for exp in resume.experience[:3]:
                resume_summary_parts.append(f"  - {exp.title} at {exp.company}")
        resume_summary_parts.append(f"Skills: {', '.join(resume.skills[:20])}")
        resume_text = "\n".join(resume_summary_parts)
        
        # Limit JD text to avoid token limits
        jd_text_limited = jd_text[:4000] if len(jd_text) > 4000 else jd_text
        user_prompt = f"""Analyze how well this resume fits the job description.

JOB DESCRIPTION:
{jd_text_limited}

RESUME:
{resume_text}

CURRENT SCORES:
- ATS Score: {ats_score}/100
- Semantic Fit: {semantic_fit}

Provide analysis in JSON format:
{{
  "summary": "2-3 sentence overall assessment - be specific about fit level, key matches, and main gaps",
  "strengths": ["specific strength 1", "specific strength 2", "specific strength 3"],
  "gaps": ["specific gap 1 - what's missing", "specific gap 2"],
  "overlaps": ["specific overlap area 1", "specific overlap area 2"],
  "recommendations": ["actionable recommendation 1", "actionable recommendation 2"]
}}

Be SPECIFIC and ACTIONABLE. Focus on concrete examples."""
        
        messages = [
            {"role": "system", "content": "You are an expert career coach and resume advisor. Analyze resume-job fit with honesty, specificity, and actionable insights. Focus on concrete examples from the resume and job description."},
            {"role": "user", "content": user_prompt}
        ]
        
        try:
            print("Generating fit summary...")
            response_text = generate_chat_completion(messages, model='gpt-4', json_mode=True)
            
            if not response_text:
                raise ValueError("Empty response from API")
            
            # Clean response
            response_text = response_text.strip()
            if response_text.startswith('```json'):
                response_text = response_text[7:]
            if response_text.startswith('```'):
                response_text = response_text[3:]
            if response_text.endswith('```'):
                response_text = response_text[:-3]
            response_text = response_text.strip()
            
            response_data = json.loads(response_text)
            
            result = {
                'summary': response_data.get('summary', f'Your resume shows a {semantic_fit.lower()} fit for this {jd.role_title} role.'),
                'top_strengths': response_data.get('strengths', [])[:5],
                'key_gaps': response_data.get('gaps', [])[:5],
                'overlaps': response_data.get('overlaps', [])[:5],
                'recommendations': response_data.get('recommendations', [])[:5]
            }
            print("✓ Generated fit summary")
            return result
        except json.JSONDecodeError as e:
            print(f"JSON decode error for fit summary: {e}")
            print(f"Response was: {response_text[:500] if 'response_text' in locals() else 'N/A'}")
            return {
                'summary': f'Your resume shows a {semantic_fit.lower()} fit for this {jd.role_title} role. ATS score: {ats_score}/100.',
                'top_strengths': ['Review the job description to identify matching experience'],
                'key_gaps': ['Compare your skills with required skills in the JD'],
                'overlaps': [],
                'recommendations': ['Use the suggestions feature to get specific improvements']
            }
        except Exception as e:
            print(f"Error generating fit summary: {e}")
            import traceback
            traceback.print_exc()
            return {
                'summary': f'Your resume shows a {semantic_fit.lower()} fit for this {jd.role_title} role. ATS score: {ats_score}/100.',
                'top_strengths': [],
                'key_gaps': [],
                'overlaps': [],
                'recommendations': ['Use the suggestions feature to get specific improvements']
            }
    
    def _create_jd_summary(self, jd: JobDescription) -> str:
        """Create a comprehensive summary of the job description."""
        summary_parts = [f"ROLE: {jd.role_title}"]
        
        if jd.company:
            summary_parts.append(f"COMPANY: {jd.company}")
        
        if jd.responsibilities:
            summary_parts.append(f"\nKEY RESPONSIBILITIES:")
            summary_parts.append("\n".join(f"  • {r}" for r in jd.responsibilities[:8]))
        
        if jd.requirements:
            summary_parts.append(f"\nREQUIREMENTS:")
            summary_parts.append("\n".join(f"  • {r}" for r in jd.requirements[:8]))
        
        if jd.preferred_qualifications:
            summary_parts.append(f"\nPREFERRED QUALIFICATIONS:")
            summary_parts.append("\n".join(f"  • {pq}" for pq in jd.preferred_qualifications[:5]))
        
        if jd.required_skills:
            summary_parts.append(f"\nREQUIRED SKILLS: {', '.join(jd.required_skills[:15])}")
        
        if jd.preferred_skills:
            summary_parts.append(f"PREFERRED SKILLS: {', '.join(jd.preferred_skills[:10])}")
        
        if jd.keywords:
            summary_parts.append(f"\nKEYWORDS: {', '.join(jd.keywords[:20])}")
        
        return "\n".join(summary_parts)


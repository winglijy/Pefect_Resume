# Simple Resume Suggestion Tool - Core Features

## What This App Does

A simple tool to help you tailor your resume to job descriptions:
1. **Upload your resume** → Stored as your default resume
2. **Paste job description** → AI analyzes it
3. **Get suggestions** → AI compares your resume with JD and suggests improvements
4. **Accept/Reject** → Review and apply suggestions

## How to Use

### Step 1: Upload Resume
- Upload your resume (PDF or DOCX)
- It's automatically set as your default resume
- The app extracts your experience, skills, education, etc.

### Step 2: Paste Job Description
- Simply paste the full job description text
- No need for URLs or formatting
- The AI uses the raw text directly for better accuracy

### Step 3: Get Suggestions
- Click "Generate Suggestions"
- The AI compares your resume with the JD
- You'll get specific suggestions showing:
  - **Current text** (what you have now)
  - **Suggested text** (improved version)
  - **Why it helps** (which JD requirement it matches)
  - **Expected impact** (score improvement)

### Step 4: Accept or Reject
- Review each suggestion
- Click **Accept** to apply the change
- Click **Reject** to skip it
- Your resume is updated automatically when you accept

## Technical Details

- **Backend**: FastAPI (Python)
- **AI**: Uses AI Builder MCP API (GPT-4)
- **Database**: SQLite (stores resumes, JDs, suggestions)
- **Frontend**: Simple HTML/CSS/JavaScript

## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Set up API key:
   ```bash
   echo "AI_BUILDER_TOKEN=your_token_here" > .env
   ```

3. Run the app:
   ```bash
   python app.py
   ```

4. Open browser:
   ```
   http://127.0.0.1:5000
   ```

## Key Features

✅ Simple 3-step flow  
✅ Direct JD text comparison (no complex parsing)  
✅ Specific, actionable suggestions  
✅ Accept/reject functionality  
✅ Automatic resume updates  


# Perfect Resume MVP

AI-powered resume tailoring tool that helps job seekers customize their resumes for specific job descriptions with ATS scoring, semantic matching, and AI-powered suggestions.

## Features

- **Resume Parsing**: Upload PDF or DOCX resumes and extract structured data
- **Job Description Parsing**: Parse job descriptions from URLs (LinkedIn, company pages) or paste text
- **ATS Scoring**: Calculate ATS-style score (0-100) with detailed breakdown
- **Semantic Matching**: Use AI embeddings to calculate semantic fit (Low/Medium/High)
- **AI Suggestions**: Get granular suggestions for:
  - Bullet point improvements
  - Skill additions
  - Summary enhancements
- **Control Loop**: Accept, reject, or edit suggestions with real-time score updates
- **Resume Regeneration**: Export tailored resume in DOCX format with formatting preservation

## Setup

1. **Install Dependencies**:
```bash
pip install -r requirements.txt
```

2. **Configure Environment**:
Create a `.env` file in the project root:
```
AI_BUILDER_TOKEN=your_token_here
```

The token can be retrieved using the MCP `get_auth_token` tool.

3. **Run the Application**:
```bash
python app.py
```

The application will be available at `http://127.0.0.1:5000`

## Usage

1. **Upload Resume**: Upload your resume (PDF or DOCX format)
2. **Add Job Description**: Paste job description text or provide a LinkedIn/company job URL
3. **Get Scores**: Calculate ATS score and semantic fit
4. **Review Suggestions**: Review AI-generated suggestions for improvement
5. **Accept/Reject**: Accept suggestions you like, reject others
6. **Export**: Download your tailored resume

## API Endpoints

### Resume Management
- `POST /api/upload-resume` - Upload and parse resume
- `GET /api/resume/{resume_id}` - Get parsed resume data

### Job Description
- `POST /api/parse-jd` - Parse job description from URL or text

### Scoring
- `POST /api/score` - Calculate ATS and semantic scores

### Suggestions
- `POST /api/suggestions` - Generate improvement suggestions
- `POST /api/suggestions/{suggestion_id}/accept` - Accept a suggestion
- `POST /api/suggestions/{suggestion_id}/reject` - Reject a suggestion
- `POST /api/suggestions/{suggestion_id}/edit` - Edit and accept a suggestion

### Export
- `POST /api/export` - Generate tailored resume
- `GET /api/download/{export_id}` - Download generated resume

## Architecture

- **Backend**: FastAPI (Python)
- **Frontend**: HTML/CSS/JavaScript
- **Database**: SQLite
- **AI**: AI Builder MCP API (OpenAI-compatible)
  - GPT-4/3.5 for suggestions
  - text-embedding-3-small for semantic matching

## Project Structure

```
Perfect Resume /
├── app.py                 # FastAPI main application
├── requirements.txt       # Python dependencies
├── database.db           # SQLite database (created on first run)
├── uploads/              # Uploaded resume files
├── exports/              # Generated resume files
├── templates/
│   └── index.html        # Frontend UI
└── src/
    ├── parsers/          # Resume and JD parsers
    ├── scoring/          # ATS and semantic scoring
    ├── suggestions/      # AI suggestion engine
    ├── regeneration/     # Resume rebuilding
    └── models/           # Data models and database
```

## Success Metrics

- Resume tailored in < 10 minutes
- ≥ +15 ATS score improvement per job
- ≥ 80% suggestions accepted or lightly edited
- Zero formatting loss in export

## License

MIT


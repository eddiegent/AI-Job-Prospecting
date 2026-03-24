# Job Prospecting Toolkit

A collection of [Claude Code](https://docs.anthropic.com/en/docs/claude-code) skills for automating and streamlining job search activities. Provide a job offer and your master CV, and get a complete, tailored application pack in seconds.

## What It Does

The main skill, `/job-application-tailor`, takes a job offer (URL or pasted text) and your master CV, then produces:

- **Tailored CV** (DOCX + PDF) — restructured and optimized for the specific role
- **Motivation letter** — formal cover letter aligned with the job requirements
- **LinkedIn messages** — ready-to-send outreach with real contact names
- **Interview prep guide** — company research, likely questions, and talking points
- **Fit score** — honest assessment of how well your profile matches the role

Every claim in the output is grounded in your source CV — nothing is invented.

### Satellite Skills

| Skill | Description |
|-------|-------------|
| `/job-status` | Update application statuses (applied, rejected, interview, offer) and manage company blacklist/whitelist |
| `/job-stats` | View application statistics, trends, skill gap analysis, and export data |

## Project Structure

```
.
├── CLAUDE.md                          # Claude Code project instructions
├── resources/
│   └── MASTER_CV.docx                 # Your master CV (not tracked in git)
├── output/                            # Generated application packs (not tracked)
│   └── [fit_level]-[date]-[job-slug]/
│       ├── CV_*.docx / .pdf
│       ├── Lettre_de_motivation_*.docx
│       ├── Interview_prep_*.md
│       ├── LinkedIn_message_*.txt
│       └── run_summary.json
└── .claude/skills/job-application-tailor/
    ├── SKILL.md                       # Main skill definition
    ├── prompts/                       # Step-by-step generation prompts
    ├── schemas/                       # JSON schemas for validation
    ├── scripts/                       # Python utilities (DOCX generation, validation)
    ├── config/                        # Language labels, formatting rules
    ├── templates/                     # Interview prep template
    ├── skills/                        # Satellite skills (job-status, job-stats)
    └── requirements.txt               # Python dependencies
```

## Prerequisites

- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) installed and configured
- Python 3.10+ with dependencies:
  ```
  pip install -r .claude/skills/job-application-tailor/requirements.txt
  ```
- LibreOffice (for PDF conversion) or Microsoft Word

## Getting Started

1. Clone this repository
2. Install Python dependencies (see above)
3. Place your master CV at `resources/MASTER_CV.docx`
4. Run Claude Code in the project directory and provide a job offer:
   ```
   claude
   > /job-application-tailor https://example.com/job-posting
   ```

The skill will analyze the offer, match it against your CV, and generate a complete application pack in the `output/` directory.

## Application Tracking

Applications are tracked in a local SQLite database (`resources/job_history.db`). Use the satellite skills to manage your pipeline:

```
> /job-status Acme Corp applied
> /job-stats summary
```

## Privacy

Personal data (your CV, generated outputs, application history) is excluded from version control via `.gitignore`. Only the skill infrastructure is tracked.

## License

MIT

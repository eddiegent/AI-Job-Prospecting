# Example Output

This folder contains anonymised sample files showing what the skill produces.

## Structure

```
examples/
├── _prep/
│   ├── job_offer_analysis.json   — structured extraction from the job offer
│   └── match_analysis.json       — requirement-by-requirement matching with fit score
└── run_summary.json              — final summary with fit %, match counts, file paths
```

## What a real output folder looks like

```
good-24032026-Senior-Full-Stack-Developer-Acme-Technologies/
├── CV_Jane_Doe_Senior_Full_Stack_Developer.docx
├── CV_Jane_Doe_Senior_Full_Stack_Developer.pdf
├── Cover_letter_Jane_Doe_Senior_Full_Stack_Developer.docx
├── Short_cover_letter_Jane_Doe_Senior_Full_Stack_Developer.txt
├── LinkedIn_message_Jane_Doe_Senior_Full_Stack_Developer.txt
├── Interview_prep_Jane_Doe_Senior_Full_Stack_Developer.md
├── run_summary.json
└── _prep/
    ├── cv_fact_base.json
    ├── job_offer_analysis.json
    ├── company_research.md
    ├── match_analysis.json
    ├── tailored_cv.json
    ├── letter.json
    ├── short_letter.json
    ├── linkedin.json
    └── interview_prep.md
```

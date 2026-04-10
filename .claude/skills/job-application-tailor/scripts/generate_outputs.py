from __future__ import annotations

import argparse
import sys
from pathlib import Path

from common import (
    build_output_folder_name,
    current_date_ddmmyyyy,
    dump_json,
    ensure_dir,
    load_json,
    load_yaml,
    safe_filename,
)
from docx_generator import generate_cv_docx, generate_letter_docx
from pdf_pipeline import PdfConversionError, convert_docx_to_pdf
from validate import validate

SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schemas"


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate output files from prepared JSON data.")
    parser.add_argument("--tailored-cv-json", required=True)
    parser.add_argument("--letter-json", required=True)
    parser.add_argument("--short-letter-json", default=None, help="Path to short_letter.json (optional)")
    parser.add_argument("--linkedin-json", required=True)
    parser.add_argument("--interview-markdown", required=True)
    parser.add_argument("--output-folder", help="Parent folder — a date-title subfolder will be created inside")
    parser.add_argument("--output-dir", help="Exact output directory — use as-is, no subfolder created")
    parser.add_argument("--job-title", required=True)
    parser.add_argument("--date-override")
    parser.add_argument("--settings", default="config/settings.yaml")
    parser.add_argument("--naming-rules", default="config/naming_rules.yaml")
    parser.add_argument("--match-analysis-json", default=None, help="Path to match_analysis.json for run summary enrichment")
    parser.add_argument("--language", default="fr")
    args = parser.parse_args()

    settings = load_yaml(Path(args.settings))
    naming = load_yaml(Path(args.naming_rules))

    cv_data = load_json(Path(args.tailored_cv_json))
    letter_data = load_json(Path(args.letter_json))
    linkedin_data = load_json(Path(args.linkedin_json))
    interview_text = Path(args.interview_markdown).read_text(encoding="utf-8")

    # Validate all JSON inputs against schemas before generating files
    validations = [
        (Path(args.tailored_cv_json), SCHEMA_DIR / "tailored_cv.schema.json", "tailored CV"),
        (Path(args.letter_json), SCHEMA_DIR / "letter.schema.json", "motivation letter"),
        (Path(args.linkedin_json), SCHEMA_DIR / "linkedin.schema.json", "LinkedIn messages"),
    ]
    for data_path, schema_path, label in validations:
        if schema_path.exists():
            errors = validate(data_path, schema_path)
            if errors:
                print(f"Validation FAILED for {label} ({data_path.name}):")
                for err in errors:
                    print(f"  - {err}")
                sys.exit(1)

    if args.output_dir:
        out_dir = Path(args.output_dir)
    elif args.output_folder:
        date_str = args.date_override or current_date_ddmmyyyy()
        folder_name = build_output_folder_name(date_str, args.job_title)
        out_dir = Path(args.output_folder) / folder_name
    else:
        parser.error("Either --output-dir or --output-folder is required")
    ensure_dir(out_dir)

    candidate_name = cv_data.get("candidate_name", "Candidate")
    filenames_cfg = naming["filenames"]
    # Support language-keyed filenames (fr/en) with fallback to fr then flat structure
    if args.language in filenames_cfg and isinstance(filenames_cfg[args.language], dict):
        patterns = filenames_cfg[args.language]
    elif "fr" in filenames_cfg and isinstance(filenames_cfg["fr"], dict):
        patterns = filenames_cfg["fr"]
    else:
        patterns = filenames_cfg  # flat legacy format

    cv_name = safe_filename(patterns["cv"], candidate_name, args.job_title)
    letter_name = safe_filename(patterns["letter"], candidate_name, args.job_title)
    linkedin_name = safe_filename(patterns["linkedin"], candidate_name, args.job_title)
    interview_name = safe_filename(patterns["interview"], candidate_name, args.job_title)

    cv_path = generate_cv_docx(out_dir / cv_name, cv_data, settings, language=args.language)
    letter_path = generate_letter_docx(out_dir / letter_name, letter_data, settings)

    # Generate PDF version of the CV via the cross-platform pipeline
    # (docx2pdf → LibreOffice → pandoc). The DOCX is always preserved.
    cv_pdf_path = None
    try:
        cv_pdf_path = convert_docx_to_pdf(cv_path)
    except PdfConversionError as exc:
        print(f"PDF conversion skipped: {exc}", file=sys.stderr)

    lines = []
    for variant in linkedin_data["variants"]:
        target = variant.get("target", "unknown").replace("_", " ").title()
        contact_name = variant.get("contact_name", "")
        linkedin_url = variant.get("linkedin_url", "")
        header = f"=== {target}"
        if contact_name:
            header += f": {contact_name}"
        header += " ==="
        lines.append(header)
        if linkedin_url:
            lines.append(f"LinkedIn: {linkedin_url}")
        if variant.get("subject_hint"):
            lines.append(f"Subject: {variant['subject_hint']}")
        lines.append("")
        lines.append(variant.get("message", ""))
        lines.append("")
    (out_dir / linkedin_name).write_text("\n".join(lines).strip(), encoding="utf-8")
    (out_dir / interview_name).write_text(interview_text, encoding="utf-8")

    # Short motivation letter (plain text for online forms)
    short_letter_path = None
    if args.short_letter_json:
        short_letter_file = Path(args.short_letter_json)
        if short_letter_file.exists():
            short_letter_data = load_json(short_letter_file)
            short_letter_name = safe_filename(
                patterns.get("short_letter", "Short_letter_{candidate_name}_{job_title}.txt"),
                candidate_name, args.job_title,
            )
            parts = []
            if short_letter_data.get("greeting"):
                parts.append(short_letter_data["greeting"])
                parts.append("")
            for para in short_letter_data.get("paragraphs", []):
                parts.append(para)
                parts.append("")
            if short_letter_data.get("signoff"):
                parts.append(short_letter_data["signoff"])
            if short_letter_data.get("name"):
                parts.append(short_letter_data["name"])
            short_text = "\n".join(parts).strip()
            short_letter_path = out_dir / short_letter_name
            short_letter_path.write_text(short_text, encoding="utf-8")

    summary = {
        "output_folder": str(out_dir),
        "cv_file": str(cv_path),
        "cv_pdf_file": str(cv_pdf_path) if cv_pdf_path else None,
        "letter_file": str(letter_path),
        "short_letter_file": str(short_letter_path) if short_letter_path else None,
        "linkedin_file": str(out_dir / linkedin_name),
        "interview_file": str(out_dir / interview_name),
        "job_title": args.job_title,
        "candidate_name": candidate_name,
    }

    if args.match_analysis_json:
        match_path = Path(args.match_analysis_json)
        if match_path.exists():
            match_data = load_json(match_path)
            match_summary = match_data.get("match_summary", {})
            summary["overall_fit_pct"] = match_summary.get("overall_fit_pct")
            summary["match_summary"] = match_summary
    dump_json(out_dir / patterns["summary"], summary)
    print(str(out_dir))


if __name__ == "__main__":
    main()

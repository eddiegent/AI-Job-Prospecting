python scripts/run_skill.py \
  --job-offer sample/job_offer.txt \
  --resource-folder resources \
  --output-folder output \
  --candidate-cv-filename CV_Edward_Gent_Master.docx \
  --language fr \
  --date-override 19032026 \
  --job-title-override "Développeur .NET"

python scripts/generate_outputs.py \
  --tailored-cv-json scripts/example_tailored_cv.json \
  --letter-json scripts/example_letter.json \
  --linkedin-json scripts/example_linkedin.json \
  --interview-markdown scripts/example_interview_prep.md \
  --output-folder output \
  --job-title "Développeur .NET"

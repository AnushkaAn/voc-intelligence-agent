#!/usr/bin/env bash
# finish_and_verify.sh — the ONE command to run locally with your real API
# keys before you zip/push. Does everything in the right order and stops
# immediately if any step fails.
set -e

echo "Step 1/3: Full pipeline (scrape, tag, both reports)..."
python voc_agent.py

echo ""
echo "Step 2/3: Delta proof (Requirement 1.3)..."
python prove_delta_pipeline.py

echo ""
echo "Step 3/3: Verifying everything is consistent..."
python verify_before_submit.py

echo ""
echo "If you see ALL CHECKS PASSED above, you're clear to:"
echo "  git init && git add . && git commit -m 'VoC Intelligence Agent'"
echo "  git remote add origin <your-repo-url> && git push -u origin main"
echo "Then add FIRECRAWL_API_KEY and GROQ_API_KEY as GitHub repo secrets,"
echo "and manually trigger the 'Weekly VoC Agent Run' workflow once."

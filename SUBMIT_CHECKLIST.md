# Before you submit

Everything that could be fixed as code has been fixed. Three things can
only happen on your machine, with your real, freshly-rotated API keys,
because this environment can't reach Firecrawl or Groq:

1. Tagging the review database (sentiment + themes)
2. The Requirement 1.3 delta proof
3. Re-recording the demo clips for the two screenshots that were removed
   (they showed function names — `tool_check_new_reviews`,
   `ask_voc_analyst()` — that don't exist in this codebase anymore)

## Run this first — rotate your keys

Your old `.env` had live keys committed in a prior zip. Treat those as
burned: go to Firecrawl and Groq, revoke/regenerate both keys, and only
put the new ones in a local `.env` (never commit it — `.gitignore`
already excludes it).

```
cp .env.example .env
# edit .env and paste your NEW keys
```

## Then run one command

```
pip install -r requirements.txt
./finish_and_verify.sh
```

This runs, in order: full pipeline → delta proof → automated verification.
It will print `✅ ALL CHECKS PASSED` or tell you exactly what's still
broken. Do not zip/push until you see the PASS message.

## Re-record 2 demo clips

Using the current tool names (`tool_detect_weekly_delta`,
`tool_answer_question`), capture:
- The agent's tool-calling sequence for a full run (replaces the old
  `tool_check_new_reviews` screenshot)
- A sample grounded Q&A answer (replaces the old `ask_voc_analyst()`
  screenshot)

Drop them in `Demo/` and update `Demo/demo.md`'s image links.

## Then, and only then, make it a real repo

```
git init
git add .
git commit -m "VoC Intelligence Agent - final submission"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git push -u origin main
```

On GitHub: Settings -> Secrets and variables -> Actions -> add
`FIRECRAWL_API_KEY` and `GROQ_API_KEY`. Then Actions tab -> "Weekly VoC
Agent Run" -> "Run workflow" once, manually, and confirm it goes green
and commits `voc_reviews.db` / `reports/` back. That green run is your
actual proof of Requirement 1.2 — without it, the automation requirement
is unverified, not just unfulfilled on paper.

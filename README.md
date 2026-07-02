# Voice of Customer (VoC) Intelligence Agent

An autonomous agent that scrapes public product reviews, stores them in SQLite,
tags sentiment/themes with an LLM, and generates action-item reports for
Product, Marketing, and Support teams — plus a grounded Q&A chat interface.
All pipeline steps run through the agent's own tool-calling loop (`run_agent()`
in `voc_agent.py`), not manual script execution.

## Products Analyzed
- Noise Master Buds
- Noise Master Buds Max

## Data Source
Flipkart public review pages (pivoted from Amazon after Amazon's bot-detection
sign-in wall blocked scraping — an explicitly allowed data source per the PRD).

## Tech Stack
- **Scraping:** Firecrawl
- **Sentiment/Theme tagging:** Groq API (Llama 3.1 8B Instant — higher free daily token budget for high-volume tagging)
- **Report generation, Q&A, and agent orchestration:** Groq API (Llama 3.3 70B, tool-calling — better quality, used only for the small number of non-tagging calls)
- **Storage:** SQLite (`voc_reviews.db`)
- **Scheduling:** GitHub Actions (weekly cron, auto-commits results back to the repo)

## Setup
1. Clone this repo.
2. Get free API keys:
   - Firecrawl: https://firecrawl.dev
   - Groq: https://console.groq.com
3. Set environment variables (never commit real keys):
   - `FIRECRAWL_API_KEY`
   - `GROQ_API_KEY`
4. `pip install -r requirements.txt`
5. `python voc_agent.py`

This single command runs the full weekly cycle **through the agent's
tool-calling loop**: scrape & store new reviews → tag untagged reviews →
detect & log the weekly delta → generate the Global report → generate the
Weekly Delta report → answer the PRD's sample grounded question. The LLM
decides which tools to call and in what order — this satisfies the PRD's
"Architecture Shift" requirement (all steps executed via tool-use).

## Files
- `voc_agent.py` — the agent: parsing, tools, and the tool-calling loop
- `voc_reviews.db` — the review database (includes `sentiment`/`themes` columns)
- `reports/delta_proof_log.csv` — the official Requirement 1.3 proof (from `prove_delta_pipeline.py`): real, previously-stored reviews temporarily removed, then correctly re-detected and re-inserted as new
- `reports/weekly_new_reviews_log.csv` — feeds the Weekly Delta Report on each normal run; kept separate from the file above so a normal run can never overwrite your Requirement 1.3 proof
- `reports/Global_Action_Item_Report.md` — all-time action items by team
- `reports/Weekly_Delta_Action_Item_Report.md` — this week's new-review insights
- `SOUL.md` — agent personality/instructions
- `.github/workflows/weekly_scrape.yml` — weekly automation; commits updated DB/reports back to the repo

## Known Real-World Constraints (documented honestly)
- Flipkart's public review pages cap out well below the PRD's 500–1,000/product
  target for these two specific listings. The scraper now runs until it hits a
  repeated page (i.e. exhausts everything Flipkart exposes) rather than
  stopping at a fixed page count, so the DB reflects the true maximum available,
  not an artificial cap.
- Amazon.in blocks scraper bots behind a sign-in wall even with stealth proxy
  mode; Flipkart was used instead, per the PRD's "Amazon and/or Flipkart" allowance.
- Groq's free tier is split across two models: Llama 3.1 8B for the ~180
  repetitive tagging calls (500,000 tokens/day budget), and Llama 3.3 70B for
  report generation, Q&A, and orchestration. This was necessary after
  Llama 3.3 70B's much smaller 100,000 tokens/day cap was exhausted partway
  through tagging under a single-model setup.

## Usage
`python voc_agent.py` triggers `run_agent()`, which is also what the weekly
GitHub Action calls. To ask an ad-hoc question without running the full
pipeline, import the module and call:
```python
from voc_agent import run_agent
print(run_agent("Answer only: what do customers complain about most for MasterBuds battery life?"))
```

## Delta Proof — how Requirement 1.3 is verified
Once the first full scrape has captured everything Flipkart publicly exposes
for these two listings, a second real scrape correctly finds **zero** new
reviews — that's the dedup logic working as intended, not a bug. To
demonstrate the "detect + capture new reviews" behavior concretely with real
data (no invented review text), `prove_delta_pipeline.py` temporarily removes
a small random sample of already-stored (real, previously scraped) reviews,
re-runs the real scraper, and confirms they're correctly re-detected and
re-inserted as "new" — exactly what happens in production when Flipkart
publishes genuinely new reviews between weekly runs.

```
python prove_delta_pipeline.py
```

This overwrites `reports/delta_proof_log.csv` with the recaptured rows,
each tagged `proof_note = recaptured_in_controlled_delta_test` for full
transparency about the test methodology.




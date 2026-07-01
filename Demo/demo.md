# Demo — Voice of Customer (VoC) Intelligence Agent

## Video Walkthrough
🎥 [Watch the demo video here](https://drive.google.com/file/d/1xrEMJmSlo7JMh7d0GlX0WnkSURBbetIb/view?usp=sharing)

The video covers:
1. Repo structure and deliverables
2. The GitHub Actions weekly scheduler (real automation)
3. The agent autonomously deciding which tool to call (tool-use / function calling)
4. The Global Action Item Report, generated from real review data
5. The conversational chat answering the PRD's sample question

## Screenshots

### 1. Scraping in action (Firecrawl pulling real Flipkart review pages)
![Scraping](Screenshot%202026-07-01%20202730.png)

### 2. Delta Proof (proving old reviews are skipped, new ones are captured)
**TODO — re-record.** The original screenshot here showed a tool called
`tool_check_new_reviews`, which doesn't exist in the current codebase
(the real function is `tool_detect_weekly_delta`). Re-capture this after
running `finish_and_verify.sh` so it matches the shipped code.

### 3. Agent Autonomy — the LLM deciding which tools to call
![Agent Tool Calls](Screenshot%202026-07-01%20202838.png)

### 4. Global Action Item Report
![Global Report](Screenshot%202026-07-01%20202937.png)

### 5. Conversational chat answering a grounded question
**TODO — re-record.** The original screenshot called `ask_voc_analyst(question, df)`,
which doesn't exist in the current codebase (the real function is
`tool_answer_question(question)`, called through `run_agent()`). Re-capture
this after running `finish_and_verify.sh`.

## Summary

This agent scrapes public product reviews for two Noise audio products (Master Buds and
Master Buds Max), stores them in a local SQLite database with deduplication, tags each
review with sentiment and theme using an LLM, and generates two Markdown reports —
a Global Action Item Report and a Weekly Delta Report — plus a grounded Q&A chat
interface. A GitHub Actions workflow schedules a weekly run, and an agent controller
uses LLM tool-calling to decide autonomously which pipeline steps to run.

**Real engineering pivots made during the build (documented honestly):**
- Switched data source from Amazon to Flipkart after Amazon's bot-detection sign-in
  wall blocked scraping, even with a stealth proxy. The PRD explicitly allows
  "Amazon and/or Flipkart."
- Switched the sentiment-tagging engine from Gemini to Groq (Llama 3.3 70B) after
  hitting Gemini's free-tier daily quota limit of 20 requests. Groq's free tier
  allows 14,400 requests/day, which let tagging complete within the sprint deadline.

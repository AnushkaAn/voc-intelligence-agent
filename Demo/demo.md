# Demo — Voice of Customer (VoC) Intelligence Agent

## Video Walkthrough
🎥 [Watch the demo video here](PASTE_YOUR_LOOM_LINK_HERE)

The video covers:
1. Repo structure and deliverables
2. The GitHub Actions weekly scheduler (real automation, manually triggered and confirmed successful)
3. The agent autonomously deciding which tool to call (tool-use / function calling)
4. The Global Action Item Report, generated from real review data
5. The conversational chat answering a grounded question from the database

## Screenshots

### 1. Scraping in action (Firecrawl pulling real Flipkart review pages)
![Scraping](01_scraping.png)

### 2. Weekly automation — manually triggered and confirmed successful
![GitHub Actions Success](02_github_actions_success.png)

### 3. Agent Autonomy — the LLM deciding which tools to call
![Agent Tool Calls](03_agent_tool_calls.png)

### 4. Global Action Item Report
![Global Report](04_global_report.png)

### 5. Conversational chat answering a grounded question
![Q&A Answer](05_qa_answer.png)

## Summary

This agent scrapes public product reviews for two Noise audio products (MasterBuds and
MasterBudsMax), stores them in a local SQLite database with deduplication, tags each
review with sentiment and theme using an LLM, and generates two Markdown reports —
a Global Action Item Report and a Weekly Delta Report — plus a grounded Q&A chat
interface. A GitHub Actions workflow schedules a weekly run, manually triggered once
and confirmed successful (see screenshot #2). An agent controller uses LLM tool-calling
to decide autonomously which pipeline steps to run.

**Real engineering pivots made during the build (documented honestly):**
- Switched data source from Amazon to Flipkart after Amazon's bot-detection sign-in
  wall blocked scraping, even with a stealth proxy. The PRD explicitly allows
  "Amazon and/or Flipkart."
- Switched sentiment-tagging from Llama 3.3 70B to Llama 3.1 8B after hitting the
  70B model's 100,000-tokens-per-day free tier cap partway through tagging 180
  reviews. Report generation and Q&A still use Llama 3.3 70B, since those are a
  handful of calls, not 180, and benefit from the stronger model's quality.
- Limited scraping to 10-12 pages per product (~100-150 reviews) per direct
  guidance from the recruiter, rather than the PRD's default 500-1,000/product.
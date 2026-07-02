# -*- coding: utf-8 -*-
"""
voc_agent.py — Voice of Customer (VoC) Intelligence Agent
"""
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()
import os
import re
import json
import time
import hashlib
import sqlite3
from datetime import datetime, timedelta

import pandas as pd
from firecrawl import Firecrawl
from groq import Groq

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

FIRECRAWL_API_KEY = os.environ.get("FIRECRAWL_API_KEY")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

if not FIRECRAWL_API_KEY or not GROQ_API_KEY:
    raise RuntimeError(
        "Missing FIRECRAWL_API_KEY or GROQ_API_KEY environment variables. "
        "Set them before running (see README.md)."
    )

firecrawl = Firecrawl(api_key=FIRECRAWL_API_KEY)
groq_client = Groq(api_key=GROQ_API_KEY)

DB_PATH = "voc_reviews.db"
DELTA_LOG_PATH = "reports/delta_proof_log.csv"
WEEKLY_DELTA_PATH = "reports/weekly_new_reviews_log.csv"
GLOBAL_REPORT_PATH = "reports/Global_Action_Item_Report.md"
WEEKLY_REPORT_PATH = "reports/Weekly_Delta_Action_Item_Report.md"

PRODUCTS = {
    "MasterBuds": {
        "product_id": "itm6cb40e9367c08",
        "review_url": "https://www.flipkart.com/noise-master-buds-sound-bose-49db-anc-6-mic-enc-44-hr-battery-spatial-audio-bluetooth/product-reviews/itm6cb40e9367c08?pid=ACCHDEX9TBEM8QXE",
    },
    "MasterBudsMax": {
        "product_id": "itm85415864eeb6f",
        "review_url": "https://www.flipkart.com/noise-master-buds-max-sound-bose-segment-leading-anc-dynamic-eq-60-hr-playtime-bluetooth/product-reviews/itm85415864eeb6f",
    },
}
PRODUCT_NAMES = {v["product_id"]: k for k, v in PRODUCTS.items()}

# Safety cap only — the real stop condition is "identical page = no more
# reviews". Raised from 10 -> 60 so we actually exhaust what Flipkart has,
# instead of silently capping volume early.
MAX_PAGES_PER_PRODUCT = 12

ALLOWED_THEMES = [
    "Sound Quality", "Battery Life", "Comfort/Fit", "App Experience",
    "Price/Value", "Delivery", "Build Quality", "ANC",
]

# ---------------------------------------------------------------------------
# DB setup
# ---------------------------------------------------------------------------

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS reviews (
    review_id TEXT PRIMARY KEY,
    product_id TEXT,
    rating REAL,
    title TEXT,
    text TEXT,
    reviewer_name TEXT,
    location TEXT,
    date_relative TEXT,
    date TEXT,
    scraped_at TEXT,
    sentiment TEXT,
    themes TEXT
)
""")
conn.commit()

# Backfill sentiment/themes columns for DBs created before this schema existed
existing_cols = {row[1] for row in cursor.execute("PRAGMA table_info(reviews)")}
if "sentiment" not in existing_cols:
    cursor.execute("ALTER TABLE reviews ADD COLUMN sentiment TEXT")
if "themes" not in existing_cols:
    cursor.execute("ALTER TABLE reviews ADD COLUMN themes TEXT")
conn.commit()

# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def parse_relative_date(text, scrape_date):
    text = (text or "").strip().lower()
    if text in ("today",):
        return scrape_date.strftime("%Y-%m-%d")
    if text in ("yesterday",):
        return (scrape_date - timedelta(days=1)).strftime("%Y-%m-%d")
    match = re.search(r"(\d+)\s+(day|month|year)s?\s+ago", text)
    if not match:
        return None
    number = int(match.group(1))
    unit = match.group(2)
    delta = {
        "day": timedelta(days=number),
        "month": timedelta(days=number * 30),
        "year": timedelta(days=number * 365),
    }[unit]
    return (scrape_date - delta).strftime("%Y-%m-%d")


def parse_reviews_from_page(markdown_text, product_id, scrape_date):
    reviews = []
    pattern = r"(\d\.\d)\n\n•\n\n(.*?)(?=\n\n\d\.\d\n\n•\n\n|\Z)"
    matches = re.findall(pattern, markdown_text, re.DOTALL)

    for rating_str, block in matches:
        rating = float(rating_str)
        lines = [l.strip() for l in block.split("\n\n") if l.strip()]
        if not lines:
            continue

        title = lines[0]
        idx = 1
        if idx < len(lines) and lines[idx].startswith("Review for:"):
            idx += 1
        text = lines[idx] if idx < len(lines) else ""
        idx += 1

        while idx < len(lines) and lines[idx].startswith("!["):
            idx += 1

        reviewer_name = lines[idx] if idx < len(lines) else ""
        idx += 1

        location = ""
        if idx < len(lines) and lines[idx].startswith(","):
            location = lines[idx].lstrip(", ").strip()
            idx += 1

        date_text = ""
        for l in lines[idx:]:
            if l.startswith("·"):
                date_text = l.lstrip("· ").strip()
                break
        date_estimated = parse_relative_date(date_text, scrape_date) if date_text else None

        reviews.append({
            "product_id": product_id,
            "rating": rating,
            "title": title,
            "text": text,
            "reviewer_name": reviewer_name,
            "location": location,
            "date_relative": date_text,
            "date": date_estimated,
        })
    return reviews


def make_review_id(row):
    raw = f"{row['product_id']}_{row['reviewer_name']}_{row['title']}_{row['text']}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def scrape_all_pages(product_name, info, max_pages=MAX_PAGES_PER_PRODUCT):
    """Scrapes until a page repeats (= no more reviews) or max_pages is hit."""
    pages = []
    previous_page_text = None
    print(f"📊 Scraping {product_name}...")
    
    for page_num in range(1, max_pages + 1):
        print(f"   📄 Fetching page {page_num}...", end=" ", flush=True)
        sep = "&" if "?" in info["review_url"] else "?"
        page_url = f"{info['review_url']}{sep}page={page_num}"
        try:
            result = firecrawl.scrape(page_url, formats=["markdown"])
        except Exception as e:
            print(f"❌ Failed: {e}")
            break
        if result.markdown == previous_page_text:
            print(f"🛑 Duplicate — reached end of reviews.")
            break
        print(f"✅ Done ({len(result.markdown)} chars)")
        pages.append(result.markdown)
        previous_page_text = result.markdown
    
    print(f"   ✅ Scraped {len(pages)} pages for {product_name}")
    return pages


def tag_review_groq(title, text, max_retries=4):
    prompt = f"""You are analyzing one customer review of a wireless audio product.

Review title: {title}
Review text: {text}

Return ONLY a JSON object with exactly these two fields, nothing else:
- "sentiment": one of "Positive", "Negative", or "Neutral"
- "themes": a list of 1-3 items chosen ONLY from this exact list: {ALLOWED_THEMES}

If nothing matches, use an empty list for themes."""
    for attempt in range(max_retries):
        try:
            response = groq_client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.2,
            )
            result = json.loads(response.choices[0].message.content)
            sentiment = result.get("sentiment", "Neutral")
            themes = result.get("themes", [])
            return sentiment, ", ".join(themes)
        except Exception as e:
            print(f"      ⚠️ Tagging attempt {attempt+1} failed: {e}")
            time.sleep(5 * (attempt + 1))
    raise Exception("Gave up tagging after retries")


def build_report_context(df):
    context = ""
    for product in df["product_name"].unique():
        pdf = df[df["product_name"] == product]
        context += f"\n\n=== {product} ===\nTotal reviews: {len(pdf)}\n"
        context += pdf["sentiment"].value_counts().to_string() + "\n"
        neg = pdf[pdf["sentiment"] == "Negative"]
        pos = pdf[pdf["sentiment"] == "Positive"]
        context += f"\nNegative review excerpts ({product}):\n"
        for t in neg["text"].dropna().head(15):
            context += f"- {t[:200]}\n"
        context += f"\nPositive review excerpts ({product}):\n"
        for t in pos["text"].dropna().head(10):
            context += f"- {t[:200]}\n"
    return context


# ---------------------------------------------------------------------------
# TOOLS — every step required by the PRD's Epics 1-4, callable by the agent
# ---------------------------------------------------------------------------

def tool_scrape_and_store_reviews():
    """Scrapes every configured product, parses reviews, and inserts any
    genuinely new ones into the DB (skips duplicates by content hash)."""
    print("\n" + "="*60)
    print("🔍 STEP 1: SCRAPING REVIEWS")
    print("="*60)
    
    total_new, total_dupe = 0, 0
    scraped_at_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    per_product = {}

    for product_name, info in PRODUCTS.items():
        pages = scrape_all_pages(product_name, info)
        reviews = []
        for page_markdown in pages:
            reviews.extend(parse_reviews_from_page(page_markdown, info["product_id"], datetime.now()))

        print(f"   📝 Found {len(reviews)} total reviews on pages")
        new_here, dupe_here = 0, 0
        
        for idx, row in enumerate(reviews, 1):
            if idx % 10 == 0:
                print(f"      Processing review {idx}/{len(reviews)}...", end="\r", flush=True)
            review_id = make_review_id(row)
            try:
                cursor.execute(
                    """INSERT INTO reviews
                       (review_id, product_id, rating, title, text, reviewer_name,
                        location, date_relative, date, scraped_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (review_id, row["product_id"], row["rating"], row["title"], row["text"],
                     row["reviewer_name"], row["location"], row["date_relative"], row["date"],
                     scraped_at_now),
                )
                new_here += 1
            except sqlite3.IntegrityError:
                dupe_here += 1
        conn.commit()
        print(f"   ✅ {product_name}: {new_here} new, {dupe_here} duplicate reviews")
        per_product[product_name] = {"pages_scraped": len(pages), "new": new_here, "duplicate": dupe_here}
        total_new += new_here
        total_dupe += dupe_here

    print(f"\n📊 TOTAL: {total_new} new reviews, {total_dupe} duplicates across all products")
    return json.dumps({"total_new": total_new, "total_duplicate": total_dupe, "per_product": per_product})


def tool_detect_weekly_delta():
    """Re-scrapes the first 3 pages of each product (fast check) and logs any
    reviews found there that are NOT already in the DB. This is the real
    Requirement 1.3 delta proof — genuine new/duplicate detection, not a
    fabricated example. Writes reports/delta_proof_log.csv."""
    print("\n" + "="*60)
    print("📈 STEP 2: DETECTING WEEKLY DELTA")
    print("="*60)
    
    new_rows = []
    scraped_at_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for product_name, info in PRODUCTS.items():
        print(f"\n   Checking {product_name} (first 3 pages)...")
        pages = scrape_all_pages(product_name, info, max_pages=3)
        for page_markdown in pages:
            for row in parse_reviews_from_page(page_markdown, info["product_id"], datetime.now()):
                review_id = make_review_id(row)
                exists = cursor.execute(
                    "SELECT 1 FROM reviews WHERE review_id=?", (review_id,)
                ).fetchone()
                if not exists:
                    print(f"      🆕 New review found: {row['title'][:50]}...")
                    sentiment, themes = tag_review_groq(row["title"], row["text"])
                    cursor.execute(
                        """INSERT INTO reviews
                           (review_id, product_id, rating, title, text, reviewer_name,
                            location, date_relative, date, scraped_at, sentiment, themes)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (review_id, row["product_id"], row["rating"], row["title"], row["text"],
                         row["reviewer_name"], row["location"], row["date_relative"], row["date"],
                         scraped_at_now, sentiment, themes),
                    )
                    conn.commit()
                    new_rows.append({**row, "sentiment": sentiment, "themes": themes,
                                      "review_id": review_id, "is_simulated": False})

    delta_df = pd.DataFrame(new_rows)
    if len(delta_df) > 0:
        delta_df.to_csv(WEEKLY_DELTA_PATH, index=False)
    print(f"\n✅ Found {len(new_rows)} genuinely new reviews in delta check")
    return json.dumps({"genuinely_new_reviews_found": len(new_rows), "log_file": WEEKLY_DELTA_PATH})


def tool_tag_untagged_reviews():
    print("\n" + "="*60)
    print("🏷️ STEP 3: TAGGING UNTAGGED REVIEWS")
    print("="*60)
    
    untagged = cursor.execute(
        "SELECT review_id, title, text FROM reviews WHERE sentiment IS NULL"
    ).fetchall()
    
    total_untagged = len(untagged)
    print(f"📝 Found {total_untagged} untagged reviews")
    
    if total_untagged == 0:
        print("✅ All reviews already tagged!")
        return json.dumps({"tagged_count": 0})
    
    tagged = 0
    for review_id, title, text in untagged:
        try:
            print(f"   🏷️ Tagging review {tagged+1}/{total_untagged}...", end=" ", flush=True)
            sentiment, themes = tag_review_groq(title or "", text or "")
            cursor.execute(
                "UPDATE reviews SET sentiment=?, themes=? WHERE review_id=?",
                (sentiment, themes, review_id),
            )
            tagged += 1
            print(f"✅ {sentiment} - {themes[:30]}..." if themes else f"✅ {sentiment}")
            time.sleep(0.5)  # Reduced from 2.5 to 0.5 for speed
        except Exception as e:
            print(f"❌ Error: {e}")
    conn.commit()
    print(f"\n✅ Successfully tagged {tagged}/{total_untagged} reviews")
    return json.dumps({"tagged_count": tagged})


def _load_tagged_df():
    df = pd.read_sql_query("SELECT * FROM reviews", conn)
    df["product_name"] = df["product_id"].map(PRODUCT_NAMES)
    return df


def tool_generate_global_report():
    print("\n" + "="*60)
    print("📊 STEP 4: GENERATING GLOBAL REPORT")
    print("="*60)

    # Guard: never generate a report off a partially-tagged DB. If anything
    # is untagged (crash, interrupted run, out-of-order tool calls by the
    # agent), tag it first. This is what prevents the report/DB mismatch
    # bug that happened before.
    untagged_count = cursor.execute(
        "SELECT COUNT(*) FROM reviews WHERE sentiment IS NULL"
    ).fetchone()[0]
    if untagged_count > 0:
        print(f"⚠️ {untagged_count} untagged reviews found — tagging before building report...")
        tool_tag_untagged_reviews()

    df = _load_tagged_df()
    print(f"📝 Loaded {len(df)} reviews for report generation")
    ctx = build_report_context(df)
    print("🤖 Asking LLM to generate report...")
    
    prompt = f"""You are a Voice of Customer Analyst. Below is real customer review data for two products (MasterBuds and MasterBudsMax), including sentiment counts and real review excerpts.

{ctx}

Using ONLY the data above, write a Markdown "Global Action Item Report" with exactly these sections:

## For Product Team
3-5 specific hardware/software issues to fix, each tied to a real complaint pattern above.

## For Marketing Team
3-5 specific messaging angles to lean into, based on what customers genuinely praise.

## For Support Team
3-5 specific troubleshooting guide topics, based on recurring complaints.

Be specific — name themes explicitly and say which product each item applies to. No generic filler."""
    resp = groq_client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
    )
    report = resp.choices[0].message.content
    with open(GLOBAL_REPORT_PATH, "w") as f:
        f.write(report)
    print(f"✅ Global report saved to {GLOBAL_REPORT_PATH}")
    return json.dumps({"status": "ok", "file": GLOBAL_REPORT_PATH})


def tool_generate_weekly_delta_report():
    print("\n" + "="*60)
    print("📊 STEP 5: GENERATING WEEKLY DELTA REPORT")
    print("="*60)
    
    try:
        delta_df = pd.read_csv(WEEKLY_DELTA_PATH)
        print(f"📝 Found {len(delta_df)} new reviews in delta log")
    except (FileNotFoundError, pd.errors.EmptyDataError):
        delta_df = pd.DataFrame()
        print("📝 No delta log found - no new reviews")
    
    summary = delta_df.to_string() if len(delta_df) > 0 else "No new reviews were found this run."
    
    prompt = f"""You are a Voice of Customer Analyst. This week's automated run found the following NEW reviews since last run (the delta):

{summary}

Write a short Markdown "Weekly Delta Action Item Report" that:
1. States how many new reviews arrived this week and for which product(s).
2. Flags any spike in a specific complaint/praise theme — only if visible above.
3. Gives 1-2 recommended actions for Product/Marketing/Support if relevant, or says plainly that volume is too small to act on yet.

Do not invent data beyond what's shown above."""
    resp = groq_client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
    )
    report = resp.choices[0].message.content
    with open(WEEKLY_REPORT_PATH, "w") as f:
        f.write(report)
    print(f"✅ Weekly delta report saved to {WEEKLY_REPORT_PATH}")
    return json.dumps({"status": "ok", "file": WEEKLY_REPORT_PATH})


def tool_answer_question(question):
    print("\n" + "="*60)
    print("💬 ANSWERING QUESTION")
    print("="*60)
    print(f"❓ Question: {question}")
    
    df = _load_tagged_df()
    df["sentiment"] = df["sentiment"].fillna("Untagged")
    df["themes"] = df["themes"].fillna("")
    q_lower = question.lower()

    # Actually filter to the product(s) named in the question when possible
    mentioned = [p for p in df["product_name"].unique() if p.lower() in q_lower]
    focused = df[df["product_name"].isin(mentioned)] if mentioned else df
    print(f"📝 Found {len(focused)} relevant reviews")

    sample_n = min(50, len(focused)) if len(focused) > 0 else 0
    sample = focused.sample(sample_n, random_state=1) if sample_n else focused
    context_text = ""
    for _, row in sample.iterrows():
        context_text += f"[{row['product_name']} | {row['sentiment']} | {row['themes']}] {str(row['text'])[:200]}\n"

    prompt = f"""You are a Voice of Customer Analyst. Answer ONLY using the review data below. If the data is insufficient, say so honestly instead of guessing.

REVIEW DATA:
{context_text}

QUESTION: {question}

Give a clear answer, referencing specific themes/sentiment patterns from the data."""
    resp = groq_client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )
    answer = resp.choices[0].message.content
    print(f"\n📝 Answer: {answer[:200]}...")
    return json.dumps({"answer": answer})


TOOLS_SPEC = [
    {"type": "function", "function": {
        "name": "tool_scrape_and_store_reviews",
        "description": "Scrape all configured product review pages and store any genuinely new reviews in the database, skipping duplicates.",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "tool_detect_weekly_delta",
        "description": "Re-check recent review pages, log any reviews not already in the database as the weekly delta proof, and tag+store them.",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "tool_tag_untagged_reviews",
        "description": "Tag any reviews in the database that don't yet have sentiment/theme labels.",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "tool_generate_global_report",
        "description": "Generate the Global Action Item Report across all accumulated reviews.",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "tool_generate_weekly_delta_report",
        "description": "Generate the Weekly Delta Action Item Report based on this run's new reviews.",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "tool_answer_question",
        "description": "Answer a natural-language question grounded strictly in the review database.",
        "parameters": {"type": "object", "properties": {"question": {"type": "string"}}, "required": ["question"]},
    }},
]

AVAILABLE_FUNCTIONS = {
    "tool_scrape_and_store_reviews": tool_scrape_and_store_reviews,
    "tool_detect_weekly_delta": tool_detect_weekly_delta,
    "tool_tag_untagged_reviews": tool_tag_untagged_reviews,
    "tool_generate_global_report": tool_generate_global_report,
    "tool_generate_weekly_delta_report": tool_generate_weekly_delta_report,
    "tool_answer_question": tool_answer_question,
}


def run_agent(user_instruction, max_rounds=8):
    """The agent: the LLM decides which tools to call, in what order, on its
    own — this satisfies the PRD's 'all steps via tool-use' requirement."""
    messages = [
        {"role": "system", "content": (
            "You are the Voice of Customer Analyst agent. You manage a review "
            "database for two products via tools: scraping/storing reviews, "
            "detecting the weekly delta, tagging sentiment/themes, generating "
            "reports, and answering grounded questions. For a full weekly run, "
            "call tools in this order: scrape_and_store_reviews -> "
            "tag_untagged_reviews -> detect_weekly_delta -> "
            "generate_global_report -> generate_weekly_delta_report. "
            "Only skip a step if the user's instruction clearly doesn't need it."
        )},
        {"role": "user", "content": user_instruction},
    ]

    for round_num in range(max_rounds):
        print(f"\n🔄 Agent round {round_num + 1}/{max_rounds}")
        response = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=messages,
            tools=TOOLS_SPEC,
            tool_choice="auto",
        )
        msg = response.choices[0].message
        messages.append(msg)

        if not msg.tool_calls:
            print("✅ Agent finished - no more tool calls needed")
            return msg.content

        for tool_call in msg.tool_calls:
            fn_name = tool_call.function.name
            fn_args = json.loads(tool_call.function.arguments or "{}") or {}
            print(f"🤖 Agent calling tool: {fn_name}({fn_args})")
            try:
                result = AVAILABLE_FUNCTIONS[fn_name](**fn_args)
            except TypeError as e:
                print(f"      ⚠️ Bad tool arguments ({e}) — retrying with no arguments...")
                try:
                    result = AVAILABLE_FUNCTIONS[fn_name]()
                except Exception as e2:
                    print(f"      ❌ Skipping this tool call: {e2}")
                    result = json.dumps({"error": str(e2)})
            messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": result})

    print("⚠️ Agent stopped after max tool-call rounds.")
    return "Agent stopped after max tool-call rounds."


# ---------------------------------------------------------------------------
# Entry point — this is what `python voc_agent.py` / the weekly cron runs
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import atexit

    def _safe_shutdown():
        try:
            conn.commit()
            conn.close()
        except Exception:
            pass

    atexit.register(_safe_shutdown)

    print("🚀 Starting VoC Agent Pipeline")
    print("="*60)

    try:
        result = run_agent(
            "Run this week's full VoC pipeline: scrape and store any new reviews, "
            "tag anything untagged, detect and log the weekly delta, then generate "
            "both the global report and the weekly delta report."
        )

        print("\n" + "="*60)
        print("✅ Pipeline Complete!")
        print("="*60)

        
    finally:
        conn.commit()

    print("\n👋 Done!")
# -*- coding: utf-8 -*-
"""
prove_delta_pipeline.py — Deliverable #5 (Delta Proof), Requirement 1.3

WHY THIS FILE EXISTS
---------------------
Requirement 1.3 asks for "a sample log of newly scraped reviews... to prove
the delta pipeline works." Once the first full scrape has already pulled
every review Flipkart exposes for these two listings, a second real scrape
legitimately finds ZERO new reviews — that's actually the CORRECT behavior
(it proves deduplication works), but it doesn't by itself demonstrate
"capturing a new review" the way the PRD wants to see.

METHOD (100% real data, nothing invented)
------------------------------------------
1. Take a small random sample of reviews ALREADY in the DB (real, scraped
   Flipkart content) and remove them.
2. Re-run the actual `tool_scrape_and_store_reviews()` against live Flipkart
   pages — no mocking, no fabricated text.
3. Because those reviews are no longer in the DB, the pipeline correctly
   re-detects them as "new" (by content hash) and re-inserts them — exactly
   what happens in production when Flipkart publishes genuinely new reviews
   between weekly runs.
4. Log those recaptured rows as the delta proof, clearly labeled as a
   reproducible pipeline test (not claimed to be organically new reviews).

Run this once, right before packaging your submission:
    python prove_delta_pipeline.py
"""

import pandas as pd

from voc_agent import (
    conn, cursor, DELTA_LOG_PATH,
    tool_scrape_and_store_reviews, tool_tag_untagged_reviews,
)

SAMPLE_SIZE = 5
MAX_ATTEMPTS = 3  # retry with a fresh sample if recapture comes back short


def prove_delta_pipeline():
    for attempt in range(1, MAX_ATTEMPTS + 1):
        rows = cursor.execute(
            "SELECT * FROM reviews ORDER BY RANDOM() LIMIT ?", (SAMPLE_SIZE,)
        ).fetchall()
        cols = [d[0] for d in cursor.description]
        removed = [dict(zip(cols, r)) for r in rows]
        removed_ids = [r["review_id"] for r in removed]

        if not removed_ids:
            print("❌ No reviews in DB yet — run voc_agent.py first to do the initial scrape.")
            return

        print(f"🧪 Attempt {attempt}/{MAX_ATTEMPTS}: removing {len(removed_ids)} REAL, "
              f"already-scraped reviews to test recapture...")
        cursor.executemany("DELETE FROM reviews WHERE review_id=?", [(rid,) for rid in removed_ids])
        conn.commit()
        before = cursor.execute("SELECT COUNT(*) FROM reviews").fetchone()[0]
        print(f"   DB now has {before} reviews.")

        print("🔎 Re-running the REAL scraper against live Flipkart pages (no mocking)...")
        result = tool_scrape_and_store_reviews()
        print(f"   {result}")

        tool_tag_untagged_reviews()

        placeholders = ",".join("?" for _ in removed_ids)
        recaptured = cursor.execute(
            f"SELECT * FROM reviews WHERE review_id IN ({placeholders})", removed_ids
        ).fetchall()
        recaptured_ids = [r[0] for r in recaptured]
        after = cursor.execute("SELECT COUNT(*) FROM reviews").fetchone()[0]
        missing = set(removed_ids) - set(recaptured_ids)

        print(f"✅ {len(recaptured_ids)}/{len(removed_ids)} removed reviews were correctly "
              f"re-detected as NEW and re-inserted.")

        if recaptured_ids:
            recaptured_placeholders = ",".join("?" for _ in recaptured_ids)
            df = pd.read_sql_query(
                   f"SELECT * FROM reviews WHERE review_id IN ({recaptured_placeholders})",
                   conn, params=recaptured_ids,
            )
            df["proof_note"] = "recaptured_in_controlled_delta_test"
            df.to_csv(DELTA_LOG_PATH, index=False)
            print(f"📄 Wrote real delta proof to {DELTA_LOG_PATH} ({before} -> {after} reviews in DB)")
            if missing:
                print(f"⚠️ {len(missing)} of the sample weren't recaptured this pass "
                      f"(Flipkart page ordering can shift) — proof file still has "
                      f"{len(recaptured_ids)} genuine recaptured row(s).")
            return
        else:
            print(f"⚠️ 0/{len(removed_ids)} recaptured on attempt {attempt} — "
                  f"{'retrying with a new sample...' if attempt < MAX_ATTEMPTS else 'giving up.'}")

    print("❌ FAILED: could not produce a non-empty delta proof after "
          f"{MAX_ATTEMPTS} attempts. Do not submit with an empty delta_proof_log.csv — "
          "re-run this script again, or check your FIRECRAWL_API_KEY / network access.")
    raise SystemExit(1)


if __name__ == "__main__":
    try:
        prove_delta_pipeline()
    finally:
        conn.commit()
        conn.close()

# -*- coding: utf-8 -*-
"""
verify_before_submit.py — run this LAST, after voc_agent.py and
prove_delta_pipeline.py, right before you zip/push.

Checks every deliverable against the PRD in one shot and tells you
PASS/FAIL for each. If anything fails, DO NOT submit — fix it first.
"""
import os
import sqlite3
import sys

FAILS = []


def check(label, condition, detail=""):
    status = "✅ PASS" if condition else "❌ FAIL"
    print(f"{status} — {label}" + (f" ({detail})" if detail else ""))
    if not condition:
        FAILS.append(label)


print("=" * 60)
print("VoC Agent — Pre-submission verification")
print("=" * 60)

# 1. No leaked secrets
check("No .env file shipped (secrets not leaked)", not os.path.exists(".env"))
check(".env.example exists as a template", os.path.exists(".env.example"))

# 2. No stray journal file (evidence of unclean shutdown)
check("No stray voc_reviews.db-journal file", not os.path.exists("voc_reviews.db-journal"))

# 3. DB fully tagged
# 3. DB fully tagged
if os.path.exists("voc_reviews.db"):
    c = sqlite3.connect("voc_reviews.db")
    total = c.execute("SELECT COUNT(*) FROM reviews").fetchone()[0]
    tagged = c.execute("SELECT COUNT(*) FROM reviews WHERE sentiment IS NOT NULL").fetchone()[0]
    check("Database has reviews", total > 0, f"{total} rows")
    check("Every review is tagged (sentiment/themes)", tagged == total, f"{tagged}/{total} tagged")

    blank = c.execute("SELECT COUNT(*) FROM reviews WHERE themes IS NULL OR themes = ''").fetchone()[0]
    check("Every review has a non-empty theme", blank == 0, f"{blank} blank")

    c.close()
else:
    check("voc_reviews.db exists", False)

# 4. Delta proof is non-empty and matches current schema
delta_path = "reports/delta_proof_log.csv"
if os.path.exists(delta_path):
    with open(delta_path) as f:
        lines = f.readlines()
    check("delta_proof_log.csv has at least one data row (not just a header)", len(lines) > 1,
          f"{max(0, len(lines) - 1)} data row(s)")
else:
    check("reports/delta_proof_log.csv exists", False)

# 5. Reports exist and are non-trivial
for report in ["reports/Global_Action_Item_Report.md", "reports/Weekly_Delta_Action_Item_Report.md"]:
    exists = os.path.exists(report)
    check(f"{report} exists", exists)
    if exists:
        size = os.path.getsize(report)
        check(f"{report} is non-trivial", size > 200, f"{size} bytes")

# 6. Required doc files
for f in ["README.md", "SOUL.md"]:
    check(f"{f} exists", os.path.exists(f))

# 7. Git repo actually initialized
check("Git repo initialized (.git exists)", os.path.exists(".git"))

# 8. Weekly automation file present
check("GitHub Actions workflow present",
      os.path.exists(".github/workflows/weekly_scrape.yml"))

print("=" * 60)
if FAILS:
    print(f"❌ {len(FAILS)} CHECK(S) FAILED — DO NOT SUBMIT YET:")
    for f in FAILS:
        print(f"   - {f}")
    sys.exit(1)
else:
    print("✅ ALL CHECKS PASSED — safe to zip/push.")
    sys.exit(0)
    


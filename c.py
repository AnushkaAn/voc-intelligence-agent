import sqlite3
conn = sqlite3.connect('voc_reviews.db')
c = conn.cursor()
c.execute("UPDATE reviews SET themes = 'General/Other' WHERE themes = '' AND sentiment IS NOT NULL")
conn.commit()
print("Fixed:", c.rowcount)

print(c.execute("SELECT COUNT(*) FROM reviews WHERE themes = ''").fetchone())

blank = c.execute("SELECT COUNT(*) FROM reviews WHERE themes IS NULL OR themes = ''").fetchone()[0]
check("Every review has a non-empty theme", blank == 0, f"{blank} blank")
from signaldesk import collect
from signaldesk.profile import DEFAULT_PREFS

from conftest import add_company, greenhouse

GH = "https://boards-api.greenhouse.io/v1/boards/fixture/jobs"


def run(engine, cid):
    company = engine.db.one("SELECT * FROM companies WHERE id = ?", (cid,))
    return collect.collect_company(engine.db, engine.fetcher, company, DEFAULT_PREFS)


def test_new_changed_and_no_longer_listed(engine, boards):
    db = engine.db
    cid = add_company(db)
    boards.routes[GH] = (200, greenhouse([{"id": 1, "title": "Product Analyst"}, {"id": 2, "title": "Solutions Engineer"}]))
    assert run(engine, cid)["new"] == 2
    # Job 1 edited, job 2 removed.
    boards.routes[GH] = (200, greenhouse([{"id": 1, "title": "Product Analyst", "content": "<p>Requirements: SQL and Python</p>"}]))
    r = run(engine, cid)
    assert (r["changed"], r["closed"]) == (1, 1)
    j1 = db.one("SELECT * FROM jobs WHERE ext_id = 'gh:1'")
    assert j1["change_state"] == "changed" and db.scalar("SELECT COUNT(*) FROM job_versions WHERE job_id = ?", (j1["id"],)) == 1
    assert db.one("SELECT listing_state FROM jobs WHERE ext_id = 'gh:2'")["listing_state"] == "no_longer_listed"
    # The published date comes from the source; first seen is ours and does not move.
    assert j1["published_at"].startswith("2026-10-30") and j1["first_seen_at"] != j1["published_at"]


def test_failed_fetch_closes_nothing(engine, boards):
    db = engine.db
    cid = add_company(db)
    boards.routes[GH] = (200, greenhouse([{"id": i, "title": f"Product Analyst {i}"} for i in range(5)]))
    run(engine, cid)
    boards.routes[GH] = (500, {"error": "down"})
    r = run(engine, cid)
    assert "error" in r
    assert db.scalar("SELECT COUNT(*) FROM jobs WHERE listing_state = 'open'") == 5
    assert db.one("SELECT last_error FROM companies WHERE id = ?", (cid,))["last_error"]


def test_suspicious_empty_board_closes_nothing(engine, boards):
    db = engine.db
    cid = add_company(db)
    boards.routes[GH] = (200, greenhouse([{"id": i, "title": f"Product Analyst {i}"} for i in range(4)]))
    run(engine, cid)
    boards.routes[GH] = (200, {"jobs": []})
    r = run(engine, cid)
    assert "warning" in r and db.scalar("SELECT COUNT(*) FROM jobs WHERE listing_state = 'open'") == 4


def test_duplicate_listings_are_marked(engine, boards):
    db = engine.db
    cid = add_company(db)
    boards.routes[GH] = (200, greenhouse([{"id": 1, "title": "Product Analyst"}, {"id": 2, "title": "Product Analyst"}, {"id": 3, "title": "Product Analyst", "location": "Remote - US"}]))
    run(engine, cid)
    dups = db.all("SELECT ext_id, duplicate_of FROM jobs ORDER BY id")
    assert [d["duplicate_of"] is not None for d in dups] == [False, True, False]


def test_manual_import_keeps_original_url_and_dedupes(engine):
    r = collect.import_job(engine.db, None, DEFAULT_PREFS, url="https://jobs.example.com/123", text="Requirements: SQL", employer="Example", title="Product Analyst", location="Bengaluru")
    assert r["result"] == "added"
    j = engine.db.one("SELECT * FROM jobs WHERE id = ?", (r["id"],))
    assert j["official_url"] == "https://jobs.example.com/123" and j["source"] == "manual" and j["bucket"] == "candidate"
    assert collect.import_job(engine.db, None, DEFAULT_PREFS, url="https://jobs.example.com/123", text="x", title="y")["result"] == "already saved"


def test_manual_import_from_page_uses_jobposting(engine, boards):
    page = ('<html><head><title>Job</title><script type="application/ld+json">{"@type":"JobPosting","title":"AI Solutions Consultant",'
            '"description":"<p>Requirements: consulting</p>","hiringOrganization":{"name":"Example Ltd"},"jobLocation":{"address":{"addressLocality":"Bengaluru"}},'
            '"datePosted":"2026-10-01"}</script></head><body>x</body></html>')
    boards.routes["https://careers.example.com/robots.txt"] = (404, "")
    boards.routes["https://careers.example.com/job/9"] = (200, page)
    r = collect.import_job(engine.db, engine.fetcher, DEFAULT_PREFS, url="https://careers.example.com/job/9")
    j = engine.db.one("SELECT * FROM jobs WHERE id = ?", (r["id"],))
    assert (j["title"], j["employer"], j["location_class"], j["published_at"]) == ("AI Solutions Consultant", "Example Ltd", "bengaluru", "2026-10-01")


FEED = """<?xml version="1.0"?><rss version="2.0"><channel><title>T</title>
<item><title>How we built an AI support assistant</title><link>https://blog.example.com/p/one?utm_source=rss</link><guid>1</guid>
<description><![CDATA[<p>Short preview.</p><p>Keep reading with a 7-day free trial</p>]]></description></item>
<item><title>How We Built an AI Support Assistant!</title><link>https://mirror.example.net/one</link><guid>2</guid><description>Same story</description></item>
</channel></rss>"""


def test_feed_excerpt_and_syndicated_duplicates(engine, boards):
    db = engine.db
    sid = db.insert("reading_sources", {"name": "Blog", "feed_url": "https://blog.example.com/feed", "kind": "substack", "enabled": 1, "created_at": "x"})
    boards.routes["https://blog.example.com/feed"] = (200, FEED)
    r = collect.collect_source(db, engine.fetcher, db.one("SELECT * FROM reading_sources WHERE id = ?", (sid,)), 10)
    assert (r["new"], r["duplicate"]) == (1, 1)
    first = db.one("SELECT * FROM articles ORDER BY id LIMIT 1")
    assert first["content_basis"] == "excerpt" and "utm_source" not in first["url"]
    # Re-reading the same feed creates nothing new.
    assert collect.collect_source(db, engine.fetcher, db.one("SELECT * FROM reading_sources WHERE id = ?", (sid,)), 10)["new"] == 0

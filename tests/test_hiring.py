"""Hiring companies: built from the same job records as Jobs. Synthetic data only; no network."""
from fastapi.testclient import TestClient

from signaldesk import funding, hiring, jobrules, sweep
from signaldesk.collect import upsert_job
from signaldesk.db import now_iso
from signaldesk.server import create_app
from signaldesk.sources import web
from tests.conftest import add_company

ELIGIBLE_SQL = ("SELECT COUNT(*) FROM jobs WHERE listing_state = 'open' AND duplicate_of IS NULL "
                "AND location_class IN ('bengaluru', 'remote_india')")


def job(engine, company_id, employer, n, title, location, source="greenhouse"):
    upsert_job(engine.db, {"ext_id": f"t{n}", "title": title, "location": location, "workplace": None,
                           "description_text": f"{title}. Requirements: SQL.", "official_url": f"https://jobs.example.com/{n}",
                           "apply_url": f"https://jobs.example.com/{n}/apply", "published_at": None, "salary_extra": None},
               company_id=company_id, employer=employer, source=source, prefs=engine.profiles.prefs(), now=now_iso())
    return engine.db.scalar("SELECT id FROM jobs WHERE ext_id = ?", (f"t{n}",))


def seed(engine):
    db = engine.db
    # 1. An employer with no funding record, hiring across several role families.
    acme = add_company(db, "Acme Analytics (synthetic)", "acme")
    db.update("companies", acme, {"last_success_at": now_iso()})
    titles = ["Chief of Staff", "Business Operations Manager", "Product Analyst", "Software Engineer"]
    acme_ids = [job(engine, acme, "Acme Analytics (synthetic)", i, t, "Bengaluru, India") for i, t in enumerate(titles)]
    db.run("UPDATE jobs SET status = 'Interested' WHERE id = ?", (acme_ids[0],))         # a saved job
    # 2. A portfolio startup with a round from years ago, tied to a tracked employer.
    old = add_company(db, "Oldline Labs (synthetic)", "oldline")
    db.update("companies", old, {"last_success_at": now_iso()})
    job(engine, old, "Oldline Labs (synthetic)", 10, "Strategy Associate", "Remote - India")
    sid = funding.upsert_startup(db, "Oldline Labs (synthetic)", watch_source="yc_companies_india", watch_url="https://yc.example/companies/oldline")
    db.update("startups", sid, {"company_id": old})
    funding.save_event(db, sid, investor="Sequoia (synthetic)", round_="seed", amount="$1M", announced_on="2019-03-01",
                       url="https://news.example/oldline-seed", title="Oldline raises seed", source="manual")
    # 3. A company with only closed or geographically ineligible roles.
    far = add_company(db, "Faraway Corp (synthetic)", "faraway")
    db.update("companies", far, {"last_success_at": now_iso()})
    job(engine, far, "Faraway Corp (synthetic)", 20, "Strategy Manager", "Remote - US")
    closed = job(engine, far, "Faraway Corp (synthetic)", 21, "Chief of Staff", "Bengaluru, India")
    db.run("UPDATE jobs SET listing_state = 'no_longer_listed' WHERE id = ?", (closed,))
    # 4. A board that could not be checked, and an untracked employer from a listing site.
    broken = add_company(db, "Broken Board Co (synthetic)", "broken")
    db.update("companies", broken, {"last_error": "HTTP 500 from boards-api.greenhouse.io", "last_error_at": now_iso()})
    job(engine, None, "Listing Only Ltd (synthetic)", 30, "Founder's Office Associate", "Bengaluru", source="yc_jobs")
    # 5. A discovered startup whose careers page has not been found.
    lone = funding.upsert_startup(db, "Lonely Startup (synthetic)", watch_source="westbridge_portfolio")
    return {"acme": acme, "old": old, "far": far, "broken": broken, "sid": sid, "lone": lone, "acme_ids": acme_ids}


def by_name(res):
    return {c["name"].split(" (")[0]: c for c in res["companies"]}


def test_counts_match_the_jobs_records(engine):
    seed(engine)
    db = engine.db
    res = hiring.companies(db, engine.cfg.home)
    employers = db.scalar("SELECT COUNT(DISTINCT COALESCE('c' || company_id, 'e' || lower(employer))) FROM jobs WHERE listing_state = 'open' "
                          "AND duplicate_of IS NULL AND location_class IN ('bengaluru', 'remote_india')")
    assert res["counts"]["openings"] == db.scalar(ELIGIBLE_SQL) == 6
    assert res["counts"]["hiring"] == employers == 3
    rows = by_name(res)
    assert set(rows) == {"Acme Analytics", "Oldline Labs", "Listing Only Ltd"}
    assert rows["Acme Analytics"]["openings"] == 4 and rows["Acme Analytics"]["shortlisted"] == 1
    assert len(rows["Acme Analytics"]["preview"]) == 3
    assert len(rows["Acme Analytics"]["families"]) >= 3                          # hiring across several families
    assert rows["Acme Analytics"]["investors"] == []                              # no funding record, still listed


def test_old_portfolio_startup_and_unknown_backing(engine):
    ids = seed(engine)
    res = by_name(hiring.companies(engine.db, engine.cfg.home))
    old = res["Oldline Labs"]
    assert old["openings"] == 1 and old["latest_round"]["announced_on"] == "2019-03-01"   # funded years ago, still listed
    assert set(old["investors"]) == {"Y Combinator", "Sequoia (synthetic)"}
    yc = by_name(hiring.companies(engine.db, engine.cfg.home, backing="investor:Y Combinator"))
    assert set(yc) == {"Oldline Labs"}
    unknown = by_name(hiring.companies(engine.db, engine.cfg.home, backing="unknown"))
    assert "Oldline Labs" not in unknown and "Acme Analytics" in unknown
    detail = hiring.company(engine.db, engine.cfg.home, f"s{ids['sid']}")      # an old startup link opens the employer
    assert detail["key"] == f"c{ids['old']}" and detail["openings"][0]["apply_url"].startswith("https://jobs.example.com/")


def test_role_families_multi_select_and_unclassified(engine):
    seed(engine)
    fam = {t: jobrules.role_family(t) for t in ("Chief of Staff", "Business Operations Manager", "Software Engineer")}
    pick = sorted({fam["Chief of Staff"], fam["Business Operations Manager"]})
    res = hiring.companies(engine.db, engine.cfg.home, families=pick)
    acme = by_name(res)["Acme Analytics"]
    assert acme["openings"] == 2 and acme["openings_all_families"] == 4
    assert res["counts"]["openings_unfiltered"] == 6
    if fam["Software Engineer"] in hiring.UNCLASSIFIED:                       # unclassified roles are under "other"
        assert by_name(hiring.companies(engine.db, engine.cfg.home, families=["other"]))["Acme Analytics"]["openings"] == 1


def test_states_tell_no_eligible_apart_from_could_not_check(engine):
    seed(engine)
    allc = by_name(hiring.companies(engine.db, engine.cfg.home, view="all"))
    far = allc["Faraway Corp"]
    assert far["state"] == "no_eligible" and far["other_open"] == 1 and far["closed"] == 1 and far["openings"] == 0
    assert allc["Broken Board Co"]["state"] == "unchecked" and allc["Broken Board Co"]["board"]["state"] == "failed"
    assert allc["Lonely Startup"]["state"] == "unchecked" and allc["Lonely Startup"]["investors"] == ["WestBridge Capital"]
    assert "Faraway Corp" not in by_name(hiring.companies(engine.db, engine.cfg.home))      # not under Hiring now


def test_api_and_failed_refresh_keeps_records(engine, boards):
    ids = seed(engine)
    c = TestClient(create_app(engine))
    r = c.get("/api/hiring").json()
    assert r["counts"]["openings"] == 6 and "refresh" in r
    assert c.get("/api/hiring?families=" + jobrules.role_family("Chief of Staff")).status_code == 200
    before = engine.db.one("SELECT last_success_at FROM companies WHERE id = ?", (ids["acme"],))["last_success_at"]
    boards.routes["https://boards-api.greenhouse.io/v1/boards/acme/jobs"] = (500, "down")
    res = c.post(f"/api/hiring/company/refresh?key=c{ids['acme']}").json()
    assert res["ok"] is False and res["error"]
    assert res["company"]["board"]["state"] == "failed" and res["company"]["board"]["last_success_at"] == before
    assert len(res["company"]["openings"]) == 4                                   # saved openings kept
    assert engine.db.scalar("SELECT status FROM jobs WHERE id = ?", (ids["acme_ids"][0],)) == "Interested"   # saved status kept
    assert sweep.agents_for("hiring") == ("funding_scout", "job_scout")


def test_portfolio_pages_with_their_own_company_pages(engine, boards):
    page = ('<a href="/portfolio/alpha-labs">Alpha Labs</a><a href="/portfolio/beta">Beta</a>'
            '<a href="https://login.fund-admin.example/ui">Investor login</a><a href="/portfolio">All</a>')
    boards.routes["https://fund.example/robots.txt"] = (404, "")
    boards.routes["https://fund.example/portfolio/alpha-labs"] = (200, '<a href="https://alphalabs.example/">Alpha Labs</a><a href="https://login.fund-admin.example/">Login</a>')
    boards.routes["https://fund.example/portfolio"] = (200, page)
    cos = web.portfolio(engine.fetcher, "https://fund.example/portfolio")
    assert [c["name"] for c in cos] == ["Alpha Labs", "Beta"]                    # outside login link ignored
    assert web.company_website(engine.fetcher, "https://fund.example/portfolio/alpha-labs", "Alpha Labs") == "https://alphalabs.example"
    assert web.company_website(engine.fetcher, "https://fund.example/portfolio/alpha-labs") is None   # no name, no guess


def test_discovered_startup_links_to_a_tracked_employer(engine):
    db = engine.db
    cid = add_company(db, "Sarvam Synthetic", "sarvam-syn")
    sid = funding.upsert_startup(db, "Sarvam Synthetic", watch_source="yc_companies_india")
    assert funding.link_known_employers(db) == 1
    assert db.scalar("SELECT company_id FROM startups WHERE id = ?", (sid,)) == cid

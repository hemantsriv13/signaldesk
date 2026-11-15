"""Safety properties of signaldesk/contacts.py, checked against invented fixtures only.

Every company and person below is INVENTED for these tests; none is a real business or a real person.

1. A name is stored only with the page that names it.
2. No profile URL is ever guessed.
3. Nothing matches on name alone.
4. Contacts and drafts never reach the cloud snapshot built by delivery.py.
"""
from __future__ import annotations

import json

import httpx
import pytest

from signaldesk import contacts, delivery
from signaldesk.db import now_iso

from conftest import add_company, drain, greenhouse

CO_A, CO_B = "Quillfeather Labs (fixture)", "Brambleway Systems (fixture)"
DOMAIN_A = "quillfeather.example"


def html(body: str) -> str:
    return f"<html><head><title>Invented team page</title></head><body>{body}</body></html>"


def posting_job(engine, boards, *, company=CO_A, board="quill", ext=701, content=None, title="Strategy Manager"):
    cid = add_company(engine.db, company, board)
    engine.db.update("companies", cid, {"careers_url": f"https://{DOMAIN_A}/careers"})
    boards.routes[f"https://boards-api.greenhouse.io/v1/boards/{board}/"] = (200, greenhouse([{
        "id": ext, "title": title, "content": content or "<p>You will report directly to Tamsin Orlowe, Head of Strategy.</p>"}]))
    from signaldesk import collect
    collect.collect_jobs(engine.db, engine.fetcher, engine.profiles.prefs())
    return engine.db.scalar("SELECT id FROM jobs WHERE ext_id = ?", (f"gh:{ext}",))


def all_contacts(db):
    return db.all("SELECT * FROM contacts ORDER BY id")


# ---------------------------------------------------------------- 1. stored only with the page that names it
def test_posting_contact_carries_the_posting_and_the_sentence_that_names_them(engine, boards):
    jid = posting_job(engine, boards)
    contacts.discover_for_job(engine.db, engine.fetcher, jid)
    (c,) = all_contacts(engine.db)
    job = engine.db.one("SELECT official_url, description_text FROM jobs WHERE id = ?", (jid,))
    assert c["name"] == "Tamsin Orlowe" and c["status"] == "verified"
    assert c["evidence_url"] == job["official_url"]
    assert "Tamsin Orlowe" in c["evidence_text"] and c["evidence_text"] in job["description_text"]


def test_team_page_contact_carries_that_page(engine, boards):
    jid = posting_job(engine, boards, content="<p>Own quarterly planning and business reviews.</p>")
    boards.routes[f"https://{DOMAIN_A}/about"] = (200, html("<div><h3>Corwin Ashdale</h3><p>Co-founder and CEO</p></div>"))
    contacts.discover_for_job(engine.db, engine.fetcher, jid)
    (c,) = all_contacts(engine.db)
    assert c["name"] == "Corwin Ashdale" and c["evidence_url"] == f"https://{DOMAIN_A}/about"
    assert "Corwin Ashdale" in c["evidence_text"]


def test_announcement_that_does_not_name_the_company_adds_nobody():
    text = "Fenwick Harrow, co-founder and CEO, said the round will fund hiring."   # no company named
    assert contacts.from_announcement(text, "https://news.example/a", CO_A) == []


def test_every_discovered_contact_has_evidence_naming_them(engine, boards):
    jid = posting_job(engine, boards, content="<p>You will report to Tamsin Orlowe, Head of Strategy. "
                                              "The hiring manager is Ilse Varnow, Director of Operations.</p>")
    boards.routes[f"https://{DOMAIN_A}/about"] = (200, html("<div><h3>Corwin Ashdale</h3><p>Co-founder and CEO</p></div>"))
    contacts.discover_for_job(engine.db, engine.fetcher, jid)
    rows = all_contacts(engine.db)
    assert rows
    for c in rows:
        assert c["evidence_url"].startswith("https://") and c["name"] in c["evidence_text"], c


# ---------------------------------------------------------------- 2. no profile URL is ever guessed
def test_no_profile_url_for_names_without_a_link(engine, boards):
    jid = posting_job(engine, boards)
    boards.routes[f"https://{DOMAIN_A}/about"] = (200, html("<div><h3>Corwin Ashdale</h3><p>Co-founder and CEO</p></div>"))
    contacts.discover_for_job(engine.db, engine.fetcher, jid)
    assert [c["profile_url"] for c in all_contacts(engine.db)] == [None, None]


def test_one_person_on_a_team_page_is_stored_once_under_their_own_name(engine, boards):
    jid = posting_job(engine, boards, content="<p>Own quarterly planning.</p>")
    boards.routes[f"https://{DOMAIN_A}/about"] = (200, html(
        '<div><h3>Corwin Ashdale</h3><p>Co-founder and CEO</p>'
        '<a href="https://www.linkedin.com/in/corwin-ashdale-fixture">LinkedIn</a></div>'))
    contacts.discover_for_job(engine.db, engine.fetcher, jid)
    # Before the fix this also stored "Corwin Ashdale Co", built from "Co-founder" by flattening the page.
    assert [(c["name"], c["profile_url"]) for c in all_contacts(engine.db)] == [
        ("Corwin Ashdale", "https://www.linkedin.com/in/corwin-ashdale-fixture")]


def test_a_neighbours_profile_link_is_never_given_to_someone_else(engine, boards):
    jid = posting_job(engine, boards, content="<p>Own quarterly planning.</p>")
    # Two people side by side. Only the second has a LinkedIn link.
    owner = {"https://www.linkedin.com/in/petra-lindqvane-fixture": "Petra Lindqvane"}
    boards.routes[f"https://{DOMAIN_A}/about"] = (200, html(
        '<div><h3>Corwin Ashdale</h3><p>Co-founder and CEO</p></div>'
        '<div><h3>Petra Lindqvane</h3><p>Head of Product</p>'
        '<a href="https://www.linkedin.com/in/petra-lindqvane-fixture">LinkedIn</a></div>'))
    contacts.discover_for_job(engine.db, engine.fetcher, jid)
    # Before the fix Petra's link was stored on a contact named "Corwin Ashdale Co".
    wrong = [(c["name"], c["profile_url"]) for c in all_contacts(engine.db) if c["profile_url"] and owner[c["profile_url"]] != c["name"]]
    assert wrong == []


def test_every_stored_name_appears_on_its_evidence_page_as_written(engine, boards):
    """Postings, and (since the fix) team pages."""
    jid = posting_job(engine, boards, content="<p>You will report to Tamsin Orlowe, Head of Strategy.</p>")
    contacts.discover_for_job(engine.db, engine.fetcher, jid)
    for c in all_contacts(engine.db):
        assert c["name"] in c["evidence_text"]


def team(engine, boards, body, path="/about", final=None):
    jid = posting_job(engine, boards, content="<p>Own quarterly planning.</p>")
    boards.routes[f"https://{DOMAIN_A}{path}"] = (200, html(body))
    contacts.discover_for_job(engine.db, engine.fetcher, jid)
    return {c["name"]: c for c in all_contacts(engine.db)}


def test_link_before_the_name_in_the_same_card_is_kept(engine, boards):
    got = team(engine, boards, '<div><a href="https://www.linkedin.com/in/corwin-ashdale-fixture">LinkedIn</a><h3>Corwin Ashdale</h3>'
                               '<p>Co-founder and CEO</p></div><div><h3>Petra Lindqvane</h3><p>Head of Product</p></div>')
    assert got["Corwin Ashdale"]["profile_url"] == "https://www.linkedin.com/in/corwin-ashdale-fixture"
    assert got["Petra Lindqvane"]["profile_url"] is None and set(got) == {"Corwin Ashdale", "Petra Lindqvane"}


def test_a_link_in_a_block_naming_several_people_goes_to_nobody(engine, boards):
    got = team(engine, boards, '<div><h3>Corwin Ashdale</h3><p>Co-founder and CEO</p><h3>Petra Lindqvane</h3><p>Head of Product</p>'
                               '<a href="https://www.linkedin.com/in/someone-fixture">LinkedIn</a></div>')
    assert {n: c["profile_url"] for n, c in got.items()} == {"Corwin Ashdale": None, "Petra Lindqvane": None}


def test_customer_quotes_naming_another_company_are_not_team_members(engine, boards):
    """Seen on a real company page: executives of customers quoted on the page were stored as staff."""
    got = team(engine, boards, '<div><p>"It changed how we bill."</p><p>Fenwick Harrow, Founder and CEO, Otherco</p></div>'
                               '<div><h3>Corwin Ashdale</h3><p>Co-founder and CEO</p></div>')
    assert set(got) == {"Corwin Ashdale"}


def test_a_team_address_that_redirects_elsewhere_is_ignored(engine, boards, monkeypatch):
    """Seen on a real company: /about redirected to the home page, whose quotes were read as the team."""
    jid = posting_job(engine, boards, content="<p>Own quarterly planning.</p>")
    boards.routes[f"https://{DOMAIN_A}/"] = (200, html("<div><h3>Corwin Ashdale</h3><p>Co-founder and CEO</p></div>"))
    real = contacts.web.article
    # The fetcher follows redirects and reports the final address; this page answers /about from the home page.
    monkeypatch.setattr(contacts.web, "article", lambda f, url: {**real(f, f"https://{DOMAIN_A}/"), "url": f"https://{DOMAIN_A}/"})
    contacts.discover_for_job(engine.db, engine.fetcher, jid)
    assert all_contacts(engine.db) == []


def test_manual_entry_keeps_only_what_you_typed(engine):
    cid = contacts.add_manual(engine.db, job_id=None, startup_id=None, company=CO_A, name="Odile Ferncastle")
    c = engine.db.one("SELECT * FROM contacts WHERE id = ?", (cid,))
    assert c["profile_url"] is None and c["status"] == "unresolved"
    with pytest.raises(ValueError):
        contacts.add_manual(engine.db, job_id=None, startup_id=None, company=CO_A, name="Odile Ferncastle", profile_url="http://example.com/x")


def test_drafts_never_contain_a_link_that_was_not_stored(engine, boards):
    jid = posting_job(engine, boards)
    (cid,) = contacts.discover_for_job(engine.db, engine.fetcher, jid)["contact_ids"]
    oid = contacts.ensure_draft(engine.db, cid, engine.profiles.profile(), None)
    o = engine.db.one("SELECT note_text, message_text FROM outreach WHERE id = ?", (oid,))
    assert "linkedin.com" not in (o["note_text"] + (o["message_text"] or "")).lower()


# ---------------------------------------------------------------- 3. nothing matches on name alone
def test_same_name_at_two_companies_stays_two_people(engine):
    a = contacts.add_manual(engine.db, job_id=None, startup_id=None, company=CO_A, name="Tamsin Orlowe")
    b = contacts.add_manual(engine.db, job_id=None, startup_id=None, company=CO_B, name="Tamsin Orlowe")
    assert a != b
    keys = {r["recipient_key"] for r in all_contacts(engine.db)}
    assert len(keys) == 2


def test_same_name_on_two_companies_jobs_is_never_merged_or_linked(engine, boards):
    ja = posting_job(engine, boards)
    jb = posting_job(engine, boards, company=CO_B, board="bramble", ext=702)
    contacts.discover_for_job(engine.db, engine.fetcher, ja)
    contacts.discover_for_job(engine.db, engine.fetcher, jb)
    rows = all_contacts(engine.db)
    assert len(rows) == 2 and {r["company"] for r in rows} == {CO_A, CO_B}
    assert len({r["recipient_key"] for r in rows}) == 2


def test_a_profile_link_from_one_company_is_never_reused_for_a_namesake_elsewhere(engine):
    contacts.add_manual(engine.db, job_id=None, startup_id=None, company=CO_A, name="Tamsin Orlowe",
                        profile_url="https://www.linkedin.com/in/tamsin-orlowe-fixture")
    cid = contacts.add_manual(engine.db, job_id=None, startup_id=None, company=CO_B, name="Tamsin Orlowe")
    assert engine.db.scalar("SELECT profile_url FROM contacts WHERE id = ?", (cid,)) is None


# ---------------------------------------------------------------- 4. never in the cloud snapshot
class Recorder:
    def __init__(self):
        self.bodies: list[str] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.bodies.append(request.content.decode())
        return httpx.Response(201, json={})


def test_contacts_and_drafts_never_reach_the_cloud_payload(engine, boards, fake_model):
    engine.cfg.experimental.contacts = True
    jid = posting_job(engine, boards)
    engine.db.update("jobs", jid, {"status": "Interested"})
    cid = contacts.add_manual(engine.db, job_id=jid, startup_id=None, company=CO_A, name="Odile Ferncastle",
                              profile_url="https://www.linkedin.com/in/odile-ferncastle-fixture")
    (found,) = contacts.discover_for_job(engine.db, engine.fetcher, jid)["contact_ids"]
    for c in (cid, found):
        contacts.ensure_draft(engine.db, c, engine.profiles.profile(), None)
    secrets = ["Odile Ferncastle", "Tamsin Orlowe", "odile-ferncastle-fixture"]
    secrets += [r["note_text"] for r in engine.db.all("SELECT note_text FROM outreach")]
    assert len(secrets) == 5

    run = engine.start_run("digest_editor")["id"]
    for _ in range(100):
        if engine.db.scalar("SELECT status FROM runs WHERE id = ?", (run,)) not in ("collecting",):
            break
        import time
        time.sleep(0.05)
    drain(engine)
    row = engine.db.one("SELECT * FROM digests ORDER BY id DESC LIMIT 1")
    assert row, "a briefing was composed"
    assert any(j["id"] == jid for j in json.loads(row["content_json"])["jobs"]), "the job with contacts is in the briefing"

    snap = json.dumps(delivery.public_snapshot(json.loads(row["content_json"]), include_manual=True))
    rec = Recorder()
    d = delivery.Delivery(engine, env={"SIGNALDESK_SUPABASE_URL": "https://cloud.fixture.example",
                                       "SIGNALDESK_SUPABASE_SERVICE_KEY": "sb_secret_fixture",
                                       "SIGNALDESK_OWNER_ID": "00000000-0000-0000-0000-000000000001",
                                       "SIGNALDESK_SYNC_MANUAL_IMPORTS": "true"},
                          client=httpx.Client(transport=httpx.MockTransport(rec.handler)))
    d.tick()
    assert rec.bodies, "the payload was built and handed to the (mock) cloud"
    for text in [snap, *rec.bodies]:
        for s in secrets:
            assert s not in text, s
        assert "contact" not in text.lower() and "outreach" not in text.lower()


def test_snapshot_drops_contact_fields_even_if_a_briefing_carried_them():
    content = {"generated_at": now_iso(), "model_id": "m", "notes": [], "quiet": False, "articles": [], "case": None, "term": None,
               "jobs": [{"type": "job", "id": 1, "title": "Strategy Manager", "subtitle": CO_A, "summary": "s", "original_url": "https://x.example",
                         "badges": [], "match": "unknown", "origin": "board",
                         "contacts": [{"name": "Tamsin Orlowe", "profile_url": "https://www.linkedin.com/in/x"}],
                         "draft": "Hello Tamsin", "outreach": {"state": "drafted"}}]}
    text = json.dumps(delivery.public_snapshot(content))
    assert "Tamsin" not in text and "linkedin" not in text and "drafted" not in text


# ---------------------------------------------------------------- found on real company pages (copy of the data), rebuilt with invented people
def test_names_with_initials_and_department_titles_are_found(engine, boards):
    got = team(engine, boards, '<div><h3>Ravindran K S</h3><p>Co-founder and CTO</p></div>'
                               '<div><h3>Corwin Ashdale</h3><p>Co-founder, Engineering</p></div>')
    assert {n: c["title"] for n, c in got.items()} == {"Ravindran K S": "Co-Founder And Cto", "Corwin Ashdale": "Co-Founder, Engineering"}


def test_an_about_page_that_moved_is_still_read(engine, boards, monkeypatch):
    """/about redirecting to /company/about-us is the same page under a new address, not the home page."""
    jid = posting_job(engine, boards, content="<p>Own quarterly planning.</p>")
    boards.routes[f"https://{DOMAIN_A}/company/about-us"] = (200, html("<div><h3>Corwin Ashdale</h3><p>Co-founder and CEO</p></div>"))
    real = contacts.web.article
    monkeypatch.setattr(contacts.web, "article", lambda f, url: {**real(f, f"https://{DOMAIN_A}/company/about-us"),
                                                                  "url": f"https://{DOMAIN_A}/company/about-us"})
    contacts.discover_for_job(engine.db, engine.fetcher, jid)
    assert [c["name"] for c in all_contacts(engine.db)] == ["Corwin Ashdale"]


def test_a_country_home_page_counts_as_the_home_page():
    assert contacts._home_page("https://quillfeather.example/in") and contacts._home_page("https://quillfeather.example/en-gb/")
    assert not contacts._home_page("https://quillfeather.example/in/about")


def test_a_careers_page_on_a_job_board_never_sends_discovery_to_the_board_company(engine, boards):
    """jobs.ashbyhq.com/<company> must not turn into ashbyhq.com/about."""
    cid = add_company(engine.db, CO_B, "bramble")
    engine.db.update("companies", cid, {"careers_url": "https://jobs.ashbyhq.com/bramble"})
    boards.routes["https://boards-api.greenhouse.io/v1/boards/bramble/"] = (200, greenhouse([{"id": 990, "title": "Strategy Manager",
                                                                                                 "content": "<p>Own planning.</p>"}]))
    from signaldesk import collect
    collect.collect_jobs(engine.db, engine.fetcher, engine.profiles.prefs())
    jid = engine.db.scalar("SELECT id FROM jobs WHERE ext_id = 'gh:990'")
    res = contacts.discover_for_job(engine.db, engine.fetcher, jid)
    assert res["checked"] == ["posting"] and not [u for u in boards.hits if "ashbyhq.com/" in u and "/about" in u]


def test_team_cards_are_read_even_where_the_article_text_drops_them(engine, boards):
    """On a real page the people section was missing from the article text but present in the page itself."""
    got = team(engine, boards, '<section aria-label="Leadership"><div><div><h3>Corwin Ashdale</h3></div><div><p>Founder &amp; CEO</p></div>'
                               '<a href="https://www.linkedin.com/in/corwin-ashdale-fixture">LinkedIn</a></div></section>')
    assert got["Corwin Ashdale"]["profile_url"] == "https://www.linkedin.com/in/corwin-ashdale-fixture"

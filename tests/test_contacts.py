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


KNOWN = ("KNOWN FAILURE, shown to the owner and not fixed yet: on a team page, the name regex runs across neighbouring "
         "text, and each LinkedIn link goes to the first name in the 160 characters before it.")


@pytest.mark.xfail(strict=True, reason=KNOWN)
def test_one_person_on_a_team_page_is_stored_once_under_their_own_name(engine, boards):
    jid = posting_job(engine, boards, content="<p>Own quarterly planning.</p>")
    boards.routes[f"https://{DOMAIN_A}/about"] = (200, html(
        '<div><h3>Corwin Ashdale</h3><p>Co-founder and CEO</p>'
        '<a href="https://www.linkedin.com/in/corwin-ashdale-fixture">LinkedIn</a></div>'))
    contacts.discover_for_job(engine.db, engine.fetcher, jid)
    # Today this stores "Corwin Ashdale" AND "Corwin Ashdale Co" (from "Co-founder"); the page names one person.
    assert [(c["name"], c["profile_url"]) for c in all_contacts(engine.db)] == [
        ("Corwin Ashdale", "https://www.linkedin.com/in/corwin-ashdale-fixture")]


@pytest.mark.xfail(strict=True, reason=KNOWN)
def test_a_neighbours_profile_link_is_never_given_to_someone_else(engine, boards):
    jid = posting_job(engine, boards, content="<p>Own quarterly planning.</p>")
    # Two people side by side. Only the second has a LinkedIn link.
    owner = {"https://www.linkedin.com/in/petra-lindqvane-fixture": "Petra Lindqvane"}
    boards.routes[f"https://{DOMAIN_A}/about"] = (200, html(
        '<div><h3>Corwin Ashdale</h3><p>Co-founder and CEO</p></div>'
        '<div><h3>Petra Lindqvane</h3><p>Head of Product</p>'
        '<a href="https://www.linkedin.com/in/petra-lindqvane-fixture">LinkedIn</a></div>'))
    contacts.discover_for_job(engine.db, engine.fetcher, jid)
    # Today Petra's link is stored on a contact named "Corwin Ashdale Co".
    wrong = [(c["name"], c["profile_url"]) for c in all_contacts(engine.db) if c["profile_url"] and owner[c["profile_url"]] != c["name"]]
    assert wrong == []


def test_every_stored_name_appears_on_its_evidence_page_as_written(engine, boards):
    """Holds for postings and announcements; the team-page case is the known failure above."""
    jid = posting_job(engine, boards, content="<p>You will report to Tamsin Orlowe, Head of Strategy.</p>")
    contacts.discover_for_job(engine.db, engine.fetcher, jid)
    for c in all_contacts(engine.db):
        assert c["name"] in c["evidence_text"]


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

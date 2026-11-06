import json
import httpx
import pytest
from signaldesk.delivery import Delivery, auth_headers, public_snapshot
from signaldesk.discovery import board_from_url, discover
from signaldesk.netsafe import Response, FetchError
from signaldesk.db import now_iso

ENV = {'SIGNALDESK_SUPABASE_URL': 'https://project.supabase.co', 'SIGNALDESK_SUPABASE_SERVICE_KEY': 'private-service-key',
       'SIGNALDESK_OWNER_ID': '00000000-0000-4000-8000-000000000001'}


def digest(db, **overrides):
    content = {'generated_at': now_iso(), 'jobs': [{'type': 'job', 'id': 1, 'title': 'AI product manager', 'original_url': 'https://company.example/job', 'why': ['PRIVATE PROFILE'], 'summary': 'A role'}],
               'articles': [], 'case': None, 'term': None, 'notes': [], 'profile': 'RAW CV', **overrides}
    return db.insert('digests', {'created_at': now_iso(), 'status': 'saved', 'content_json': json.dumps(content)})


def test_export_excludes_raw_profile_and_local_detail_links():
    content = {'generated_at': now_iso(), 'jobs': [{'title': 'Job', 'type': 'job', 'id': 1, 'why': ['PRIVATE'], 'detail': '#/jobs/1'}], 'profile': 'CV', 'articles': [], 'notes': []}
    out = json.dumps(public_snapshot(content))
    assert 'PRIVATE' not in out and 'CV' not in out and '#/jobs' not in out


def test_failed_cloud_sync_is_reported(engine):
    calls = []
    d = Delivery(engine, env=ENV, client=httpx.Client(transport=httpx.MockTransport(lambda r: (calls.append(r) or httpx.Response(500)))))
    did = digest(engine.db)
    d.tick()
    assert len(calls) == 1
    assert engine.db.get_setting(f'delivery:{did}') is None
    assert engine.db.get_setting('sync_status')['state'] == 'failed'


def test_archived_synced_copy_is_removed(engine):
    calls = []
    d = Delivery(engine, env=ENV, client=httpx.Client(transport=httpx.MockTransport(lambda r: (calls.append(r) or httpx.Response(201, json={})))))
    did = digest(engine.db)
    d.tick()
    engine.db.update('digests', did, {'status': 'archived'})
    d.tick()
    assert calls[-1].method == 'DELETE'
    assert engine.db.get_setting(f'delivery:{did}')['cloud'] == 'removed'


@pytest.mark.parametrize('url,expected', [('https://jobs.lever.co/acme/123', 'lever'), ('https://job-boards.greenhouse.io/acme', 'greenhouse'), ('https://jobs.ashbyhq.com/acme/job', 'ashby'), ('https://jobs.lever.co.evil.example/acme', None)])
def test_board_discovery_matches_exact_hosts(url, expected):
    board = board_from_url(url)
    assert (board['ats'] if board else None) == expected


def test_discovery_respects_robots_and_requires_review():
    class Fetch:
        def get(self, url, **kw):
            assert kw['check_robots']
            return Response(url, 200, {}, b'<a href="https://jobs.ashbyhq.com/acme">Jobs</a>')
    res = discover(Fetch(), 'https://acme.example/careers')
    assert res['boards'][0]['ats_id'] == 'acme'
    assert 'does not prove who owns' in res['note']
    with pytest.raises(FetchError, match='LinkedIn'):
        discover(Fetch(), 'https://www.linkedin.com/jobs')


def test_delivery_not_configured_does_no_network(engine):
    d = Delivery(engine, env={})
    d.tick()
    assert not d.describe()['cloud_configured'] and d.client is None


def test_greenhouse_embed_and_careers_redirect():
    assert board_from_url('https://boards.greenhouse.io/embed/job_board?for=acme')['ats_id'] == 'acme'
    class Redirect:
        def get(self, url, **kw):
            return Response('https://jobs.ashbyhq.com/acme', 200, {}, b'<p>No direct job links in this excerpt.</p>')
    assert discover(Redirect(), 'https://acme.example/careers')['boards'][0]['ats_id'] == 'acme'


def test_sync_uploads_once_and_keeps_secrets_out_of_status(engine):
    calls = []
    d = Delivery(engine, env=ENV, client=httpx.Client(transport=httpx.MockTransport(lambda r: (calls.append(r) or httpx.Response(201, json={})))))
    did = digest(engine.db)
    d.tick(); d.tick()
    assert len(calls) == 1 and 'on_conflict' in str(calls[0].url)
    assert engine.db.get_setting(f'delivery:{did}')['cloud'] == 'synced'
    assert 'private-service-key' not in json.dumps(d.describe())


def test_only_supabase_is_contacted_even_with_old_whatsapp_settings(engine):
    calls = []
    env = {**ENV, 'SIGNALDESK_WHATSAPP_ENABLED': 'true', 'WHATSAPP_ACCESS_TOKEN': 'x', 'WHATSAPP_PHONE_NUMBER_ID': '1', 'WHATSAPP_TO': '919999999999', 'WHATSAPP_TEMPLATE': 't', 'WHATSAPP_GRAPH_VERSION': 'v23.0'}
    d = Delivery(engine, env=env, client=httpx.Client(transport=httpx.MockTransport(lambda r: (calls.append(r) or httpx.Response(201, json={})))))
    digest(engine.db)
    d.tick()
    assert calls and all(r.url.host == 'project.supabase.co' for r in calls)


def test_new_secret_keys_are_not_sent_as_bearer_tokens():
    assert auth_headers('sb_secret_abc') == {'apikey': 'sb_secret_abc'}
    assert auth_headers('legacy.jwt.key')['Authorization'] == 'Bearer legacy.jwt.key'

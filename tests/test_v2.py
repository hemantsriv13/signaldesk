import json
import httpx
import pytest
from signaldesk.delivery import Delivery, public_snapshot, summary_text
from signaldesk.discovery import board_from_url, discover
from signaldesk.netsafe import Response, FetchError
from signaldesk.db import now_iso

ENV = {'SIGNALDESK_SUPABASE_URL': 'https://project.supabase.co', 'SIGNALDESK_SUPABASE_SERVICE_KEY': 'private-service-key',
       'SIGNALDESK_OWNER_ID': '00000000-0000-4000-8000-000000000001', 'SIGNALDESK_WHATSAPP_ENABLED': 'true',
       'WHATSAPP_ACCESS_TOKEN': 'private-meta-token', 'WHATSAPP_PHONE_NUMBER_ID': '123456', 'WHATSAPP_TO': '919999999999',
       'WHATSAPP_TEMPLATE': 'daily_briefing', 'WHATSAPP_GRAPH_VERSION': 'v23.0', 'SIGNALDESK_READER_URL': 'https://reader.example/'}


def digest(db, **overrides):
    content = {'generated_at': now_iso(), 'jobs': [{'type': 'job', 'id': 1, 'title': 'AI product manager', 'original_url': 'https://company.example/job', 'why': ['PRIVATE PROFILE'], 'summary': 'A role'}],
               'articles': [], 'case': None, 'term': None, 'notes': [], 'profile': 'RAW CV', **overrides}
    return db.insert('digests', {'created_at': now_iso(), 'status': 'saved', 'content_json': json.dumps(content)})


def test_export_excludes_raw_profile_and_local_detail_links():
    content = {'generated_at': now_iso(), 'jobs': [{'title': 'Job', 'type': 'job', 'id': 1, 'why': ['PRIVATE'], 'detail': '#/jobs/1'}], 'profile': 'CV', 'articles': [], 'notes': []}
    out = json.dumps(public_snapshot(content))
    assert 'PRIVATE' not in out and 'CV' not in out and '#/jobs' not in out
    assert len(summary_text(public_snapshot(content))) <= 900


def test_sync_idempotent_and_whatsapp_not_repeated(engine):
    calls = []
    def handler(req):
        calls.append(req)
        if 'graph.facebook.com' in str(req.url): return httpx.Response(200, json={'messages': [{'id': 'meta-1'}]})
        return httpx.Response(201, json={})
    delivery = Delivery(engine, env=ENV, client=httpx.Client(transport=httpx.MockTransport(handler)))
    did = digest(engine.db)
    delivery.tick(); delivery.tick()
    assert len(calls) == 2
    assert 'on_conflict' in str(calls[0].url)
    assert engine.db.get_setting(f'delivery:{did}')['whatsapp'] == 'submitted'
    assert 'private-service-key' not in json.dumps(delivery.describe())
    template = json.loads(calls[1].content)['template']
    assert template['components'][1]['parameters'][0]['text'] == engine.db.get_setting(f'delivery:{did}')['remote_id']


def test_historical_digests_sync_without_whatsapp_flood(engine):
    digest(engine.db)
    calls = []
    d = Delivery(engine, env=ENV, client=httpx.Client(transport=httpx.MockTransport(lambda r: (calls.append(r) or httpx.Response(201, json={})))))
    d.tick()
    assert len(calls) == 1 and 'supabase.co' in str(calls[0].url)


def test_ambiguous_whatsapp_submission_not_auto_retried(engine):
    calls = []
    def handler(req):
        calls.append(req)
        if 'graph.facebook.com' in str(req.url): raise httpx.ReadTimeout('maybe accepted')
        return httpx.Response(201, json={})
    d = Delivery(engine, env=ENV, client=httpx.Client(transport=httpx.MockTransport(handler)))
    did = digest(engine.db)
    d.tick(); d.tick()
    assert len(calls) == 2
    assert engine.db.get_setting(f'delivery:{did}')['whatsapp'] == 'submission_unknown'


def test_failed_cloud_sync_does_not_send_whatsapp(engine):
    calls = []
    d = Delivery(engine, env=ENV, client=httpx.Client(transport=httpx.MockTransport(lambda r: (calls.append(r) or httpx.Response(500)))))
    did = digest(engine.db)
    d.tick()
    assert len(calls) == 1
    assert engine.db.get_setting(f'delivery:{did}') is None
    assert engine.db.get_setting('sync_status')['state'] == 'failed'


def test_archived_synced_copy_is_removed(engine):
    calls = []
    env = {**ENV, 'SIGNALDESK_WHATSAPP_ENABLED': 'false'}
    d = Delivery(engine, env=env, client=httpx.Client(transport=httpx.MockTransport(lambda r: (calls.append(r) or httpx.Response(201, json={})))))
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


def test_only_rejected_submissions_can_be_retried(engine):
    replies = [201, 400, 200]
    calls = []
    def handler(req):
        calls.append(req)
        return httpx.Response(replies.pop(0), json={'messages': [{'id': 'accepted'}]})
    d = Delivery(engine, env=ENV, client=httpx.Client(transport=httpx.MockTransport(handler)))
    did = digest(engine.db)
    d.tick()
    assert engine.db.get_setting(f'delivery:{did}')['whatsapp'] == 'rejected'
    d.retry_rejected(did)
    assert len(calls) == 3 and engine.db.get_setting(f'delivery:{did}')['whatsapp'] == 'submitted'
    with pytest.raises(ValueError, match='Only explicitly rejected'):
        d.retry_rejected(did)


def test_greenhouse_embed_and_careers_redirect():
    assert board_from_url('https://boards.greenhouse.io/embed/job_board?for=acme')['ats_id'] == 'acme'
    class Redirect:
        def get(self, url, **kw):
            return Response('https://jobs.ashbyhq.com/acme', 200, {}, b'<p>No direct job links in this excerpt.</p>')
    assert discover(Redirect(), 'https://acme.example/careers')['boards'][0]['ats_id'] == 'acme'


def test_whatsapp_variable_has_no_characters_meta_rejects():
    content = {'jobs': [{'title': 'Lead\n\tPM     AI'}, {'title': 'Second'}], 'articles': [{'title': 'A read'}], 'case': {'title': 'A case'}}
    text = summary_text(content)
    assert '\n' not in text and '\t' not in text and '     ' not in text
    assert 'Lead PM AI' in text and text.startswith('Your SignalDesk briefing')

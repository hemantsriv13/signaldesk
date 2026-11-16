"""Check privacy rules on your live Supabase project, using two real reader accounts.

Reads <data dir>\\delivery.env and <data dir>\\rls-test.env. Neither belongs in Git.
rls-test.env holds READER_A_EMAIL, READER_A_PASSWORD, READER_B_EMAIL and READER_B_PASSWORD.
Reader A must be the SIGNALDESK_OWNER_ID account, and at least one briefing must be synced.
Prints results only, never keys or passwords. Exit code 0 means every check passed.
Add --projects to also check the Project Coach tables (cloud/project_coach.sql).
"""
import os
import sys
from pathlib import Path

import httpx

HOME = Path(os.environ.get('SIGNALDESK_HOME', r'D:\LocalAI\signaldesk'))
TABLE = '/rest/v1/signaldesk_digests'
TASKS = '/rest/v1/signaldesk_project_tasks'
RESPONSES = '/rest/v1/signaldesk_project_responses'
TEST_TASK = '00000000-0000-4000-8000-00000000c0de'      # throwaway row, deleted at the end


def load(path):
    values = {}
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            key, value = line.split('=', 1)
            values[key.strip()] = value.strip()
    return values


def main():
    try:
        cfg = load(HOME / 'delivery.env')
        users = load(HOME / 'rls-test.env')
        url = cfg['SIGNALDESK_SUPABASE_URL'].rstrip('/')
        key = cfg['SIGNALDESK_SUPABASE_ANON_KEY']
        owner = cfg['SIGNALDESK_OWNER_ID']
        a_login = (users['READER_A_EMAIL'], users['READER_A_PASSWORD'])
        b_login = (users['READER_B_EMAIL'], users['READER_B_PASSWORD'])
    except (OSError, KeyError) as exc:
        print(f'Setup incomplete: {exc}')
        return 2

    failures = []

    def check(name, passed, detail=''):
        print(('PASS  ' if passed else 'FAIL  ') + name + (f' ({detail})' if detail else ''))
        if not passed:
            failures.append(name)

    client = httpx.Client(timeout=25, follow_redirects=False)

    def sign_in(login):
        r = client.post(url + '/auth/v1/token', params={'grant_type': 'password'}, headers={'apikey': key},
                        json={'email': login[0], 'password': login[1]})
        if r.status_code == 200:
            return r.json()
        # The error code names the cause and contains no credentials.
        try:
            reason = r.json().get('error_code') or r.json().get('error') or 'unknown'
        except ValueError:
            reason = 'unknown'
        print(f'      Sign-in refused: HTTP {r.status_code}, {reason}')
        return None

    def as_user(session):
        return {'apikey': key, 'Authorization': 'Bearer ' + session['access_token']}

    r = client.get(url + TABLE, params={'select': 'id'}, headers={'apikey': key})
    check('Signed-out request reads no briefings', r.status_code in (401, 403) or (r.status_code == 200 and r.json() == []), f'HTTP {r.status_code}')

    a, b = sign_in(a_login), sign_in(b_login)
    check('Reader A can sign in', bool(a))
    check('Reader B can sign in', bool(b))
    if not a or not b:
        print(f'\n{len(failures)} check(s) failed.')
        return 1
    check('Reader A is the configured owner', a['user']['id'] == owner)

    r = client.get(url + TABLE, params={'select': 'id,owner_id'}, headers=as_user(a))
    rows = r.json() if r.status_code == 200 else []
    check('Reader A reads their synced briefings', bool(rows), f'{len(rows)} found')
    check('Reader A sees only their own rows', all(x['owner_id'] == a['user']['id'] for x in rows))

    r = client.get(url + TABLE, params={'select': 'id'}, headers=as_user(b))
    check('Reader B reads none of them', r.status_code == 200 and r.json() == [], f'HTTP {r.status_code}')
    if rows:
        target = rows[0]['id']
        r = client.get(url + TABLE, params={'select': 'id', 'id': 'eq.' + target}, headers=as_user(b))
        check('Reader B cannot fetch one by its exact ID', r.status_code == 200 and r.json() == [], f'HTTP {r.status_code}')

        # These attempts must change nothing. Each app login is meant to be read-only.
        prefer = {'Prefer': 'return=representation'}
        for label, session in (('A', a), ('B', b)):
            r = client.delete(url + TABLE, params={'id': 'eq.' + target}, headers={**as_user(session), **prefer})
            check(f'Reader {label} cannot delete a briefing', r.status_code in (401, 403) or (r.is_success and r.json() == []), f'HTTP {r.status_code}')
            r = client.patch(url + TABLE, params={'id': 'eq.' + target}, headers={**as_user(session), **prefer}, json={'payload': {}})
            check(f'Reader {label} cannot edit a briefing', r.status_code in (401, 403) or (r.is_success and r.json() == []), f'HTTP {r.status_code}')
        r = client.post(url + TABLE, headers={**as_user(b), **prefer}, json={
            'id': '00000000-0000-4000-8000-00000000abcd', 'owner_id': b['user']['id'],
            'created_at': '2026-01-01T00:00:00Z', 'payload': {}})
        check('Reader B cannot add a briefing', r.status_code in (401, 403), f'HTTP {r.status_code}')
        r = client.get(url + TABLE, params={'select': 'id', 'id': 'eq.' + target}, headers=as_user(a))
        check('The briefing is still there afterwards', r.status_code == 200 and len(r.json()) == 1)

    if '--projects' in sys.argv:
        check_projects(client, url, key, cfg, a, b, as_user, check)

    print('\nAll checks passed.' if not failures else f'\n{len(failures)} check(s) failed.')
    return 1 if failures else 0


def check_projects(client, url, key, cfg, a, b, as_user, check):
    """Project Coach tables. Uses the laptop's server key only to create and remove one throwaway
    task, so the positive answer check never reaches your real reviews."""
    import uuid
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from signaldesk.delivery import auth_headers
    service = auth_headers(cfg['SIGNALDESK_SUPABASE_SERVICE_KEY'])
    owner = a['user']['id']
    print('\nProject Coach tables')
    for table, label in ((TASKS, 'project tasks'), (RESPONSES, 'answers')):
        r = client.get(url + table, params={'select': 'id'}, headers={'apikey': key})
        check(f'Signed-out request reads no {label}', r.status_code in (401, 403) or (r.status_code == 200 and r.json() == []), f'HTTP {r.status_code}')
    r = client.post(url + TASKS, headers={**service, 'Prefer': 'resolution=merge-duplicates'}, params={'on_conflict': 'id'}, json={
        'id': TEST_TASK, 'owner_id': owner, 'day': '2000-01-01', 'project': 'verify-cloud', 'kind': 'label_reply',
        'payload': {'title': 'verify_cloud test task', 'verdicts': ['pass', 'fail', 'unclear']}, 'created_at': '2000-01-01T00:00:00Z'})
    check('Laptop key can write a project task', r.is_success, f'HTTP {r.status_code}')
    if not r.is_success:
        print('      Run cloud/project_coach.sql in the Supabase SQL editor, then try again.')
        return
    prefer = {'Prefer': 'return=representation'}

    def answer(session, verdict='unclear', rid=None, **extra):
        return client.post(url + RESPONSES, headers={**as_user(session), **prefer}, json={
            'id': rid or str(uuid.uuid4()), 'task_id': TEST_TASK, 'verdict': verdict,
            'note': 'verify_cloud test', 'answered_at': '2000-01-01T00:00:00Z', **extra})

    def refused(r):
        return r.status_code in (400, 401, 403) or (r.is_success and r.json() == [])
    try:
        r = client.get(url + TASKS, params={'select': 'id,owner_id'}, headers=as_user(a))
        rows = r.json() if r.status_code == 200 else []
        check('Reader A reads their project tasks', any(x['id'] == TEST_TASK for x in rows))
        check('Reader A sees only their own tasks', all(x['owner_id'] == owner for x in rows))
        r = client.get(url + TASKS, params={'select': 'id', 'id': 'eq.' + TEST_TASK}, headers=as_user(b))
        check("Reader B cannot read A's task", r.status_code == 200 and r.json() == [], f'HTTP {r.status_code}')
        r = client.patch(url + TASKS, params={'id': 'eq.' + TEST_TASK}, headers={**as_user(a), **prefer}, json={'status': 'answered'})
        check('Reader A cannot change a task', refused(r), f'HTTP {r.status_code}')
        check("Reader B cannot answer A's task", refused(answer(b)))
        check('A verdict the task does not allow is refused', refused(answer(a, 'agree')))
        check('Reader A cannot write an answer as someone else', refused(answer(a, owner_id=b['user']['id'])))
        check('Reader A cannot mark an answer as imported', refused(answer(a, imported_at='2000-01-01T00:00:00Z')))
        rid = '00000000-0000-4000-8000-00000000beef'
        r = answer(a, rid=rid)
        check('Reader A can answer their own task', r.status_code == 201, f'HTTP {r.status_code}')
        r = answer(a, rid=rid)
        check('A repeated send of the same answer is refused, not duplicated', r.status_code == 409, f'HTTP {r.status_code}')
        r = answer(a, 'fail')
        check('A second, different answer to the same task is refused', r.status_code == 409, f'HTTP {r.status_code}')
        r = client.patch(url + RESPONSES, params={'id': 'eq.' + rid}, headers={**as_user(a), **prefer}, json={'verdict': 'pass'})
        check('Reader A cannot edit a sent answer', refused(r), f'HTTP {r.status_code}')
        r = client.delete(url + RESPONSES, params={'id': 'eq.' + rid}, headers={**as_user(a), **prefer})
        check('Reader A cannot delete a sent answer', refused(r), f'HTTP {r.status_code}')
        r = client.get(url + RESPONSES, params={'select': 'id', 'id': 'eq.' + rid}, headers=as_user(b))
        check("Reader B cannot read A's answer", r.status_code == 200 and r.json() == [], f'HTTP {r.status_code}')
    finally:
        r = client.delete(url + TASKS, params={'id': 'eq.' + TEST_TASK}, headers=service)
        check('Throwaway task and its answer removed', r.is_success, f'HTTP {r.status_code}')


if __name__ == '__main__':
    sys.exit(main())

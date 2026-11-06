"""Optional outbound cloud snapshots for the private phone reader.

No inbound access to the laptop. Credentials come from environment variables.
"""
import hashlib
import json
import os
import re
import threading
import uuid
from urllib.parse import urlsplit
import httpx
from .db import now_iso


def public_snapshot(content):
    # Export a read-only briefing, not the database, raw CV, or full source texts.
    def item(x):
        return {k: x.get(k) for k in ('type', 'id', 'title', 'subtitle', 'summary', 'original_url', 'badges', 'match')}
    return {'generated_at': content['generated_at'], 'model_id': content.get('model_id'),
            'jobs': [item(x) for x in content.get('jobs', [])],
            'articles': [item(x) for x in content.get('articles', [])],
            'case': item(content['case']) if content.get('case') else None,
            'term': {k: content['term'].get(k) for k in ('term', 'explanation')} if content.get('term') else None,
            'notes': content.get('notes', []), 'quiet': content.get('quiet', False)}


def valid_https(url):
    try:
        p = urlsplit(url)
        return p.scheme == 'https' and bool(p.hostname) and not p.username and not p.password
    except ValueError:
        return False


def auth_headers(key):
    # Supabase's newer sb_secret_ keys are not JWTs, so they go only in the apikey header.
    return {'apikey': key} if key.startswith('sb_') else {'apikey': key, 'Authorization': 'Bearer ' + key}


class Delivery:
    def __init__(self, engine, *, env=None, client=None):
        self.engine, self.db = engine, engine.db
        self.env = dict(os.environ if env is None else env)
        self.client = client
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.thread = threading.Thread(target=self._loop, daemon=True, name='signaldesk-sync')
        if not self.db.get_setting('sync_instance'):
            self.db.set_setting('sync_instance', str(uuid.uuid4()))

    def config(self):
        e = self.env
        cloud = bool(valid_https(e.get('SIGNALDESK_SUPABASE_URL', '')) and e.get('SIGNALDESK_SUPABASE_SERVICE_KEY') and
                     re.fullmatch(r'[0-9a-fA-F-]{36}', e.get('SIGNALDESK_OWNER_ID', '')))
        return {'cloud_configured': cloud, 'note': 'Only completed briefings sync. New analysis needs the laptop.'}

    def describe(self):
        return {**self.config(), 'last_run': self.db.get_setting('sync_status'),
                'recent': [self.db.get_setting(f'delivery:{r["id"]}') for r in self.db.all('SELECT id FROM digests ORDER BY id DESC LIMIT 5')]}

    def tick(self):
        if not self.config()['cloud_configured'] or not self.lock.acquire(blocking=False):
            return
        try:
            if self.client is None:
                self.client = httpx.Client(timeout=25, follow_redirects=False)
            rows = self.db.all("SELECT * FROM digests WHERE status != 'saved'") + list(reversed(self.db.all("SELECT * FROM digests WHERE status = 'saved' ORDER BY id DESC LIMIT 50")))
            for row in rows:
                self._publish(row)
            self.db.set_setting('sync_status', {'at': now_iso(), 'state': 'checked'})
        except Exception:
            # Provider errors can include credentials/echoed payloads: never log response bodies.
            self.db.set_setting('sync_status', {'at': now_iso(), 'state': 'failed', 'message': 'Cloud sync failed. Check credentials, schema and network; the next check retries.'})
        finally:
            self.lock.release()

    def _publish(self, row):
        e = self.env
        state = self.db.get_setting(f'delivery:{row["id"]}') or {'local_id': row['id']}
        remote_id = str(uuid.uuid5(uuid.UUID(self.db.get_setting('sync_instance')), str(row['id'])))
        # Archived/deleted-from-saved briefings are removed from the remote read model.
        base = e['SIGNALDESK_SUPABASE_URL'].rstrip('/')
        headers = auth_headers(e['SIGNALDESK_SUPABASE_SERVICE_KEY'])
        if row['status'] != 'saved':
            if state.get('cloud') == 'synced':
                r = self.client.delete(base + '/rest/v1/signaldesk_digests', headers=headers,
                    params={'id': 'eq.' + remote_id, 'owner_id': 'eq.' + e['SIGNALDESK_OWNER_ID']})
                r.raise_for_status()
                state['cloud'] = 'removed'
                self.db.set_setting(f'delivery:{row["id"]}', state)
            return
        payload = public_snapshot(json.loads(row['content_json']))
        # Includes the owner so changing accounts uploads the briefings again.
        fingerprint = hashlib.sha256(json.dumps({'owner': e['SIGNALDESK_OWNER_ID'], 'payload': payload}, sort_keys=True).encode()).hexdigest()
        if state.get('fingerprint') != fingerprint or state.get('cloud') != 'synced':
            r = self.client.post(base + '/rest/v1/signaldesk_digests', headers={**headers, 'Prefer': 'resolution=merge-duplicates'},
                params={'on_conflict': 'owner_id,id'}, json={'id': remote_id, 'owner_id': e['SIGNALDESK_OWNER_ID'],
                    'created_at': row['created_at'], 'synced_at': now_iso(), 'payload': payload})
            r.raise_for_status()
            state.update(cloud='synced', fingerprint=fingerprint, remote_id=remote_id, synced_at=now_iso())
            self.db.set_setting(f'delivery:{row["id"]}', state)

    def _loop(self):
        while not self.stop.is_set():
            self.tick()
            self.stop.wait(60)

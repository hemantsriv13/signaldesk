"""Optional outbound cloud snapshots and WhatsApp template submissions.

No inbound access to the laptop. Credentials come from environment variables.
HTTP acceptance is not a delivery receipt. Ambiguous sends are not auto-retried.
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


def summary_text(content):
    lines = ['Your SignalDesk briefing']
    for key, label in (('jobs', 'Jobs'), ('articles', 'Reading')):
        items = content.get(key, [])
        if items:
            lines.append(label + ': ' + '; '.join(str(i['title'])[:100] for i in items[:3]))
    if content.get('case'):
        lines.append('AI in practice: ' + str(content['case']['title'])[:100])
    if len(lines) == 1:
        lines.append('A quiet day. Open the app to review saved results.')
    # Meta rejects template variables containing newlines, tabs or runs of 5+ spaces.
    return re.sub(r'\s+', ' ', ' | '.join(lines)).strip()[:900]


def valid_https(url):
    try:
        p = urlsplit(url)
        return p.scheme == 'https' and bool(p.hostname) and not p.username and not p.password
    except ValueError:
        return False


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
        enabled = self.env.get('SIGNALDESK_WHATSAPP_ENABLED') == 'true'
        newly_enabled = enabled and not self.db.get_setting('delivery_whatsapp_enabled')
        self.db.set_setting('delivery_whatsapp_enabled', enabled)
        if newly_enabled or self.db.get_setting('delivery_activation') is None:
            self.db.set_setting('delivery_activation', {'id': self.db.scalar('SELECT MAX(id) FROM digests') or 0})

    def config(self):
        e = self.env
        cloud = bool(valid_https(e.get('SIGNALDESK_SUPABASE_URL', '')) and e.get('SIGNALDESK_SUPABASE_SERVICE_KEY') and
                     re.fullmatch(r'[0-9a-fA-F-]{36}', e.get('SIGNALDESK_OWNER_ID', '')))
        whatsapp = bool(e.get('SIGNALDESK_WHATSAPP_ENABLED') == 'true' and cloud and
                        e.get('WHATSAPP_ACCESS_TOKEN') and e.get('WHATSAPP_TEMPLATE') and
                        re.fullmatch(r'\d+', e.get('WHATSAPP_PHONE_NUMBER_ID', '')) and
                        re.fullmatch(r'\d{8,15}', e.get('WHATSAPP_TO', '')) and
                        re.fullmatch(r'v\d+\.\d+', e.get('WHATSAPP_GRAPH_VERSION', '')) and
                        valid_https(e.get('SIGNALDESK_READER_URL', '')))
        return {'cloud_configured': cloud, 'whatsapp_configured': whatsapp,
                'automatic_whatsapp': e.get('SIGNALDESK_WHATSAPP_ENABLED') == 'true',
                'note': 'Only completed briefings sync. New analysis needs the laptop. WhatsApp requires configured credentials and an approved template.'}

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

    def retry_rejected(self, digest_id):
        state = self.db.get_setting(f'delivery:{digest_id}') or {}
        if state.get('whatsapp') != 'rejected':
            raise ValueError('Only explicitly rejected submissions can be retried. Submitted or uncertain sends require checking WhatsApp first.')
        if not self.config()['whatsapp_configured']:
            raise ValueError('Complete WhatsApp configuration before retrying.')
        if not self.lock.acquire(blocking=False):
            raise ValueError('A sync is in progress. Try again after it finishes.')
        try:
            row = self.db.one('SELECT * FROM digests WHERE id = ?', (digest_id,))
            if not row or row['status'] != 'saved':
                raise ValueError('The briefing must still be saved.')
            state.pop('whatsapp', None)
            self.db.set_setting(f'delivery:{digest_id}', state)
            self._publish(row)
        finally:
            self.lock.release()

    def _publish(self, row):
        e = self.env
        state = self.db.get_setting(f'delivery:{row["id"]}') or {'local_id': row['id']}
        remote_id = str(uuid.uuid5(uuid.UUID(self.db.get_setting('sync_instance')), str(row['id'])))
        # Archived/deleted-from-saved briefings are removed from the remote read model.
        base = e['SIGNALDESK_SUPABASE_URL'].rstrip('/')
        headers = {'apikey': e['SIGNALDESK_SUPABASE_SERVICE_KEY'], 'Authorization': 'Bearer ' + e['SIGNALDESK_SUPABASE_SERVICE_KEY']}
        if row['status'] != 'saved':
            if state.get('cloud') == 'synced':
                r = self.client.delete(base + '/rest/v1/signaldesk_digests', headers=headers,
                    params={'id': 'eq.' + remote_id, 'owner_id': 'eq.' + e['SIGNALDESK_OWNER_ID']})
                r.raise_for_status()
                state['cloud'] = 'removed'
                self.db.set_setting(f'delivery:{row["id"]}', state)
            return
        payload = public_snapshot(json.loads(row['content_json']))
        fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        if state.get('fingerprint') != fingerprint or state.get('cloud') != 'synced':
            r = self.client.post(base + '/rest/v1/signaldesk_digests', headers={**headers, 'Prefer': 'resolution=merge-duplicates'},
                params={'on_conflict': 'owner_id,id'}, json={'id': remote_id, 'owner_id': e['SIGNALDESK_OWNER_ID'],
                    'created_at': row['created_at'], 'synced_at': now_iso(), 'payload': payload})
            r.raise_for_status()
            state.update(cloud='synced', fingerprint=fingerprint, remote_id=remote_id, synced_at=now_iso())
            self.db.set_setting(f'delivery:{row["id"]}', state)
        # Do not flood WhatsApp with historical briefings on first installation.
        if row['id'] <= self.db.get_setting('delivery_activation')['id']:
            return
        if not self.config()['whatsapp_configured'] or state.get('whatsapp'):
            return
        # Persist before the network call: after timeout/crash, retry could duplicate a real send.
        state.update(whatsapp='submission_unknown', attempted_at=now_iso())
        self.db.set_setting(f'delivery:{row["id"]}', state)
        body = {'messaging_product': 'whatsapp', 'to': e['WHATSAPP_TO'], 'type': 'template',
                'template': {'name': e['WHATSAPP_TEMPLATE'], 'language': {'code': e.get('WHATSAPP_LANGUAGE', 'en')},
                    'components': [{'type': 'body', 'parameters': [{'type': 'text', 'text': summary_text(payload)}]},
                        {'type': 'button', 'sub_type': 'url', 'index': '0', 'parameters': [{'type': 'text', 'text': remote_id}]}]}}
        try:
            r = self.client.post(f'https://graph.facebook.com/{e["WHATSAPP_GRAPH_VERSION"]}/{e["WHATSAPP_PHONE_NUMBER_ID"]}/messages',
                headers={'Authorization': 'Bearer ' + e['WHATSAPP_ACCESS_TOKEN']}, json=body)
            if r.is_success:
                state.update(whatsapp='submitted', message_id=(r.json().get('messages') or [{}])[0].get('id'))
            elif r.status_code < 500:
                state.update(whatsapp='rejected', http_status=r.status_code)
            # 5xx is ambiguous, like a timeout: retain submission_unknown.
        except Exception:
            pass
        self.db.set_setting(f'delivery:{row["id"]}', state)

    def _loop(self):
        while not self.stop.is_set():
            self.tick()
            self.stop.wait(60)

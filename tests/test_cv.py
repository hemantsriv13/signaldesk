from io import BytesIO
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient
from signaldesk.cv import preview_cv, MAX_BYTES
from signaldesk.server import create_app
from signaldesk import analysis


def docx(text):
    from xml.sax.saxutils import escape
    out = BytesIO()
    with ZipFile(out, 'w') as z:
        z.writestr('word/document.xml', '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>' + escape(text) + '</w:t></w:r></w:p></w:body></w:document>')
    return out.getvalue()


def test_docx_and_text_preserve_claims():
    text = 'Built data products using SQL and Python; no production ML experience.'
    assert preview_cv('cv.docx', docx(text))['candidates'] == [text]
    assert preview_cv('cv.txt', text.encode())['candidates'] == [text]


@pytest.mark.parametrize('name,payload', [('cv.doc', b'old word format'), ('cv.docx', b'bad zip'), ('cv.txt', b''), ('cv.txt', b'x' * (MAX_BYTES + 1))])
def test_bad_uploads_have_actionable_errors(name, payload):
    with pytest.raises(ValueError):
        preview_cv(name, payload)


def test_long_facts_are_not_silently_truncated():
    res = preview_cv('cv.txt', ('Work experience ' * 100).encode())
    assert res['candidates'] == []
    assert any('400 characters' in w for w in res['warnings'])
    assert len(res['text']) > 400


def test_import_is_preview_until_profile_saved(engine):
    c = TestClient(create_app(engine))
    before = engine.profiles.profile()
    payload = b'Built SQL pipelines and worked with finance stakeholders.'
    r = c.post('/api/profile/cv-preview?filename=cv.txt', content=payload)
    assert r.status_code == 200
    assert engine.profiles.profile() == before
    facts = [{'text': t} for t in r.json()['candidates']]
    c.put('/api/profile', json={**before, 'facts': facts})
    assert engine.profiles.profile()['facts'][0]['text'] == payload.decode()
    assert not list(engine.cfg.home.glob('*.txt'))


def test_large_and_cross_origin_upload_rejected(engine):
    c = TestClient(create_app(engine))
    assert c.post('/api/profile/cv-preview?filename=cv.txt', content=b'x' * (MAX_BYTES + 1)).status_code == 413
    assert c.post('/api/profile/cv-preview?filename=cv.txt', content=b'CV', headers={'origin':'https://evil.example'}).status_code == 403


def test_long_cv_facts_bounded_and_coverage_disclosed():
    profile = {'facts': [{'id': f'P{i}', 'text': f'Role {i}: ' + 'Experience with stakeholder engagement. ' * 8} for i in range(30)], 'not_claimed': []}
    job = {'title': 'SQL Engineer', 'employer': 'Example', 'description_text': 'SQL required. ' * 1000}
    profile['facts'][-1]['text'] = 'Built SQL pipelines and Python tooling.'
    prompt, coverage = analysis.job_prompt(job, profile, 6000)
    assert len(prompt) + len(analysis.SYSTEM) < 6100
    assert 'P29' in coverage['profile_fact_ids']
    assert len(coverage['profile_fact_ids']) < coverage['profile_facts_total']
    assert profile['facts'][-1]['text'] in prompt


def test_pdf_without_text_explains_ocr():
    from pypdf import PdfWriter
    out = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=300, height=300)
    writer.write(out)
    with pytest.raises(ValueError, match='OCR'):
        preview_cv('scanned.pdf', out.getvalue())


def test_imported_cv_is_used_by_local_matcher_and_invalidates_cache(engine, fake_model):
    from test_engine import add_job, FIT
    from conftest import drain
    fake_model.replies['JOB:'] = FIT
    jid = add_job(engine)
    engine.analyse('job_fit', jid)
    drain(engine)
    old_key = engine.key_for('job_fit', jid)
    c = TestClient(create_app(engine))
    text = 'Built supply-chain data products using SQL and Python.'
    draft = c.post('/api/profile/cv-preview?filename=cv.txt', content=text.encode()).json()
    before = engine.profiles.profile()
    c.put('/api/profile', json={**before, 'facts': [{'text': t} for t in draft['candidates']]})
    assert old_key != engine.key_for('job_fit', jid)
    assert engine.latest('job_fit', 'job', jid)['outdated']
    engine.analyse('job_fit', jid)
    drain(engine)
    assert text in fake_model.calls[-1]['messages'][1]['content']
    assert not engine.latest('job_fit', 'job', jid)['outdated']


def test_profile_change_while_queued_saves_under_actual_profile_version(engine, fake_model):
    from test_engine import add_job, FIT
    from conftest import drain
    fake_model.replies['JOB:'] = FIT
    jid = add_job(engine)
    engine.analyse('job_fit', jid)
    profile = engine.profiles.profile()
    profile['facts'].append({'text': 'Built a procurement reporting application.'})
    engine.profiles.save_profile(profile)
    expected = engine.key_for('job_fit', jid)
    drain(engine)
    result = engine.latest('job_fit', 'job', jid)
    assert not result['outdated']
    assert result['inputs']['profile_version'] == engine.profiles.profile_version()
    assert engine.db.scalar('SELECT cache_key FROM analyses WHERE id = ?', (result['id'],)) == expected

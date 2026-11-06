"""Discover public ATS boards from a user-supplied careers page; never crawl LinkedIn."""
from html.parser import HTMLParser
import re
from urllib.parse import urljoin, urlsplit, unquote, parse_qs
from .netsafe import FetchError


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []
    def handle_starttag(self, tag, attrs):
        if tag in ('a', 'iframe'):
            self.urls += [v for k, v in attrs if k in ('href', 'src') and v]


def board_from_url(url):
    p = urlsplit(url)
    host = (p.hostname or '').lower()
    pieces = [unquote(x) for x in p.path.split('/') if x]
    types = {'boards.greenhouse.io': 'greenhouse', 'job-boards.greenhouse.io': 'greenhouse',
             'jobs.lever.co': 'lever', 'jobs.ashbyhq.com': 'ashby'}
    kind = types.get(host)
    if kind == 'greenhouse' and pieces and pieces[0] == 'embed':
        board_id = parse_qs(p.query).get('for', [''])[0]
        if re.fullmatch(r'[A-Za-z0-9_.-]{1,80}', board_id):
            return {'ats': kind, 'ats_id': board_id, 'url': f'https://boards.greenhouse.io/{board_id}'}
        return None
    if kind and pieces and re.fullmatch(r'[A-Za-z0-9_.-]{1,80}', pieces[0]):
        return {'ats': kind, 'ats_id': pieces[0], 'url': f'https://{host}/{pieces[0]}'}
    return None


def discover(fetcher, url):
    host = (urlsplit(url).hostname or '').lower()
    if host == 'linkedin.com' or host.endswith('.linkedin.com'):
        raise FetchError('Use LinkedIn search in your browser, then paste the employer careers URL here.')
    direct = board_from_url(url)
    if direct:
        return {'boards': [direct], 'checked_url': url, 'note': 'Check this is the right employer before adding it.'}
    r = fetcher.get(url, check_robots=True, accept='text/html')
    if r.status != 200:
        raise FetchError(f'Careers page returned HTTP {r.status}.')
    if 'linkedin.com' in (urlsplit(r.url).hostname or ''):
        raise FetchError('This page redirects to LinkedIn; use the employer careers site instead.')
    page = Links()
    page.feed(r.text[:2_000_000])
    candidates = [r.url, *[urljoin(r.url, link) for link in page.urls]]
    # Include embedded ATS addresses in script configuration, without executing scripts.
    candidates += re.findall(r'https://(?:job-boards\.greenhouse\.io|boards\.greenhouse\.io|jobs\.lever\.co|jobs\.ashbyhq\.com)/[A-Za-z0-9_.-]+', r.text[:2_000_000])
    found = {}
    for link in candidates:
        board = board_from_url(link)
        if board:
            found[(board['ats'], board['ats_id'])] = board
    return {'boards': list(found.values())[:20], 'checked_url': r.url,
            'note': 'Check this is the right employer before adding it. A link on a page does not prove who owns the board.' if found else
            "No supported job board found on this page. You can add this employer's jobs by hand."}

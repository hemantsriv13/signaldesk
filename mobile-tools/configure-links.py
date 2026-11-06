"""Configure verified HTTPS Android App Links after choosing your reader domain."""
import argparse
import json
import re
from pathlib import Path
from xml.etree import ElementTree as E

ap = argparse.ArgumentParser()
ap.add_argument('--host', required=True, help='Reader hostname, without https:// or a path')
ap.add_argument('--fingerprint', required=True, help='SHA-256 fingerprint of the APK signing certificate')
args = ap.parse_args()
if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9.-]+', args.host) or not re.fullmatch(r'(?:[0-9a-fA-F]{2}:){31}[0-9a-fA-F]{2}', args.fingerprint):
    ap.error('Provide a hostname and a colon-separated SHA-256 certificate fingerprint.')
root = Path(__file__).resolve().parent.parent
manifest = root / 'web/android/app/src/main/AndroidManifest.xml'
E.register_namespace('android', 'http://schemas.android.com/apk/res/android')
ns = '{http://schemas.android.com/apk/res/android}'
tree = E.parse(manifest)
activity = tree.find('./application/activity')
for f in list(activity.findall('intent-filter')):
    if f.find('action') is not None and f.find('action').get(ns + 'name') == 'android.intent.action.VIEW':
        activity.remove(f)
f = E.SubElement(activity, 'intent-filter', {ns + 'autoVerify': 'true'})
E.SubElement(f, 'action', {ns + 'name': 'android.intent.action.VIEW'})
for category in ('DEFAULT', 'BROWSABLE'):
    E.SubElement(f, 'category', {ns + 'name': 'android.intent.category.' + category})
E.SubElement(f, 'data', {ns + 'scheme': 'https', ns + 'host': args.host, ns + 'pathPrefix': '/'})
E.indent(tree, space='    ')
tree.write(manifest, encoding='utf-8', xml_declaration=True)
links = root / 'web/public/.well-known/assetlinks.json'
links.parent.mkdir(exist_ok=True)
links.write_text(json.dumps([{'relation': ['delegate_permission/common.handle_all_urls'],
    'target': {'namespace': 'android_app', 'package_name': 'com.hemant.signaldesk',
               'sha256_cert_fingerprints': [args.fingerprint.upper()]}}], indent=2))
print('Configured App Links. Rebuild the APK and host the generated assetlinks.json at https://' + args.host + '/.well-known/assetlinks.json')

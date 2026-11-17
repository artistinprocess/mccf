#!/usr/bin/env python3
"""MCCF scene validator.  Three layers:
   1. XSD   (form)                      mccf.xsd
   2. Schematron (meaning)              mccf_rules.sch
   3. Python (things only code can see) JSON attributes parse, cultivars and files exist
Usage:  python mccf_validate.py scene.xml [--cultivars DIR] [--base DIR]
Returns a report dict: {ok, errors:[...], warnings:[...]}.  ok is True when there are no errors."""
import os, sys, json
from lxml import etree, isoschematron

HERE = os.path.dirname(os.path.abspath(__file__))
NS = {'m': 'http://mccf.artistinprocess.com/v1'}
_xsd = _sch = None

def _load():
    global _xsd, _sch
    if _xsd is None:
        _xsd = etree.XMLSchema(etree.parse(os.path.join(HERE, 'mccf.xsd')))
        _sch = isoschematron.Schematron(etree.parse(os.path.join(HERE, 'mccf_rules.sch')),
                                        store_report=True, error_finder=isoschematron.Schematron.ASSERTS_AND_REPORTS)
    return _xsd, _sch

def validate(xml_text, cultivars_dir=None, base_dir=None):
    errors, warnings = [], []
    try:
        doc = etree.fromstring(xml_text.encode('utf-8') if isinstance(xml_text, str) else xml_text).getroottree()
    except etree.XMLSyntaxError as e:
        return {'ok': False, 'errors': ['Not well-formed XML: %s' % e], 'warnings': []}
    xsd, sch = _load()
    if doc.getroot().tag != '{%s}Scene' % NS['m']:
        return {'ok': True, 'errors': [], 'warnings': ['Not a Scene document; scene rules skipped.']}
    if not xsd.validate(doc):
        for e in xsd.error_log:
            errors.append('Form (line %d): %s' % (e.line, e.message))
    sch.validate(doc)
    if sch.validation_report is not None:
        svrl = {'s': 'http://purl.oclc.org/dsdl/svrl'}
        for f in sch.validation_report.xpath('//s:failed-assert', namespaces=svrl):
            text = ' '.join(''.join(f.xpath('s:text//text()', namespaces=svrl)).split())
            (errors if f.get('role') == 'error' else warnings).append(text)
    # layer 3
    for attr, tag in (('coupler_params', 'Link'), ('data', 'RouteGraph')):
        for el in doc.xpath('//m:%s[@%s]' % (tag, attr), namespaces=NS):
            v = el.get(attr)
            if v and v.strip():
                try: json.loads(v)
                except Exception as e: errors.append('%s@%s is not valid JSON (line %d): %s' % (tag, attr, el.sourceline, e))
    if cultivars_dir and os.path.isdir(cultivars_dir):
        have = {os.path.splitext(f)[0].replace('cultivar_', '', 1).lower() for f in os.listdir(cultivars_dir) if f.endswith('.xml')}
        for a in doc.xpath('//m:AgentPlacement', namespaces=NS):
            c = a.get('cultivar', '')
            if c.lower().replace(' ', '_') not in have and c.lower() not in have:
                warnings.append("Character '%s' has no cultivar file on this server." % c)
    if base_dir:
        # Scene URLs are relative to the web root: the server folder, its static/ folder,
        # or static/x3d/ (where X3DAssets/ lives).
        roots = [base_dir, os.path.join(base_dir, 'static'), os.path.join(base_dir, 'static', 'x3d')]
        for el in doc.xpath('//m:Track[@url] | //m:Asset[@url] | //m:AudioSource[@url] | //m:MidiSource[@url]', namespaces=NS):
            u = el.get('url', '')
            if u and '://' not in u and not u.startswith('data:') and not any(os.path.exists(os.path.join(r, u.lstrip('/'))) for r in roots):
                warnings.append("File not found: %s (%s)." % (u, etree.QName(el).localname))
    return {'ok': not errors, 'errors': errors, 'warnings': warnings}

if __name__ == '__main__':
    a = sys.argv[1:]
    if not a: sys.exit(__doc__)
    kw = {}
    if '--cultivars' in a: kw['cultivars_dir'] = a[a.index('--cultivars') + 1]
    if '--base' in a: kw['base_dir'] = a[a.index('--base') + 1]
    r = validate(open(a[0], encoding='utf-8').read(), **kw)
    for e in r['errors']: print('ERROR  ', e)
    for w in r['warnings']: print('WARNING', w)
    print('OK' if r['ok'] else 'FAILED', '-', len(r['errors']), 'errors,', len(r['warnings']), 'warnings')
    sys.exit(0 if r['ok'] else 1)

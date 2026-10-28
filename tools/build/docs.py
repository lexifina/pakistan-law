"""README, REPRODUCE.md, SOURCES.md, LICENSE, corpus.json, laws.csv, data/ and tools for the Pakistan law repository
(called by build.py)."""
import csv
import hashlib
import io
import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).parent
REPO_FILES = HERE / 'repo'
CACHE = HERE / '.cache'
BUILD_FILES = ('fetch.py', 'parse_pdf.py', 'build.py', 'docs.py', 'check_text.py')
TEMPLATES = ('README.md', 'REPRODUCE.md', 'SOURCES.md', 'LICENSE')


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _csv(rows: list[list]) -> bytes:
    out = io.StringIO()
    w = csv.writer(out, lineterminator='\n')
    for r in rows:
        w.writerow(r)
    return out.getvalue().encode('utf-8')


def source_sums() -> str:
    """sha256 of every cached file the build reads: the listing pages, catalogue, law pages and PDFs."""
    paths = [CACHE / 'catalogue.json', CACHE / 'fetched.json']
    for sub, pat in (('listing', '*.html'), ('pages', '*.html'), ('pdf', '*.pdf')):
        paths += sorted((CACHE / sub).glob(pat))
    return ''.join(f'{p.relative_to(CACHE).as_posix()}\t{_sha(p)}\n' for p in paths)


def render(laws: list[dict], built: list[tuple], excluded: list[list], amend: list[list], issues: list[list],
           day: str, today: str) -> dict[str, bytes]:
    blaws = [b[0] for b in built]
    by_folder = Counter(l['folder'] for l in blaws)
    units = sum(l['units'] for l in blaws)
    sections = sum(1 for b in built for p in b[2] if p.rsplit('/', 1)[1].startswith(('section-', 'article-')))
    schedules = sum(1 for b in built for p in b[2] if p.rsplit('/', 1)[1].startswith('schedule-'))
    reasons = Counter(e[3].split(':')[0].split(' "')[0] if e[3].startswith('the same PDF') else e[3] for e in excluded)
    with_wef = sum(1 for a in amend if a[6])
    with_law = sum(1 for a in amend if a[4] or a[5])
    stamped = [l for l in blaws if l['updated_till']]
    years = sorted(l['promulgated_iso'][:4] for l in blaws if l['promulgated_iso'])

    stats = {
        'today': today, 'retrieved': day, 'listed': len(laws), 'laws': len(blaws), 'excluded': len(excluded),
        'acts': by_folder.get('acts', 0), 'ordinances': by_folder.get('ordinances', 0),
        'orders': by_folder.get('orders', 0), 'regulations': by_folder.get('regulations', 0),
        'constitution': by_folder.get('constitution', 0), 'units': units, 'sections': sections,
        'schedules': schedules, 'commits': len(built) + 1, 'consolidated': len(built), 'footnotes': len(amend),
        'footnotes_with_law': with_law, 'footnotes_with_wef': with_wef, 'unresolved': sum(1 for i in issues if i[1].startswith('footnote marker')),
        'laws_with_empty_pages': sum(1 for i in issues if i[1].startswith('PDF pages')),
        'stamped': len(stamped), 'excluded_repealed_title': sum(1 for e in excluded if e[3].startswith('titled')),
        'excluded_stub': sum(1 for e in excluded if 'notice' in e[3]),
        'excluded_no_pdf': sum(1 for e in excluded if e[3].startswith('no PDF')),
        'excluded_scan': sum(1 for e in excluded if 'scan' in e[3] or 'text layer' in e[3]),
        'excluded_duplicate': sum(1 for e in excluded if e[3].startswith('the same PDF')),
        'excluded_other': 0, 'oldest': years[0] if years else '', 'newest': years[-1] if years else '',
        'excluded_reasons': dict(sorted(reasons.items())),
    }
    stats['excluded_other'] = len(excluded) - sum(stats[k] for k in (
        'excluded_repealed_title', 'excluded_stub', 'excluded_no_pdf', 'excluded_scan', 'excluded_duplicate'))
    parts = [('the Constitution of 1973', stats['constitution'])] if stats['constitution'] else []
    for k, one, many in (('acts', 'Act', 'Acts'), ('ordinances', 'Ordinance', 'Ordinances'), ('orders', 'Order', 'Orders'),
                         ('regulations', 'Regulation', 'Regulations')):
        if stats[k]:
            parts.append((f"{stats[k]:,} {one if stats[k] == 1 else many}", stats[k]))
    names = [p for p, _ in parts]
    stats['kinds'] = ', '.join(names[:-1]) + ' and ' + names[-1] if len(names) > 1 else ''.join(names)
    stats['stub_phrase'] = (f", and {stats['excluded_stub']:,} more whose PDF is a one-page \"THIS LAW HAS BEEN "
                            f"REPEALED\" notice" if stats['excluded_stub'] else
                            "; every PDF that is only a one-page \"THIS LAW HAS BEEN REPEALED\" notice belongs to one "
                            "of these")
    sha = {name: _sha(HERE / name) for name in BUILD_FILES}
    texts = {}
    for name in TEMPLATES:
        t = (REPO_FILES / name).read_text('utf-8')
        for k, v in stats.items():
            if isinstance(v, (str, int)):
                t = t.replace('{{' + k.upper() + '}}', f'{v:,}' if isinstance(v, int) else v)
        for n, h in sha.items():
            t = t.replace('{{SHA_' + n.upper().replace('.', '_') + '}}', h)
        if '{{' in t:
            raise SystemExit(f'{name}: unfilled placeholder near {t[t.index("{{"):t.index("{{") + 40]!r}')
        texts[name] = t

    laws_csv = _csv([['title', 'number', 'kind', 'category', 'promulgated', 'units', 'footnotes', 'updated_till',
                      'unresolved_markers', 'path', 'pdf_sha256', 'source']] +
                    [[l['title'], l['number'], l['folder'].rstrip('s'), l['category'], l['promulgated_iso'], l['units'],
                      l['notes'], l['updated_till'], l['unresolved'], l['dir'] + '/', l['sha256'],
                      'https://pakistancode.gov.pk/english/' + l['href']] for l in sorted(blaws, key=lambda x: x['dir'])])
    amend_csv = _csv([['law', 'note', 'cited_in', 'kind', 'amending_law', 'amending_law_number', 'wef', 'text']] + amend)
    excl_csv = _csv([['listed_title', 'number', 'category', 'reason', 'pdf']] + excluded)
    issues_csv = _csv([['law', 'issue', 'where']] + issues)

    corpus = {
        'corpus': 'pk/national/acts',
        'name': 'Pakistan Code (consolidated federal laws)',
        'label': 'Pakistan',
        'language': 'en',
        'history': 'current-only',
        'laws': {k: stats[k] for k in ('constitution', 'acts', 'ordinances', 'orders', 'regulations')},
        'history_from': day,
        'record_to': day,
        'record_note': 'The Pakistan Code publishes only the current consolidated PDF of each federal law, so each law '
                       f'has one version here: the text as retrieved on {day}. There is no line-by-line history before '
                       'that day. The amendment footnotes are kept as text and in data/amendments.csv. The site says '
                       'its laws are under review and for information only; the Gazette of Pakistan is authoritative.',
        'built': today,
        'baseline_trailer': 'Consolidated',
        'in_force_trailer': 'In-force',
        'dates': {'commit': 'the day the PDFs were retrieved', 'baseline_trailer': 'Consolidated',
                  'other_trailers': ['Promulgated', 'Updated-till'],
                  'time': '12:00 Pakistan time (UTC+5; UTC+6 in the daylight-saving periods of 2002, 2008 and 2009)'},
        'author': {'consolidated': 'Pakistan Code (Ministry of Law and Justice)', 'amendment': 'none yet',
                   'unexplained': 'Pakistan Code (Ministry of Law and Justice)'},
        'citation': {
            'file': r'((?:acts|ordinances|orders|regulations|constitution)/[0-9]{4}/[a-z0-9-]+)/(?:section|article)-([0-9]+[A-Z]*)\.md',
            'cites': '([Ss]ection|[Aa]rticle|[Ss]\\.|[Aa]rt\\.) ?{n}([^0-9A-Za-z]|$)',
        },
        'scope': {
            'trailer': 'Applies',
            'groups': 'any one line',
            'conditions': 'all of a line',
            'when_absent': 'not extracted for Pakistan; savings and transitional rules are in the amending laws',
            'default_reach': {
                'rule': 'presumption against retroactivity',
                'meaning': 'a repeal does not affect anything done, rights acquired or proceedings pending under the '
                           'repealed law unless a different intention appears',
                'authority': 'General Clauses Act, 1897, section 6 (effect of repeal)',
                'decided_here': False,
            },
        },
        'tool': 'tools/in_force_on.py',
    }
    files = {
        'corpus.json': (json.dumps(corpus, indent=2, ensure_ascii=False) + '\n').encode('utf-8'),
        'laws.csv': laws_csv,
        'data/amendments.csv': amend_csv,
        'data/excluded.csv': excl_csv,
        'data/issues.csv': issues_csv,
        'data/stats.json': (json.dumps(stats, indent=1, sort_keys=True) + '\n').encode('utf-8'),
        'data/source-sha256.tsv': source_sums().encode('utf-8'),
        'tools/in_force_on.py': (REPO_FILES / 'tools' / 'in_force_on.py').read_bytes(),
    }
    for name, t in texts.items():
        files[name] = t.encode('utf-8')
    for name in BUILD_FILES:
        files[f'tools/build/{name}'] = (HERE / name).read_bytes()
    for name in TEMPLATES:
        files[f'tools/build/repo/{name}'] = (REPO_FILES / name).read_bytes()
    files['tools/build/repo/tools/in_force_on.py'] = (REPO_FILES / 'tools' / 'in_force_on.py').read_bytes()
    return files

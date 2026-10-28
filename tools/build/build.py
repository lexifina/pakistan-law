"""Build the Pakistan law repository from the retrieved Pakistan Code pages and PDFs.

    python -X utf8 build.py <build folder> --today YYYY-MM-DD [--limit N] [--workers 4]

The Pakistan Code (pakistancode.gov.pk, Ministry of Law and Justice) publishes one consolidated PDF of each federal
law, with the amendment history as footnotes, and keeps no earlier versions. So the history here starts at that text
(corpus.json `history: "current-only"`):

1. Every law listed on the 26 alphabetical pages with a PDF that has a text layer is one law, except the laws titled
   "Repealed", one-page "THIS LAW HAS BEEN REPEALED" stubs, scanned gazettes whose only text is an OCR layer, and a
   second listing of the same PDF. Those are listed in data/excluded.csv with the reason.
2. parse_pdf.py splits each PDF into title.md (title, number, date, long title, preamble), contents.md (the printed
   list of sections), one file per section or Article (`section-12A.md`, `article-25.md`) with the Part and Chapter
   headings above it as `##` lines, and one file per Schedule. One paragraph per line. Footnote markers become
   `[^n]` and every file ends with the footnotes it cites; notes.md holds all of them in order.
3. Each law is one commit, `Kind: consolidated`, authored by the publisher, dated noon Pakistan time on the day the
   PDFs were retrieved; In-force and Consolidated give that day. The "Updated till" stamp some PDFs carry is kept as
   an `Updated-till:` trailer, as printed. Footnotes are parsed into data/amendments.csv (kind, amending law,
   w.e.f. date). No line is credited to an amending law: the earlier text is not published.
4. The whole history is written by one deterministic git fast-import, so the same retrieved files give the same hashes.
"""
import argparse
import csv
import hashlib
import io
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).parent
CACHE = HERE / '.cache'
SITE = 'https://pakistancode.gov.pk'
COMMITTER = 'Lexifina <pakistan@lexifina.com>'
PUBLISHER = ('Pakistan Code (Ministry of Law and Justice)', 'pakistan-code@pakistancode-gov-pk.invalid')
MONTHS = {m: i for i, m in enumerate(['january', 'february', 'march', 'april', 'may', 'june', 'july', 'august',
                                      'september', 'october', 'november', 'december'], 1)}
# Pakistan Standard Time is UTC+5. Daylight saving time (UTC+6) was kept only in these three periods
# (hard-coded, so the build needs no time-zone database).
PK_DST = [('2002-04-07', '2002-10-06'), ('2008-06-01', '2008-11-01'), ('2009-04-15', '2009-11-01')]


def pk_offset(day: str) -> int:
    return 6 if any(a <= day < b for a, b in PK_DST) else 5


def git_date(day: str) -> str:
    """Noon in Pakistan on `day`, as a git date."""
    off = pk_offset(day)
    d = datetime.strptime(day, '%Y-%m-%d').replace(tzinfo=timezone(timedelta(hours=off)))
    ts = int((d + timedelta(hours=12)).timestamp())
    return f'{ts} +0{off}00'


# ---------------------------------------------------------------------------------------------------- catalogue

def clean_title(t: str) -> str:
    t = re.sub(r'\s*\((?:Under Review|Under-Review)\)\s*', ' ', t, flags=re.I)
    return re.sub(r'\s+', ' ', t).strip().rstrip('.')


def slug(t: str) -> str:
    t = t.lower().replace('&', ' and ').replace('’', '').replace("'", '')
    t = re.sub(r'^the\s+', '', t)
    t = re.sub(r'[^a-z0-9]+', '-', t).strip('-')
    return t[:90].rstrip('-') or 'law'


def bare_title(t: str) -> str:
    """The title without the listing's notes in brackets: "(Same as on the official website of FBR dated ...)",
    "(ANF 1997)", "(Act No_XXVI of 2018)". Brackets without a digit or such a note are part of the name."""
    return re.sub(r'\s*\((?=[^()]*(?:\d|same as|under review|amended|valid))[^()]*\)', '', t, flags=re.I).strip()


def law_kind(title: str) -> str:
    """By the last of Act / Ordinance / Order / Regulation in the title outside brackets: "Martial Law Regulation No.
    60 (Repeal) Act, 1989" is an Act."""
    if re.match(r'^(the\s+)?constitution of the islamic republic of pakistan$', title, re.I):
        return 'constitution'
    words = re.findall(r'\b(act|ordinance|order|regulations?)\b', re.sub(r'\([^()]*\)', ' ', title), re.I)
    last = words[-1].lower() if words else 'act'
    return {'act': 'acts', 'ordinance': 'ordinances', 'order': 'orders'}.get(last, 'regulations')


def law_year(law: dict) -> str:
    for src in (bare_title(law['title']), law['number'], law['promulgated']):
        ys = re.findall(r'(1[789]\d\d|20\d\d)', src or '')
        if ys:
            return ys[-1]
    return '0000'


def promulgated_iso(s: str) -> str:
    m = re.match(r'([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})', s or '')
    if not m or m.group(1).lower() not in MONTHS:
        return ''
    return f'{int(m.group(3)):04d}-{MONTHS[m.group(1).lower()]:02d}-{int(m.group(2)):02d}'


def load_catalogue(limit: int | None) -> list[dict]:
    cat = json.loads((CACHE / 'catalogue.json').read_text('utf-8'))
    fetched = {r['href']: r for r in json.loads((CACHE / 'fetched.json').read_text('utf-8'))}
    laws = []
    for i, c in enumerate(cat):
        f = fetched.get(c['href'], {})
        laws.append({'order': i, 'href': c['href'], 'listed_title': c['title'], 'title': clean_title(c['title']),
                     'number': c['number'], 'category': c['category'], 'promulgated': c['promulgated'],
                     'promulgated_iso': promulgated_iso(c['promulgated']), 'tab': c['tab'],
                     'pdf': f.get('pdf'), 'pdf_url': f.get('pdf_url') or ''})
    return laws[:limit] if limit else laws


# ---------------------------------------------------------------------------------------------------- notes

KINDS = [(r'\bsubs(?:\.|tituted)', 'substituted'), (r'\bins(?:\.|erted)', 'inserted'), (r'\bomitted\b', 'omitted'),
         (r'\badded\b', 'added'), (r'\brep(?:\.|ealed)', 'repealed'), (r'\bre-?numbered\b', 'renumbered'),
         (r'\bamended\b', 'amended'), (r'\bdeleted\b', 'deleted')]
ACT_NO = re.compile(r'\b((?:Act|Ordinance|Ord\.|Order|P\.\s?O\.|President[’\']s Order|Regulation|Regulations)\s+'
                    r'(?:No\.?\s*)?(?:[IVXLCDM]+|\d+)\s+of\s+\d{4})', re.I)
ACT_NAME = re.compile(r'\b(?:by|vide|in)\s+(?:the\s+)?([A-Z][^,;]{2,160}?(?:Act|Ordinance|Order|Regulations?)'
                      r'\s*,?\s*\d{4})')
AO = re.compile(r'\b((?:F\.\s?A\.\s?O\.|A\.\s?O\.)\s*,?\s*\d{4})')
WEF = re.compile(r'(?:w\.\s?e\.\s?f\.?|with effect from)\s*,?\s*(?:the\s+)?(\d{1,2})(?:st|nd|rd|th)?\s*(?:day\s+of\s+)?'
                 r',?\s*([A-Za-z]+)\s*,?\s*(\d{4})', re.I)
WEF_NUM = re.compile(r'(?:w\.\s?e\.\s?f\.?|with effect from)\s*,?\s*(?:the\s+)?(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})', re.I)


def note_row(note: str) -> tuple[str, str, str, str]:
    """(kinds, amending law by name, amending law by number, w.e.f. date) read from one footnote."""
    low = note.lower()
    kinds = [k for p, k in KINDS if re.search(p, low)]
    name = ACT_NAME.search(note) or AO.search(note)
    number = ACT_NO.search(note)
    wef = ''
    m = WEF.search(note)
    if m and m.group(2).lower() in MONTHS:
        wef = f'{int(m.group(3)):04d}-{MONTHS[m.group(2).lower()]:02d}-{int(m.group(1)):02d}'
    else:
        m = WEF_NUM.search(note)
        if m and 1 <= int(m.group(2)) <= 12:
            wef = f'{int(m.group(3)):04d}-{int(m.group(2)):02d}-{int(m.group(1)):02d}'
    return ('; '.join(kinds), re.sub(r'\s+', ' ', name.group(1)).strip() if name else '',
            re.sub(r'\s+', ' ', number.group(1)).strip() if number else '', wef)


# ---------------------------------------------------------------------------------------------------- one law

def parse_all(todo: list[dict], workers: int, fresh: bool) -> dict[str, dict]:
    """href -> parse_pdf.parse() result (plus the PDF's sha256). Parsed by up to `workers` processes of
    `parse_pdf.py --batch`, into .cache/parsed/<sha256 of parse_pdf.py>/, so a parse is reused only by the same
    parser. --fresh parses everything again."""
    key = hashlib.sha256((HERE / 'parse_pdf.py').read_bytes()).hexdigest()[:16]
    out = CACHE / 'parsed' / key
    if fresh and out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    pdfs = sorted({l['pdf'] for l in todo})
    missing = [p for p in pdfs if not (out / f'{p}.json').exists()]
    # big PDFs first, dealt round-robin, so the shards finish together
    missing.sort(key=lambda p: -(CACHE / 'pdf' / p).stat().st_size)
    shards = [missing[i::workers] for i in range(workers)] if missing else []
    procs = [subprocess.Popen([sys.executable, '-X', 'utf8', str(HERE / 'parse_pdf.py'), '--batch', str(out),
                               *[str(CACHE / 'pdf' / p) for p in s]], stdin=subprocess.DEVNULL)
             for s in shards if s]
    if procs:
        print(f'parsing {len(missing)} PDFs in {len(procs)} processes', flush=True)
    for p in procs:
        if p.wait():
            sys.exit('a parse_pdf.py --batch process failed')
    res = {}
    for l in todo:
        res[l['href']] = json.loads((out / f"{l['pdf']}.json").read_text('utf-8'))
    return res


def repealed_title(t: str) -> bool:
    """The listing marks a repealed law in its title: "(Repealed)", "(Repealed by Act XIV of 2016)", "(Repeal by Ord.
    52 of 2001, s.610)". A repealing law's own name, "Federal Court (Repeal) Act, 2014", is not such a mark."""
    return bool(re.search(r'\brepealed\b', t, re.I) or
                re.search(r'repeal(?:ed)?\s*(?:by|vide|through|via|w\.?e\.?f|under|in|on|dated)\b', t, re.I))


def excluded_reason(law: dict, r: dict | None) -> str | None:
    if repealed_title(law['listed_title']):
        return 'titled as repealed on the Pakistan Code ("Repealed", "Repeal by ...")'
    if not law['pdf']:
        return 'no PDF: the law page links none, or the link answers an error'
    if r is None or 'error' in r:
        return (r or {}).get('error', 'not parsed')
    if r['text_layer'] < 200:
        return 'PDF has no text layer (a scan)'
    if r['invisible_chars'] > 0.3 * r['text_layer'] or r['ocr_chars'] > 0.3 * r['text_layer']:
        return 'PDF is a scanned gazette whose only text is an invisible OCR layer, not the publisher\'s text'
    if len(r['empty_pages']) > 0.3 * r['pages']:
        return f"PDF is mostly scanned pages without text ({len(r['empty_pages'])} of {r['pages']} pages)"
    alltext = ' '.join(r['title'] + [l for u in r['units'] for l in u['lines']])
    if r['pages'] <= 2 and re.search(r'THIS\s+LAW\s+HAS\s+BEEN\s+REPEALED', alltext, re.I) and len(alltext) < 600:
        return 'PDF is a one-page "THIS LAW HAS BEEN REPEALED" notice'
    return None


def unit_kind(law: dict, r: dict) -> str:
    """Articles for the Constitution and for Orders that call their units Articles; sections otherwise."""
    if law['folder'] == 'constitution':
        return 'article'
    if law['folder'] == 'orders':
        text = ' '.join(l for u in r['units'] for l in u['lines'])
        if len(re.findall(r'\bArticles?\b', text)) > len(re.findall(r'\b[Ss]ections?\b', text)):
            return 'article'
    return 'section'


def files_for(law: dict, r: dict) -> tuple[dict[str, str], list[str]]:
    notes = {n['g']: n['text'] for n in r['notes']}
    d = law['dir']
    files: dict[str, str] = {}
    order: list[str] = []

    def defs(nums: list[int]) -> list[str]:
        return [f'[^{n}]: {notes[n]}' for n in nums if n in notes]

    def put(name: str, lines: list[str], nums: list[int]) -> None:
        lines = [l for l in lines if l.strip()]
        if not lines:
            return
        body = '\n'.join(lines) + '\n'
        nd = defs(nums)
        if nd:
            body += '\n' + '\n'.join(nd) + '\n'
        files[f'{d}/{name}'] = body
        order.append(name)

    title = list(r['title'])
    if title:
        title[0] = '# ' + title[0]
    put('title.md', title, sorted({int(n) for l in r['title'] for n in re.findall(r'\[\^(\d+)\]', l)}))
    put('contents.md', r['contents'], sorted({int(n) for l in r['contents'] for n in re.findall(r'\[\^(\d+)\]', l)}))
    kind = law['unit_kind']
    for u in r['units']:
        uid = u['id'].replace('section-', f'{kind}-', 1) if u['kind'] == 'section' else u['id']
        put(f'{uid}.md', u['lines'], u['notes'])
    if r['notes']:
        files[f'{d}/notes.md'] = '\n'.join(f"[^{n['g']}]: {n['text']}" for n in r['notes']) + '\n'
        order.append('notes.md')
    files[f'{d}/index.txt'] = '\n'.join(order) + '\n'
    return files, order


# ---------------------------------------------------------------------------------------------------- write

def message(law: dict, day: str, r: dict, n_units: int) -> str:
    kind = 'Articles' if law['unit_kind'] == 'article' else 'sections'
    subject = f"{law['title']}: as consolidated on the Pakistan Code, retrieved {day}"
    stamp = r['stamps'][0] if r['stamps'] else ''
    body = [f"The text of the {law['title']} ({law['number']}) as the Pakistan Code publishes it in its consolidated "
            f"PDF, retrieved on {day}." + (f' The PDF is stamped "{stamp}".' if stamp else ''),
            '',
            'The Pakistan Code keeps no earlier versions, so this commit holds the whole text and nobody is credited',
            'with single lines. The amendment history the PDF prints as footnotes is kept in the files and in',
            f"data/amendments.csv ({len(r['notes'])} footnotes; {n_units} {kind} and schedules).",
            '',
            'The site says: "The content available on this Website is for information purposes only, and is',
            'currently under review." For the authentic text, see the Gazette of Pakistan.']
    tr = ['Kind: consolidated', f'In-force: {day}', f'Consolidated: {day}', 'Date-source: retrieved',
          f"Law: {law['title']}", f"Law-number: {law['number']}", f"Law-kind: {law['folder'].rstrip('s')}",
          f"Category: {law['category']}"]
    if law['promulgated_iso']:
        tr.append(f"Promulgated: {law['promulgated_iso']}")
    for s in r['stamps']:
        tr.append('Updated-till: ' + re.sub(r'^\s*updated?\s*till\s*', '', s, flags=re.I).strip())
    tr += [f"Source: {SITE}/english/{law['href']}", f"PDF: {law['pdf_url']}", f"PDF-sha256: {r['sha256']}"]
    msg = '\n'.join([subject, '', *body, '', *tr]) + '\n'
    return msg.replace('\r', '')


def fast_import(repo: Path, commits: list[tuple], docs: dict[str, bytes], day: str) -> None:
    buf = io.BytesIO()
    w = buf.write
    name, email = PUBLISHER
    when = git_date(day)
    for law, r, files, n_units in commits:
        w(b'commit refs/heads/main\n')
        w(f'author {name} <{email}> {when}\ncommitter {COMMITTER} {when}\n'.encode())
        m = message(law, day, r, n_units).encode('utf-8')
        w(f'data {len(m)}\n'.encode() + m + b'\n')
        for path, text in sorted(files.items()):
            t = text.encode('utf-8')
            w(f'M 100644 inline {path}\ndata {len(t)}\n'.encode() + t + b'\n')
        w(b'\n')
    msg = (f'Documentation: README, REPRODUCE, SOURCES, tools, laws.csv and data\n\n'
           f'Built from the Pakistan Code PDFs retrieved on {day}.\n\nKind: documentation\nIn-force: {day}\n').encode()
    w(b'commit refs/heads/main\n')
    w(f'author {COMMITTER} {when}\ncommitter {COMMITTER} {when}\n'.encode())
    w(f'data {len(msg)}\n'.encode() + msg + b'\n')
    for path, data in sorted(docs.items()):
        w(f'M 100644 inline {path}\ndata {len(data)}\n'.encode() + data + b'\n')
    w(b'\n')
    res = subprocess.run(['git', '-C', str(repo), 'fast-import', '--quiet', '--force'], input=buf.getvalue(),
                         capture_output=True)
    if res.returncode:
        sys.exit(res.stderr.decode('utf-8', 'replace')[-3000:])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('repo', type=Path)
    ap.add_argument('--today', required=True)
    ap.add_argument('--limit', type=int)
    ap.add_argument('--workers', type=int, default=4)
    ap.add_argument('--fresh', action='store_true', help='parse every PDF again (ignore .cache/parsed)')
    args = ap.parse_args()
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', args.today):
        sys.exit('--today must be YYYY-MM-DD')
    day = (CACHE / 'fetched_on.txt').read_text('utf-8').strip()
    if day > args.today:
        sys.exit(f'retrieval date {day} is after --today {args.today}')
    if args.repo.name in ('pakistan-law', 'lexifina'):
        sys.exit('build into a separate build folder, never the checkout')

    laws = load_catalogue(args.limit)
    todo = [l for l in laws if l['pdf'] and not repealed_title(l['listed_title'])]
    parsed = parse_all(todo, min(args.workers, 4), args.fresh)

    excluded: list[list[str]] = []
    built: list[tuple] = []
    seen_pdf: dict[str, str] = {}
    used_dirs: dict[str, str] = {}
    amend: list[list] = []
    issues: list[list[str]] = []
    for law in sorted(laws, key=lambda l: l['order']):
        r = parsed.get(law['href'])
        why = excluded_reason(law, r)
        if why is None and law['pdf'] in seen_pdf:
            why = f'the same PDF as "{seen_pdf[law["pdf"]]}"'
        if why:
            excluded.append([law['listed_title'], law['number'], law['category'], why, law['pdf_url']])
            continue
        seen_pdf[law['pdf']] = law['title']
        law['folder'] = law_kind(law['title'])
        name = re.sub(r',?\s*(1[789]|20)\d\d\s*$', '', bare_title(law['title']))
        base = f"{law['folder']}/{law_year(law)}/{slug(name)}"
        d, k = base, 2
        while d in used_dirs:
            d = f'{base}-{k}'
            k += 1
        used_dirs[d] = law['href']
        law['dir'] = d
        law['unit_kind'] = unit_kind(law, r)
        files, order = files_for(law, r)
        n_units = sum(1 for n in order if n not in ('title.md', 'contents.md', 'notes.md'))
        law.update({'units': n_units, 'notes': len(r['notes']), 'pages': r['pages'],
                    'updated_till': '; '.join(re.sub(r'^\s*updated?\s*till\s*', '', s, flags=re.I) for s in r['stamps']),
                    'sha256': r['sha256'], 'unresolved': r['unresolved_markers']})
        cited: dict[int, list[str]] = {}
        for name in order:
            if name in ('notes.md',):
                continue
            for n in re.findall(r'\[\^(\d+)\]', files[f'{d}/{name}'].split('\n\n[^')[0]):
                cited.setdefault(int(n), [])
                if name[:-3] not in cited[int(n)]:
                    cited[int(n)].append(name[:-3])
        for n in r['notes']:
            kinds, by_name, by_number, wef = note_row(n['text'])
            amend.append([d, n['g'], ' '.join(cited.get(n['g'], [])), kinds, by_name, by_number, wef, n['text']])
        if r['empty_pages']:
            issues.append([d, 'PDF pages with no text (a scanned page, a picture or a blank page); nothing taken from '
                              'them', 'pages ' + ', '.join(map(str, r['empty_pages']))])
        for u in r['unresolved']:
            issues.append([d, 'footnote marker with no footnote of that number on its page; kept as printed', u])
        built.append((law, r, files, n_units))
    built.sort(key=lambda c: c[0]['dir'])
    print(f'{len(laws)} listed, {len(built)} built, {len(excluded)} excluded, {len(amend)} footnotes, '
          f'{len(issues)} unresolved markers', flush=True)

    import docs as docmod
    docs = docmod.render(laws, built, excluded, amend, issues, day, args.today)

    repo = args.repo
    if repo.exists():
        import os
        import stat

        def onerr(func, path, _):
            os.chmod(path, stat.S_IWRITE)
            func(path)
        shutil.rmtree(repo, onerror=onerr)
    repo.mkdir(parents=True)
    subprocess.run(['git', 'init', '-q', '-b', 'main', str(repo)], check=True)
    for k, v in (('core.autocrlf', 'false'), ('core.longpaths', 'true'), ('core.quotepath', 'false')):
        subprocess.run(['git', '-C', str(repo), 'config', k, v], check=True)
    fast_import(repo, built, docs, day)
    subprocess.run(['git', '-C', str(repo), 'checkout', '-q', '-f', 'main'], check=True)
    head = subprocess.run(['git', '-C', str(repo), 'rev-parse', 'HEAD'], capture_output=True, text=True).stdout.strip()
    count = subprocess.run(['git', '-C', str(repo), 'rev-list', '--count', 'HEAD'], capture_output=True,
                           text=True).stdout.strip()
    print(f'built {repo}: {count} commits, head {head}', flush=True)


if __name__ == '__main__':
    main()

"""Independent check: the letters and digits of each law in the repo equal those of its PDF.

    python -X utf8 check_text.py <repo> [--show N] [--only <path-substring>]

The source side is read by `pdftotext -layout` (xpdf, not PyMuPDF, which the build uses), page by page, keeping every
text line except: the "Page x of y" footer, the "Updated till ..." stamp, a bare page number as a page's first or last
line (one that fits the run of page numbers: the page's own number, or an offset from it that recurs), and a running header (a page's first line that, digits aside, is the first line of at least half the pages).
A running footer is not removed: the last line is often a footnote that recurs on many pages. Both sides are cut into tokens, runs of letters and runs of digits, casefolded, so spaces,
punctuation, dashes and line breaks do not count.

The repo side is every file of the law at HEAD: the unit files without their footnote definitions, and notes.md
(each footnote once), with the `[^n]` references removed. Footnotes move from the foot of the page into the files,
so order is not compared; the counts are:
- letters: the multiset of letter tokens should be equal; where it is not, the letters of the differing words are
  compared, and if they are the same the law is counted as "broken into words differently" (a gap read as a space
  by one reader and not by the other), not as a difference;
- digits: the repo must have no digit the PDF lacks. The PDF should have, beyond the repo's digit tokens, one
  token for every footnote number it prints and every marker the build turned into `[^n]`; laws where that count
  is off (a marker run into a neighbouring number) are listed, not failed.
Any other difference fails. The exit status is the number of laws that differ.
"""
import argparse
import csv
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).parent
CACHE = HERE / '.cache'
TOKEN = re.compile(r'[^\W\d_]+|\d+')


HYPHEN = re.compile(r'[\-‐‑­]')
ARABIC = re.compile(r'[؀-ۿ]')


def tokens(s: str) -> list[str]:
    """Letter runs and digit runs, casefolded. Hyphens, non-breaking hyphens and soft hyphens separate tokens on
    both sides (the PDF is read with -layout, which keeps a hyphen at a line end instead of joining the word); and
    text in Arabic script is compared letter by letter, because the two readers order the lam-alef ligature's
    letters and break the words differently."""
    s = HYPHEN.sub(' ', s)
    out = []
    for t in TOKEN.findall(s):
        t = t.casefold()
        if ARABIC.search(t):
            out += list(t)
        else:
            out.append(t)
    return out


def pdf_text(pdf: Path) -> str:
    out = subprocess.run(['pdftotext', '-layout', '-enc', 'UTF-8', str(pdf), '-'], capture_output=True, check=True).stdout
    pages = [[l for l in p.split('\n') if l.strip()] for p in out.decode('utf-8', 'replace').split('\f')]
    pages = [p for p in pages if p] or [[]]

    def key(l: str) -> str:
        return re.sub(r'\d+', '#', re.sub(r'\s+', '', l).lower())
    pages = [[l for l in p if not re.fullmatch(r'page\d+of\d+', re.sub(r'\s+', '', l).lower())
              and not re.match(r'\s*updated\s*till\b', l, re.I)] for p in pages]
    # headers only: a page's last line is often a footnote that recurs on many pages, so it is never taken as furniture
    heads = Counter(key(p[0]) for p in pages if p)
    common = {k for k, c in heads.items() if len(pages) >= 3 and c >= max(3, len(pages) // 2) and k}
    pageno = re.compile(r'[-–\s]*(\d{1,4})[-–\s]*')
    # a bare number is a page number only when it fits the run of page numbers: the page's own number, or the same
    # offset from the page's place on at least two pages (so the last row of a table, "660", is not taken for one)
    offsets = Counter()
    for i, p in enumerate(pages):
        for l in {id(x): x for x in p[:1] + p[-1:]}.values():
            m = pageno.fullmatch(l)
            if m:
                offsets[int(m.group(1)) - i] += 1

    def is_pageno(l: str, i: int) -> bool:
        m = pageno.fullmatch(l)
        return bool(m) and (int(m.group(1)) == i + 1 or offsets[int(m.group(1)) - i] >= 2)
    keep = []
    for i, p in enumerate(pages):
        # one line at each end at most, so a list of identical rows ("N. Repeal") is not eaten
        if p and (key(p[0]) in common or is_pageno(p[0], i)):
            p.pop(0)
        elif p and common:
            # -layout can print the running header on one line with a fragment of the first body row beside it
            # ("(h)        THE CUSTOMS ACT,1969"): drop only the fragment that is the header
            frags = re.split(r'\s{2,}', p[0].strip())
            rest = [f for f in frags if key(f) not in common]
            if len(rest) < len(frags):
                p[0] = '   '.join(rest)
                if not p[0].strip():
                    p.pop(0)
        if p and is_pageno(p[-1], i):
            p.pop()
        keep += p
    # a few PDFs print the footnote marker and number 1 as a lower-case L ("l[Federal Government]", "lSubs. by");
    # the build reads it as the number, so it is not a letter of the text
    return re.sub(r'(?<![^\W\d_])l(?=\[|[A-Z][a-z])', '', '\n'.join(keep))


class Blobs:
    """Reads files from git through one `git cat-file --batch` process."""

    def __init__(self, repo: Path):
        self.p = subprocess.Popen(['git', '-C', str(repo), 'cat-file', '--batch'], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE)

    def get(self, spec: str) -> str | None:
        self.p.stdin.write(spec.encode('utf-8') + b'\n')
        self.p.stdin.flush()
        head = self.p.stdout.readline().split()
        if len(head) < 3 or head[1] == b'missing':
            return None
        data = self.p.stdout.read(int(head[2]))
        self.p.stdout.read(1)
        return data.decode('utf-8')


def repo_text(blobs: Blobs, path: str) -> tuple[str, int, int]:
    """(text, references, footnotes) of one law at HEAD."""
    names = [n for n in (blobs.get(f'HEAD:{path}/index.txt') or '').split('\n') if n]
    parts, refs, notes = [], 0, 0
    for n in names:
        t = blobs.get(f'HEAD:{path}/{n}') or ''
        if n == 'notes.md':
            lines = t.split('\n')
            notes += sum(1 for l in lines if re.match(r'^\[\^\d+\]: ', l))
            t = '\n'.join(re.sub(r'^\[\^\d+\]: ', '', l) for l in lines)
        else:
            t = '\n'.join(l for l in t.split('\n') if not re.match(r'^\[\^\d+\]: ', l))
            refs += len(re.findall(r'\[\^\d+\]', t))
        parts.append(re.sub(r'\[\^\d+\]', ' ', t))
    return '\n'.join(parts), refs, notes


def main() -> None:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    ap = argparse.ArgumentParser()
    ap.add_argument('repo', type=Path)
    ap.add_argument('--show', type=int, default=15)
    ap.add_argument('--only')
    args = ap.parse_args()
    blobs = Blobs(args.repo)
    fetched = {r['href']: r for r in json.loads((CACHE / 'fetched.json').read_text('utf-8'))}
    rows = list(csv.DictReader(io_text(blobs.get('HEAD:laws.csv'))))
    bad, letters_total, digits_total = [], 0, 0
    spacing: list[str] = []
    digit_count: list[str] = []
    letters_off = 0
    for row in rows:
        path = row['path'].rstrip('/')
        if args.only and args.only not in path:
            continue
        href = row['source'].rsplit('/english/', 1)[1]
        pdf = CACHE / 'pdf' / fetched[href]['pdf']
        src = Counter(tokens(pdf_text(pdf)))
        text, refs, notes = repo_text(blobs, path)
        mine = Counter(tokens(text))
        sl = Counter({k: v for k, v in src.items() if not k.isdigit()})
        ml = Counter({k: v for k, v in mine.items() if not k.isdigit()})
        sd = Counter({k: v for k, v in src.items() if k.isdigit()})
        md = Counter({k: v for k, v in mine.items() if k.isdigit()})
        letters_total += sum(ml.values())
        digits_total += sum(md.values())
        problems = []
        if sl != ml:
            a, b = sl - ml, ml - sl
            ca, cb = Counter(''.join(k * v for k, v in a.items())), Counter(''.join(k * v for k, v in b.items()))
            if ca == cb:
                spacing.append(path)   # the same letters, broken into words differently
            else:
                lost = sum((ca - cb).values())
                extra = sum((cb - ca).values())
                letters_off += lost + extra
                problems.append(f'letters: {lost} only in PDF, {extra} only in repo; words only in PDF '
                                f'{dict(a.most_common(6))}, only in repo {dict(b.most_common(6))}')
        dd = Counter(''.join(k * v for k, v in md.items())) - Counter(''.join(k * v for k, v in sd.items()))
        if dd:
            problems.append(f'digits in the repo that the PDF lacks: {dict(dd)}')
        if sum((sd - md).values()) != refs + notes:
            digit_count.append(path)   # markers run into other digits, or digits broken differently
        if problems:
            bad.append((path, problems))
    for path, problems in bad[:args.show]:
        print(f'DIFF {path}')
        for p in problems:
            print(f'     {p}')
    print(f'{len(rows) if not args.only else "selected"} laws checked; {letters_total:,} letter tokens and '
          f'{digits_total:,} digit tokens in the repo')
    print(f'  same letters but broken into words differently: {len(spacing)} laws {spacing[:args.show]}')
    print(f'  digit-token count not explained exactly by markers + footnote numbers (no digit invented): '
          f'{len(digit_count)} laws {digit_count[:args.show]}')
    print(f'  letters or digits differ: {len(bad)} laws, {letters_off:,} letters in all')
    sys.exit(min(len(bad), 125))


def io_text(s: str | None):
    import io
    return io.StringIO(s or '')


if __name__ == '__main__':
    main()

"""Independent check: the letters and digits of each law in the repo equal those of its PDF.

    python -X utf8 check_text.py <repo> [--show N] [--only <path-substring>]

The source side is read by `pdftotext -layout` (xpdf, not PyMuPDF, which the build uses), page by page, keeping every
text line except: the "Page x of y" footer (also "Page of y", and as a fragment of a line where -layout prints it
beside other text), the "Updated till ..." stamp (also "Update Till", and several stamps printed over each other),
a bare page number as a page's first or last line (one that fits the run of page numbers: the page's own number, or
an offset from it that recurs), and a running header (a page's first line, or a fragment of it, that digits aside
is the first line of at least a third of the pages; on a page printed sideways, where -layout scatters the header's
parts over the page, each part once). A running footer is not removed: the last line is often a footnote
that recurs on many pages. A lone lower-case L, which these PDFs use for the marker or number 1, is dropped on both
sides (see LONE_L). Both sides are cut into tokens, runs of letters and runs of digits, casefolded, so spaces,
punctuation, dashes and line breaks do not count.

The repo side is every file of the law at HEAD: the unit files without their footnote definitions, and notes.md
(each footnote once), with the `[^n]` references removed. Footnotes move from the foot of the page into the files,
so order is not compared; the counts are:
- letters: the multiset of letter tokens should be equal; where it is not, the letters of the differing words are
  compared, and if they are the same the law is counted as "broken into words differently" (a gap read as a space
  by one reader and not by the other), not as a difference. Two cases are listed apart, not failed: a PDF word that is
  a repo word with an L run into it, where the repo has a footnote reference right there (the marker 1 printed as
  an L, "rulesl to be"); and laws where only the number of L's differs and is the same on both sides before lone L's
  are dropped (text printed over other text, which -layout interleaves glyph by glyph, makes an L stand alone or
  not on one side only);
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


def pdf_text(pdf: Path, keep_l: bool = False) -> str:
    out = subprocess.run(['pdftotext', '-layout', '-enc', 'UTF-8', str(pdf), '-'], capture_output=True, check=True).stdout
    pages = [[l for l in p.split('\n') if l.strip()] for p in out.decode('utf-8', 'replace').split('\f')]
    pages = [p for p in pages if p] or [[]]

    def key(l: str) -> str:
        return re.sub(r'\d+', '#', re.sub(r'\s+', '', l).lower())
    def unfooter(l: str) -> str:
        """The line without its "Page x of y" footer ("Page of 11" in a PDF that lost the number), also where -layout
        prints the footer on one line with another fragment ("268A. Orderly use of building.      Page 15 of 137")."""
        frags = re.split(r'(\s{2,})', l)
        return ''.join(f for f in frags if not re.fullmatch(r'page\d*of\d+', re.sub(r'\s+', '', f).lower()))
    pages = [[unfooter(l) for l in p] for p in pages]
    # the stamp, also "Update Till ...", and several stamps printed over each other, which -layout interleaves glyph
    # by glyph ("UpdaUteUUpdpdpdaTatdteeidlaTlTtii2llell322d3.2.88..."): a line of only the letters of "updated till",
    # digits and dots, starting "Up"
    def stamp(l: str) -> bool:
        return bool(re.match(r'\s*updated?\s*till\b', l, re.I) or
                    (re.fullmatch(r'\s*up[updateil\d.\s]{8,}', l, re.I) and re.search(r'\d', l)))
    pages = [[l for l in p if l.strip() and not stamp(l)] for p in pages]
    # headers only: a page's last line is often a footnote that recurs on many pages, so it is never taken as furniture
    heads = Counter(key(p[0]) for p in pages if p)
    common = {k for k, c in heads.items() if len(pages) >= 3 and c >= max(3, len(pages) // 3) and k}
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
    # each running header as the parts -layout prints apart ("Page - 480", "ESTACODE (EDITION-2021)", "CHAPTER-5")
    head_parts = {tuple(key(f) for f in re.split(r'\s{2,}', p[0].strip()))
                  for p in pages if p and key(p[0]) in common and re.search(r'\s{2,}', p[0].strip())}

    def scattered(p: list[str]) -> set[str]:
        """The parts of a running header that a page holds apart, on different lines, some below its first line:
        every part with at least 6 letters is there (so a "CHAPTER-5" heading alone is not taken), and no line holds
        them all (a gazette's first page prints its header whole a few lines down), or nothing."""
        frags = [{key(f) for f in re.split(r'\s{2,}', l.strip())} for l in p]
        allf = set().union(*frags) if frags else set()
        for parts in head_parts:
            big = {k for k in parts if len(re.findall(r'[^\W\d_]', k)) >= 6}
            if len(big) >= 2 and big <= allf and any(big & f for f in frags[1:]) and \
                    not any(big <= f for f in frags):
                return set(parts)
        return set()
    keep = []
    for i, p in enumerate(pages):
        # one line at each end at most, so a list of identical rows ("N. Repeal") is not eaten
        if p and (key(p[0]) in common or is_pageno(p[0], i)):
            p.pop(0)
        elif p and common and not any(key(f) in common for f in re.split(r'\s{2,}', p[0].strip())) and scattered(p):
            # a page printed sideways (the Estacode's leave-account form, p.483): -layout scatters the running
            # header's parts over the page's lines; each part is dropped once, wherever it is
            todo = scattered(p)
            for j, l in enumerate(p):
                frags = re.split(r'(\s{2,})', l)
                for n, f in enumerate(frags):
                    if key(f) in todo:
                        todo.discard(key(f))
                        frags[n] = ''
                p[j] = ''.join(frags)
            p[:] = [l for l in p if l.strip()]
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
    # a few PDFs print the footnote marker and number 1 as a lower-case L ("l[Federal Government]", "lSubs. by",
    # "lACT No."); the build reads it as the number, so it is not a letter of the text. Not before a lone capital
    # or other capitals: there it is the digit 1 or the letter I typed as an L, in the text ("section lA", "lCT")
    return '\n'.join(keep) if keep_l else drop_marker_l('\n'.join(keep))


def drop_marker_l(s: str) -> str:
    return re.sub(r'(?<![^\W\d_])l(?=\[|[A-Z][a-z]|ACT\b)', '', s)


# A lone lower-case L (not a clause label "(l)") is ambiguous in these PDFs: it is the marker or footnote number 1
# typed as a letter ("l[Pakistan]" where no footnote 1 is on the page, "l The words ...", "l0[" for 10), or the digit 1
# typed as a letter in the text ("l95l", "l. Title and extent"). It is dropped on both sides, so it never counts.
LONE_L_AT = re.compile(r'(?<![^\W\d_(])l(?![^\W\d_)])')


class _LoneL:
    """LONE_L.sub(' ', s): drop each lone L, except in letter-spaced text ("N a t i o n a l"), where the L next to
    another single letter is part of a word."""

    @staticmethod
    def sub(repl: str, s: str) -> str:
        out, last = [], 0
        for m in LONE_L_AT.finditer(s):
            before = re.search(r'(?:^|[^\w])([^\W\d_])\s+$', s[max(0, m.start() - 4):m.start()])
            after = re.match(r'\s+([^\W\d_])(?:[^\w]|$)', s[m.end():m.end() + 4])
            if before or after:
                continue
            out.append(s[last:m.start()] + repl)
            last = m.end()
        return ''.join(out) + s[last:]


LONE_L = _LoneL()


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


def marker_words(blobs: Blobs, path: str) -> tuple[set[str], set[str]]:
    """The words (casefolded) printed right before and right after a footnote reference in the law's units."""
    before, after = set(), set()
    for n in [n for n in (blobs.get(f'HEAD:{path}/index.txt') or '').split('\n') if n and n != 'notes.md']:
        t = blobs.get(f'HEAD:{path}/{n}') or ''
        before |= {w.casefold() for w in re.findall(r'([^\W\d_]+)(?:\[\^\d+\])+', t)}
        after |= {w.casefold() for w in re.findall(r'(?:\[\^\d+\])+([^\W\d_]+)', t)}
    return before, after


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
    glued: list[str] = []
    lone_l: list[str] = []
    digit_count: list[str] = []
    letters_off = 0
    for row in rows:
        path = row['path'].rstrip('/')
        if args.only and args.only not in path:
            continue
        href = row['source'].rsplit('/english/', 1)[1]
        pdf = CACHE / 'pdf' / fetched[href]['pdf']
        src_raw = pdf_text(pdf, keep_l=True)
        src = Counter(tokens(LONE_L.sub(' ', drop_marker_l(src_raw))))
        text, refs, notes = repo_text(blobs, path)
        mine = Counter(tokens(LONE_L.sub(' ', text)))
        sl = Counter({k: v for k, v in src.items() if not k.isdigit()})
        ml = Counter({k: v for k, v in mine.items() if not k.isdigit()})
        sd = Counter({k: v for k, v in src.items() if k.isdigit()})
        md = Counter({k: v for k, v in mine.items() if k.isdigit()})
        letters_total += sum(ml.values())
        digits_total += sum(md.values())
        problems = []
        if sl != ml:
            # a marker printed as a lower-case L run into the word before or after it ("determined by the rulesl to
            # be"): the PDF's word is the repo's word with an L, and the repo has a footnote reference right there
            before, after = marker_words(blobs, path)
            a, b = sl - ml, ml - sl
            for t, c in list(a.items()):
                for w, near, ok in ((t[:-1], before, t.endswith('l')), (t[1:], after, t.startswith('l'))):
                    if ok and w and w in near and b[w] > 0:
                        k = min(c, b[w])
                        sl[t] -= k
                        sl[w] += k
                        b[w] -= k
                        glued.append(path)
                        break
            sl = +sl
        if sl != ml:
            a, b = sl - ml, ml - sl
            ca, cb = Counter(''.join(k * v for k, v in a.items())), Counter(''.join(k * v for k, v in b.items()))
            if ca == cb:
                spacing.append(path)   # the same letters, broken into words differently
            elif set((ca - cb) | (cb - ca)) == {'l'} and src_raw.count('l') == text.count('l'):
                # only the number of L's differs, and it is the same before lone L's are dropped: the two readers
                # saw a different number of lone L's (text printed over other text, which -layout interleaves glyph
                # by glyph, leaves an L of a word standing alone, or runs a lone one into its neighbours)
                lone_l.append(path)
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
    print(f'  a marker printed as an L run into a word, where the repo has a footnote reference: '
          f'{len(set(glued))} laws {sorted(set(glued))[:args.show]}')
    print(f"  only the number of L's differs, the same before lone L's are dropped: {len(lone_l)} laws "
          f'{lone_l[:args.show]}')
    print(f'  digit-token count not explained exactly by markers + footnote numbers (no digit invented): '
          f'{len(digit_count)} laws {digit_count[:args.show]}')
    print(f'  letters or digits differ: {len(bad)} laws, {letters_off:,} letters in all')
    sys.exit(min(len(bad), 125))


def io_text(s: str | None):
    import io
    return io.StringIO(s or '')


if __name__ == '__main__':
    main()

"""Parse one Pakistan Code PDF (Word-made, consolidated, with footnotes) into units and notes.

    python parse_pdf.py <pdf> [--show]          # print the units of one PDF
    python parse_pdf.py --stats [--limit N]     # survey every cached PDF

The layout (learned from the cache, 2026-10-28):
- every page has a "Page x of y" footer; some first pages carry an "Updated till dd.mm.yyyy" stamp at the top;
- CONTENTS pages come first (non-bold "N." rows), then the title (bold, 14-16pt), the Act or Ordinance number, the
  date, the long title and preamble;
- a section (an Article in the Constitution and in President's Orders) starts a row with "N." or "NA." and a bold
  heading, possibly after a footnote marker and "[": "3[9A. Clean ...";
- footnote markers are digit-only spans at under 0.8 x the size of the row's text; footnotes are 8pt rows at the
  bottom of the page, each starting with its number in a ~5pt span, numbered afresh on every page, and a footnote can
  run on at the bottom of the next page;
- "__" spans at 8pt inside the body are how these PDFs print a dash: they are text and are kept.

Output: a dict with the title rows, contents rows, units (kind, id, heading lines, paragraphs, note numbers), notes
(numbered 1..n in document order across the whole law), the "Updated till" stamps and counts. Nothing is reworded:
spaces are collapsed and the spans of a printed row are joined; markers become `[^n]`.
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

FOOTER = re.compile(r'^Page\d+of\d+$', re.I)
# "3", "2,3,4&5" (several notes at one spot), or a lower-case L that a few PDFs print for the marker 1
MARKER = re.compile(r'\s*(?:\d{1,3}(?:\s*[,&]\s*\d{1,3})*|l)\s*')
PAGENO = re.compile(r'[-–\s]*\d{1,4}[-–\s]*')
STAMP = re.compile(r'^\s*updated\s*till\b', re.I)
SECTION = re.compile(r'^(\d{1,3}[A-Z]{0,3})\s?\.(?=\s|[A-Z(\[“"_*])')
SCHEDULE = re.compile(r'^(?:THE\s+)?(?:(?:FIRST|SECOND|THIRD|FOURTH|FIFTH|SIXTH|SEVENTH|EIGHTH|NINTH|TENTH|ELEVENTH|'
                      r'TWELFTH|THIRTEENTH|FOURTEENTH|FIFTEENTH|SIXTEENTH)\s+)?(?:SCHEDULE|ANNEX|ANNEXURE|APPENDIX)\b'
                      r'(?:[\s\-–—]*[IVXLC0-9]+\b)?')
LABEL = re.compile(r'^(\[\^\d+\])*\[?\(?([a-z]{1,3}|[0-9]{1,3}[A-Z]?|[ivxlc]{1,6}|[A-Z])\)')


@dataclass
class Span:
    x0: float
    x1: float
    y0: float
    y1: float
    size: float
    bold: bool
    text: str
    font: str = ''

    @property
    def h(self) -> float:
        return self.y1 - self.y0


@dataclass
class Row:
    page: int
    spans: list[Span] = field(default_factory=list)
    text: str = ''          # joined, with markers as \x00n\x00 (page-local numbers)
    plain: str = ''         # joined, markers dropped
    size: float = 0.0       # largest size of a span with letters
    x0: float = 0.0
    x1: float = 0.0
    y0: float = 0.0
    y1: float = 0.0

    @property
    def top(self) -> float:
        return self.y0


def _spans(page) -> list[Span]:
    """Every text span of the page, including text that runs past the page's edge: some contents rows and
    table cells are printed wider than the page, and PyMuPDF by default cuts them at the edge ("Governme")."""
    out = []
    flags = pymupdf.TEXTFLAGS_RAWDICT & ~pymupdf.TEXT_MEDIABOX_CLIP
    for b in page.get_text('rawdict', flags=flags)['blocks']:
        for l in b.get('lines', []):
            for s in l['spans']:
                if abs(l['dir'][1]) > 0.01:   # rotated text (a table's column heads): glyph positions run along y
                    text = ''.join(c['c'] for c in s['chars'])
                else:
                    text = _span_text(s['chars'], s['size'])
                if not text:
                    continue
                x0, y0, x1, y1 = s['bbox']
                out.append(Span(x0, x1, y0, y1, round(s['size'], 1), bool(s['flags'] & 16), text, s['font']))
    return out


def _span_text(chars: list[dict], size: float) -> str:
    """A span's text, with the spaces the glyph positions show: some PDFs encode a space of zero width inside a
    word ("execu tion"), and some print words apart with no space character. A space character is kept only where
    the next glyph starts more than 0.1 x the font size after the last one ends; a gap of over 0.3 x the size
    between two glyphs gets a space."""
    out: list[str] = []
    prev_end = None   # x1 of the last glyph that is not a space
    pending = False   # a space character since that glyph
    prev_x0 = None
    for c in chars:
        ch = c['c']
        if ch.isspace():
            pending = True
            continue
        x0 = c['bbox'][0]
        if out and not pending and ch == out[-1] and prev_x0 is not None and abs(x0 - prev_x0) < 0.6 and \
                prev_end - prev_x0 > 1.5:
            continue   # the same glyph printed again on the same spot (fake bold): "Senatte" is "Senate"
        if prev_end is not None:
            gap = x0 - prev_end
            if (pending and gap > 0.1 * size) or gap > 0.3 * size:
                out.append(' ')
        elif pending:
            out.append(' ')   # leading space: kept, it separates the span from the one before
        out.append(ch)
        prev_end = c['bbox'][2]
        prev_x0 = x0
        pending = False
    if pending and out:
        out.append(' ')
    return ''.join(out)


def _group(spans: list[Span], page: int) -> list[Row]:
    rows: list[Row] = []
    for s in sorted([s for s in spans if s.text.strip()], key=lambda s: ((s.y0 + s.y1) / 2, s.x0)):
        best = None
        for r in rows[-6:]:
            ov = min(r.y1, s.y1) - max(r.y0, s.y0)
            if ov >= 0.5 * min(s.h, r.y1 - r.y0):
                best = r
        if best is None:
            best = Row(page, y0=s.y0, y1=s.y1)
            rows.append(best)
        best.spans.append(s)
        # the row's extent follows its largest text, so a superscript does not stretch it
        big = max(x.size for x in best.spans)
        main = [x for x in best.spans if x.size >= 0.9 * big]
        best.y0, best.y1 = min(x.y0 for x in main), max(x.y1 for x in main)
    for r in rows:
        r.spans.sort(key=lambda s: s.x0)
        # drop exact overlays (some stamps and headings are printed twice on the same spot)
        keep: list[Span] = []
        for s in r.spans:
            if any(k.text == s.text and abs(k.x0 - s.x0) < 1 and abs(k.y0 - s.y0) < 1 for k in keep):
                continue
            keep.append(s)
        r.spans = keep
        letters = [s.size for s in r.spans if re.search(r'[^\W\d_]', s.text)]
        r.size = max(letters) if letters else max(s.size for s in r.spans)
        r.x0 = min(s.x0 for s in r.spans)
        r.x1 = max(s.x1 for s in r.spans)
    rows.sort(key=lambda r: r.y0)
    return rows


def is_marker(s: Span, row_size: float) -> bool:
    return bool(MARKER.fullmatch(s.text)) and s.size <= 0.8 * row_size


def _join(row: Row) -> None:
    parts: list[str] = []
    plain: list[str] = []
    prev = None
    for s in row.spans:
        mark = is_marker(s, row.size)
        t = f'\x00{s.text.strip()}\x00' if mark else s.text
        if prev is not None and parts:
            gap = s.x0 - prev.x1
            # a gap, or a span that starts left of the last one's end (the next line of a wrapped table cell)
            if (gap > 0.1 * max(s.size, prev.size, 4) or s.x0 < prev.x0 + 0.5) and \
                    not parts[-1].endswith((' ', '\x00')) and not t.startswith(' ') and not mark:
                parts.append(' ')
                plain.append(' ')
        parts.append(t)
        if not mark:
            plain.append(s.text)
        prev = s
    row.text = re.sub(r'\s+', ' ', ''.join(parts)).strip()
    row.plain = re.sub(r'\s+', ' ', ''.join(plain)).strip()


@dataclass
class Para:
    rows: list[Row]
    text: str = ''

    @property
    def page(self) -> int:
        return self.rows[0].page


def parse(pdf: Path) -> dict:
    doc = pymupdf.open(str(pdf))
    pages: list[list[Row]] = []
    stamps: list[str] = []
    scan_pages = 0
    invisible = 0
    empty_pages: list[int] = []
    heights = [doc[i].rect.height for i in range(len(doc))]
    width = doc[0].rect.width if len(doc) else 595
    for pn in range(len(doc)):
        area = doc[pn].rect.width * doc[pn].rect.height
        if any((im['bbox'][2] - im['bbox'][0]) * (im['bbox'][3] - im['bbox'][1]) >= 0.5 * area
               for im in doc[pn].get_image_info()):
            scan_pages += 1   # a page-sized picture: a scan, or (often) a Word page with a background image
        for tr in doc[pn].get_texttrace():
            if tr['type'] == 3:   # text render mode 3, invisible: the OCR layer laid over a scanned page
                invisible += len(tr['chars'])
        rows = _group(_spans(doc[pn]), pn)
        for r in rows:
            _join(r)
        keep = []
        for r in rows:
            if FOOTER.match(r.plain.replace(' ', '')):
                continue
            if STAMP.match(r.plain):
                st = re.sub(r'\s+', ' ', r.plain).strip()
                if st not in stamps:
                    stamps.append(st)
                continue
            keep.append(r)
        pages.append(keep)
        if sum(len(r.plain) for r in keep) < 40:
            empty_pages.append(pn + 1)   # a page with no text: a scanned page, a picture or a blank
    # running headers and footers: the first or last row of a page when the same text (digits aside) is the first or
    # last row of at least half the pages, and bare page numbers at the bottom or top
    furniture = 0
    if len(pages) >= 3:
        def key(r: Row) -> str:
            return re.sub(r'\d+', '#', r.plain.replace(' ', '').lower())
        ends = Counter()
        for rows in pages:
            # rows at footnote size never count: the same footnote is often the last row of many pages
            for r in {id(x): x for x in rows[:1] + rows[-1:]
                      if x.size >= 10 and not (re.fullmatch(r'\s*\d{1,3}\s*', x.spans[0].text)
                                               and x.spans[0].size < 0.8 * x.size)}.values():
                ends[key(r)] += 1
        common = {k for k, c in ends.items() if c >= max(3, len(pages) // 2) and k}
        for pn, rows in enumerate(pages):
            hgt = heights[pn]
            # only in the top and bottom margins: a list of "N. Repeal" rows also repeats at the top of pages
            while rows and rows[0].y1 < 0.15 * hgt and (key(rows[0]) in common or PAGENO.fullmatch(rows[0].plain)):
                rows.pop(0)
                furniture += 1
            while rows and rows[-1].y0 > 0.8 * hgt and (key(rows[-1]) in common or PAGENO.fullmatch(rows[-1].plain)):
                rows.pop()
                furniture += 1
    else:
        # a law of one or two pages: only a bare number in the margin that is the page's own number
        for pn, rows in enumerate(pages):
            hgt = heights[pn]
            for i in (-1, 0):
                if rows and (rows[i].y0 > 0.8 * hgt if i else rows[i].y1 < 0.15 * hgt) and \
                        re.fullmatch(r'[-–\s]*(\d{1,4})[-–\s]*', rows[i].plain) and \
                        int(re.sub(r'\D', '', rows[i].plain)) == pn + 1:
                    rows.pop(i)
                    furniture += 1
    chars = Counter()
    ocr = 0
    for rows in pages:
        for r in rows:
            for s in r.spans:
                chars[s.size] += len(s.text.strip())
                if re.search(r'OCR|GlyphLess', s.font, re.I):
                    ocr += len(s.text.strip())
    body = max(chars, key=chars.get) if chars else 12.0
    text_layer = sum(chars.values())

    # ---- footnote zones: the run of small rows at the bottom of a page
    notes: list[dict] = []          # {'page', 'n', 'text'}
    note_at: dict[tuple[int, int], int] = {}
    body_rows: list[Row] = []
    def digits_only(r: Row) -> bool:
        return all(re.fullmatch(r'\s*\d{0,3}\s*', s.text) for s in r.spans) and bool(r.plain.strip())

    def note_start(r: Row, expected: set[int]) -> tuple[int, list[Span]] | None:
        """(number, the rest of the row) when the row starts a footnote: a small number span, or (in some PDFs) the
        number printed at the text's size and run into its first word ("1Proviso ins. ..."), which is taken only
        when it is the number expected next, so a continuation line starting with a year is not mistaken for one."""
        first = r.spans[0]
        if re.fullmatch(r'\s*\d{1,3}\s*', first.text) and first.size < 0.92 * r.size and len(r.spans) > 1:
            return int(first.text), r.spans[1:]
        if first.text.strip() == 'l' and first.size < 0.8 * r.size and len(r.spans) > 1:
            return 1, r.spans[1:]   # a lower-case L typed for the number 1 (seen in a few PDFs)
        m = re.match(r'^\s*(\d{1,3})(?=[^\W\d_]|[\[“"(*‘\'])', first.text)
        if m and int(m.group(1)) in expected:
            s = Span(first.x0, first.x1, first.y0, first.y1, first.size, first.bold, first.text[m.end():])
            return int(m.group(1)), [s] + r.spans[1:]
        return None

    for pn, rows in enumerate(pages):
        small = 0.86 * body
        k = len(rows)
        while k > 0 and rows[k - 1].size <= small:
            k -= 1
        zone = rows[k:]
        last_n = notes[-1]['n'] if notes else 0
        numbered = [r for r in zone if note_start(r, {1, last_n + 1}) or digits_only(r)]
        if zone and not numbered and not (notes and notes[-1]['page'] == pn - 1):
            zone = []
            k = len(rows)
        rest_body = rows[:k]
        if not zone:
            # a few PDFs print body text below the footnotes: then the notes are the small rows from the first
            # small numbered row in the lower half of the page down, and larger rows stay body
            hgt = heights[pn]
            j = next((i for i, r in enumerate(rows) if r.size <= small and r.y0 > 0.5 * hgt
                      and (note_start(r, {1, last_n + 1}) or (digits_only(r) and r.size <= 7))), None)
            if j is not None:
                zone = [r for r in rows[j:] if r.size <= small]
                rest_body = rows[:j] + [r for r in rows[j:] if r.size > small]
        body_rows += rest_body
        pending = None
        page_notes = 0
        for r in zone:
            if digits_only(r) and r.size <= 7:
                pending = int(r.plain.split()[0])
                continue
            expected = {notes[-1]['n'] + 1} if page_notes else {1, (notes[-1]['n'] + 1) if notes else 1}
            hit = (pending, r.spans) if pending is not None else note_start(r, expected)
            pending = None
            if hit:
                n, rest_spans = hit
                rest = Row(pn, rest_spans, size=r.size)
                _join(rest)
                note_at.setdefault((pn, n), len(notes))
                notes.append({'page': pn, 'n': n, 'text': rest.text.replace('\x00', '')})
                page_notes += 1
            elif notes:
                notes[-1]['text'] = (notes[-1]['text'] + ' ' + r.text.replace('\x00', '')).strip()
            else:
                body_rows.append(r)
    for i, nt in enumerate(notes, 1):
        nt['g'] = i
        nt['text'] = re.sub(r'\s+', ' ', nt['text']).strip()

    unresolved: list[str] = []

    def resolve(row: Row) -> str:
        """Markers become [^g]; a small number with no footnote of that number on its page stays as printed."""
        def sub(m):
            nums = [int(x) for x in re.findall(r'\d+', m.group(1))] or [1]   # 'l' is the marker 1
            idx = [note_at.get((row.page, n)) for n in nums]
            if any(i is None for i in idx):
                unresolved.append(f'p{row.page + 1} #{m.group(1).strip()}: {row.plain[:70]}')
                return m.group(1).strip()
            return ''.join(f'[^{notes[i]["g"]}]' for i in idx)
        return re.sub(r'\x00([^\x00]*)\x00', sub, row.text)

    # ---- paragraphs
    xs0 = sorted(r.x0 for r in body_rows if r.size >= 0.9 * body)
    xs1 = sorted(r.x1 for r in body_rows if r.size >= 0.9 * body)
    # the text margins: the 5th percentile of row starts and the 95th of row ends (a stray wide row is ignored)
    left = xs0[len(xs0) // 20] if xs0 else 72
    deltas = Counter()
    for a, b in zip(body_rows, body_rows[1:]):
        if a.page == b.page and a.size >= 0.9 * body and b.size >= 0.9 * body:
            d = round(b.y0 - a.y0)
            if 0.8 * body <= d <= 3 * body:
                deltas[d] += 1
    total = sum(deltas.values())
    common = sorted(d for d, c in deltas.items() if c >= 0.05 * total) if total else []
    line_gap = common[0] if common else round(1.2 * body)

    right = xs1[min(len(xs1) - 1, len(xs1) * 19 // 20)] if xs1 else width - 72

    def centred(r: Row) -> bool:
        """A heading row: centred between the margins, short, and in capitals or bold (PART I, CHAPTER II)."""
        mid = (r.x0 + r.x1) / 2
        if not (r.x0 > left + 30 and len(r.plain) < 120 and
                (abs(mid - (left + right) / 2) < 20 or abs(mid - width / 2) < 20)):
            return False
        letters = re.sub(r'[^\W\d_]', '', r.plain) != r.plain
        words = [s for s in r.spans if s.text.strip() and not is_marker(s, r.size)]
        return (not letters) or r.plain.upper() == r.plain or all(s.bold for s in words)

    def starts_section(r: Row) -> str | None:
        t = re.sub(r'^(\x00[^\x00]*\x00|\[|\s)+', '', r.text)
        m = SECTION.match(t)
        if not m:
            return None
        # a bold heading among the first spans (the number itself may be plain)
        seen = 0
        for s in r.spans:
            if is_marker(s, r.size) or not s.text.strip() or s.text.strip() in '[':
                continue
            seen += 1
            if s.bold and len(re.findall(r'[^\W\d_]', s.text)) >= 2:
                return m.group(1)
            if seen >= 3:
                break
        return None

    paras: list[Para] = []
    for i, r in enumerate(body_rows):
        prev = body_rows[i - 1] if i else None
        sec = starts_section(r)
        new = prev is None or sec is not None or centred(r) or (prev is not None and centred(prev))
        if not new and prev is not None:
            if r.page != prev.page:
                last = paras[-1].text if paras else ''
                new = bool(re.search(r'[.;:_—]\]?\s*$', last)) or not re.match(r'^[a-z]', r.plain or 'X')
            else:
                d = r.y0 - prev.y0
                new = d > 1.35 * line_gap or d < -1
                if not new and LABEL.match(r.plain) and re.search(r'[.;:_—]\]?\s*$', prev.plain) and r.x0 > left + 10:
                    new = True
        t = resolve(r)
        if new:
            paras.append(Para([r], t))
        else:
            p = paras[-1]
            p.rows.append(r)
            if re.search(r'[^\W\d_]-$', p.text) and re.match(r'^[a-z]', t):
                p.text += t
            else:
                p.text += ' ' + t
    for p in paras:
        p.text = re.sub(r'\s+', ' ', p.text).strip()

    # ---- front matter, units
    contents_at = next((i for i, p in enumerate(paras[:400]) if re.fullmatch(r'CONTENTS?\.?', p.text.strip(), re.I)),
                       None)
    def sched_head(p: Para) -> bool:
        t = re.sub(r'^(\[\^\d+\]|\[|\s)+', '', p.text)
        return bool(SCHEDULE.match(t)) and (centred(p.rows[0]) or t[:12].isupper()) and len(t) < 200

    def big_bold(p: Para) -> bool:
        r = p.rows[0]
        return r.size >= max(13.5, body + 1.5) and any(s.bold for s in r.spans) and \
            len(re.findall(r'[^\W\d_]', r.plain)) >= 3

    title_rows: list[str] = []
    contents_rows: list[str] = []
    start = 0
    if contents_at is not None:
        # the contents run until the title is printed again (large, bold), or else until the first bold section
        body_title = next((i for i in range(contents_at + 1, len(paras)) if big_bold(paras[i])), None)
        if body_title is None:
            body_title = next((i for i in range(contents_at + 1, len(paras)) if starts_section(paras[i].rows[0])),
                              len(paras))
        title_rows = [p.text for p in paras[:contents_at]]
        contents_rows = [p.text for p in paras[contents_at:body_title]]
        start = body_title
    # the first section; a schedule heading only when the law has no sections (a contents list may name the
    # schedules before the first section)
    first_unit = next((i for i in range(start, len(paras)) if starts_section(paras[i].rows[0])), None)
    if first_unit is None:
        first_unit = next((i for i in range(start, len(paras)) if sched_head(paras[i])), None)
    front = paras[start:first_unit if first_unit is not None else len(paras)]
    # centred headings right before the first unit belong to it
    pending: list[str] = []
    while front and first_unit is not None and centred(front[-1].rows[0]) and not big_bold(front[-1]):
        pending.insert(0, front.pop().text)
    title_rows += [p.text for p in front]

    kind = 'section'
    units: list[dict] = []
    if first_unit is not None:
        cur: dict | None = None
        buf: list[str] = list(pending)
        in_schedule = False
        n_sched = 0
        seen: Counter = Counter()

        def open_unit(kind_: str, num: str) -> dict:
            seen[(kind_, num)] += 1
            uid = f'{kind_}-{num}' + (f'~{seen[(kind_, num)]}' if seen[(kind_, num)] > 1 else '')
            u = {'kind': kind_, 'num': num, 'id': uid, 'lines': []}
            units.append(u)
            return u

        for p in paras[first_unit:]:
            r = p.rows[0]
            if sched_head(p):
                in_schedule = True
                n_sched += 1
                cur = open_unit('schedule', str(n_sched))
                cur['lines'] += buf + [p.text]
                buf = []
                continue
            sec = None if in_schedule else starts_section(r)
            if sec:
                cur = open_unit('section', sec)
                cur['lines'] += [f'## {b}' if re.search(r'[^\W\d_]', b) else b for b in buf] + [p.text]
                buf = []
                continue
            if centred(r):
                buf.append(p.text)
                continue
            if cur is None:
                cur = open_unit('text', '1')
            cur['lines'] += buf + [p.text]
            buf = []
        if buf:
            if cur is None:
                cur = open_unit('text', '1')
            cur['lines'] += buf
    for u in units:
        u['notes'] = sorted({int(n) for l in u['lines'] for n in re.findall(r'\[\^(\d+)\]', l)})
    title_notes = sorted({int(n) for l in title_rows + contents_rows for n in re.findall(r'\[\^(\d+)\]', l)})
    return {'pages': len(doc), 'body_size': body, 'text_layer': text_layer, 'ocr_chars': ocr, 'scan_pages': scan_pages, 'invisible_chars': invisible, 'empty_pages': empty_pages, 'stamps': stamps,
            'title': title_rows, 'contents': contents_rows, 'title_notes': title_notes, 'units': units,
            'notes': [{'g': n['g'], 'page': n['page'] + 1, 'n': n['n'], 'text': n['text']} for n in notes],
            'unresolved_markers': len(unresolved), 'unresolved': unresolved, 'line_gap': line_gap, 'kind': kind}


def main() -> None:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if sys.argv[1] == '--batch':
        # parse_pdf.py --batch <outdir> <pdf> ...: one JSON per PDF (build.py runs several of these at once, as
        # separate processes: PyMuPDF does not load in multiprocessing's spawned workers on this machine)
        import hashlib
        import json
        out = Path(sys.argv[2])
        for f in sys.argv[3:]:
            p = Path(f)
            try:
                r = parse(p)
            except Exception as e:  # noqa: BLE001 - reported per PDF
                r = {'error': f'parse failed: {type(e).__name__}: {e}'}
            r['sha256'] = hashlib.sha256(p.read_bytes()).hexdigest()
            tmp = out / (p.name + '.json.part')
            tmp.write_text(json.dumps(r, ensure_ascii=False), 'utf-8')
            tmp.replace(out / (p.name + '.json'))
        return
    if sys.argv[1] == '--stats':
        import glob
        files = sorted(glob.glob(str(Path(__file__).parent / '.cache' / 'pdf' / '*.pdf')))
        lim = int(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[2] == '--limit' else None
        for f in files[:lim]:
            r = parse(Path(f))
            secs = sum(1 for u in r['units'] if u['kind'] == 'section')
            print(f"{Path(f).name[13:25]} p={r['pages']} body={r['body_size']} ocr={r['ocr_chars']}/{r['text_layer']} scan={r['scan_pages']} gap={r['line_gap']} secs={secs} "
                  f"sch={sum(1 for u in r['units'] if u['kind'] == 'schedule')} notes={len(r['notes'])} "
                  f"unres={r['unresolved_markers']} contents={len(r['contents'])} title={len(r['title'])} "
                  f"stamp={r['stamps']} t0={(r['title'][:1] or [''])[0][:50]!r}", flush=True)
        return
    r = parse(Path(sys.argv[1]))
    print('STAMPS', r['stamps'], 'unresolved', r['unresolved'], 'gap', r['line_gap'])
    print('== TITLE'); print('\n'.join(r['title']))
    print('== CONTENTS', len(r['contents'])); print('\n'.join(r['contents'][:8]))
    for u in r['units']:
        print('==', u['id'], u['notes']); print('\n'.join(u['lines']))
    print('== NOTES')
    for n in r['notes']:
        print(f"[^{n['g']}] (p{n['page']} #{n['n']}): {n['text']}")


if __name__ == '__main__':
    main()

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
STAMP = re.compile(r'^\s*updated?\s*till\b', re.I)   # also "Update Till 22.8.2022" (Safeguard Measures Ordinance)
SECTION = re.compile(r'^(\d{1,3}[A-Z]{0,3})\s?\.(?=\s|[A-Z(\[“"_*])')
SCHEDULE = re.compile(r'^(?:THE\s+)?(?:(?:FIRST|SECOND|THIRD|FOURTH|FIFTH|SIXTH|SEVENTH|EIGHTH|NINTH|TENTH|ELEVENTH|'
                      r'TWELFTH|THIRTEENTH|FOURTEENTH|FIFTEENTH|SIXTEENTH)\s+)?(?:SCHEDULE|ANNEX|ANNEXURE|APPENDIX)\b'
                      r'(?:[\s\-–—]*[IVXLC0-9]+\b)?')
LR_HEAD = re.compile(r'LEGAL\s+REFERENCES?', re.I)
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
    dom: float = 0.0        # the size most of its letters are printed at (a footnote's 11pt "I" aside)
    x0: float = 0.0
    x1: float = 0.0
    y0: float = 0.0
    y1: float = 0.0
    block: int = -1         # the LEGAL REFERENCE block its markers refer to (-1: none)

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
                if text.strip() and all('' <= ch <= '' for ch in text.strip()):
                    # a number in a symbol font, whose digits sit in the private use area (U+F031 for "1"): the
                    # footnote numbers of the NAB Ordinance in the Estacode, while its markers are plain digits
                    text = text.translate({cp: cp - 0xF000 for cp in range(0xF030, 0xF03A)})
                if s.get('alpha', 255) < 128 and not re.search(r'\w', text):
                    continue   # a translucent watermark: the big grey ".." printed twice on every Income Tax page
                x0, y0, x1, y1 = s['bbox']
                out.append(Span(x0, x1, y0, y1, round(s['size'], 1), bool(s['flags'] & 16), text, s['font']))
    return out


def _span_text(chars: list[dict], size: float) -> str:
    """A span's text, with the spaces the glyph positions show: some PDFs encode a space of zero width inside a
    word ("execu tion"), and some print words apart with no space character. A space character is kept only where
    the next glyph starts more than 0.1 x the font size after the last one ends; a gap of over 0.3 x the size
    between two glyphs gets a space."""
    if any('؀' <= c['c'] <= 'ۿ' for c in chars):
        # Arabic script runs right to left, so the glyph-position rules below do not apply: they took the two alefs
        # of "الا" (Qanun-e-Shahadat art. 71), printed at almost the same spot, for one glyph printed twice, and
        # dropped the spaces between the words. The span's characters are kept as given.
        return re.sub(r'\s+', ' ', ''.join(c['c'] for c in chars))
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
        by: Counter = Counter()
        for s in r.spans:
            by[s.size] += len(re.findall(r'[^\W\d_]', s.text))
        r.dom = max(by, key=lambda z: (by[z], z)) if sum(by.values()) else r.size
        r.x0 = min(s.x0 for s in r.spans)
        r.x1 = max(s.x1 for s in r.spans)
    rows.sort(key=lambda r: r.y0)
    # a footnote marker raised so far above its line that it formed a row of its own ("l" over "ACT No. XI OF 1886",
    # "l" over "Subs. by A. O., 1937"): it belongs to the row below it when it touches that row and is at most 0.8 x
    # its size
    out: list[Row] = []
    for i, r in enumerate(rows):
        nxt = rows[i + 1] if i + 1 < len(rows) else None
        if nxt is not None and all(MARKER.fullmatch(s.text) for s in r.spans) and \
                max(s.size for s in r.spans) <= 0.8 * nxt.size and r.y1 > nxt.y0 and r.y0 < nxt.y0:
            nxt.spans = sorted(r.spans + nxt.spans, key=lambda s: s.x0)
            continue
        out.append(r)
    return out


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
    # running headers and footers: the first or last row of a page when the same text (digits and markers aside) is
    # the first or last row of at least a third of the pages (odd and even pages often alternate two headers:
    # "CHAPTER-4 ESTACODE (EDITION-2021) Page - 317", "Page -318 ESTACODE (EDITION-2021) CHAPTER-4"), and bare page
    # numbers at the bottom or top
    furniture = 0
    if len(pages) >= 3:
        def key(r: Row) -> str:
            t = re.sub(r'\x00[^\x00]*\x00|\d+', '#', r.text.replace(' ', '').lower())
            return re.sub(r'#+', '#', t)
        ends = Counter()
        for rows in pages:
            # rows at footnote size never count: the same footnote is often the last row of many pages
            for r in {id(x): x for x in rows[:1] + rows[-1:]
                      if x.size >= 10 and not (re.fullmatch(r'\s*\d{1,3}\s*', x.spans[0].text)
                                               and x.spans[0].size < 0.8 * x.size)}.values():
                ends[key(r)] += 1
        # a numbered row ("16. Repeal", "#.repeal") is a contents or section row, never a running header
        common = {k for k, c in ends.items() if c >= max(3, len(pages) // 3) and k and not re.match(r'#[a-z]{0,3}\.', k)}
        for pn, rows in enumerate(pages):
            hgt = heights[pn]
            # only in the top and bottom margins, and one running row at each end: a list of "N. Repeal" rows also
            # repeats at the top and foot of pages
            for i, inside in ((0, lambda r: r.y1 < 0.18 * hgt), (-1, lambda r: r.y0 > 0.8 * hgt)):
                took = False
                while rows and inside(rows[i]) and (PAGENO.fullmatch(rows[i].plain) or
                                                    (not took and key(rows[i]) in common)):
                    took = took or not PAGENO.fullmatch(rows[i].plain)
                    rows.pop(i)
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
    body_chars = Counter()   # without the footnotes: in a short law with long notes they outweigh the body text
    ocr = 0
    for pn, rows in enumerate(pages):
        # the first footnote: a row in the lower part of the page, smaller than the full rows of text above it,
        # starting with a small number (a body row that starts with a marker, "3[9A. ...", is not smaller)
        j = next((i for i, r in enumerate(rows) if r.y0 > 0.4 * heights[pn] and len(r.spans) > 1 and
                  re.fullmatch(r'\s*(\d{1,3}|l)\s*', r.spans[0].text) and r.spans[0].size < 0.8 * r.size and
                  r.size < 0.9 * max([x.size for x in rows[:i] if len(x.plain) >= 40] or [0])), len(rows))
        note_size = rows[j].size if j < len(rows) else 0
        for i, r in enumerate(rows):
            in_notes = i >= j and r.size <= note_size
            for s in r.spans:
                chars[s.size] += len(s.text.strip())
                if not in_notes:
                    body_chars[s.size] += len(s.text.strip())
                if re.search(r'OCR|GlyphLess', s.font, re.I):
                    ocr += len(s.text.strip())
    sizes = body_chars or chars
    body = max(sizes, key=sizes.get) if sizes else 12.0
    text_layer = sum(chars.values())

    # ---- "LEGAL REFERENCE" blocks (the Customs Act, as FBR publishes it): the notes are not at the foot of each page
    # but in a block under that heading after a group of sections, numbered afresh in each block ("1. Substituted by
    # ..."), printed smaller than the text and running on over pages until the text resumes. The markers since the
    # last block refer to the notes of the next one. The heading stays in the text; the block's rows become notes.
    lr_notes: list[dict] = []
    lr_at: dict[tuple[int, str], list[dict]] = {}
    if any(LR_HEAD.fullmatch(r.plain.strip()) for rows in pages for r in rows):
        k, inside, first_x, seen, cur = 0, False, None, set(), None
        for pn, rows in enumerate(pages):
            keep = []
            for r in rows:
                if LR_HEAD.fullmatch(r.plain.strip()):
                    r.block = k
                    keep.append(r)
                    blk, k, inside, first_x, seen, cur = k, k + 1, True, None, set(), None
                    continue
                if inside and r.size <= 0.86 * body:
                    t = r.text.replace('\x00', '')
                    m = re.match(r'^\s*(\d{1,3}[a-z]?)\s*(\.)?\s*(?=\S)', t)
                    last = max((int(re.sub(r'\D', '', x)) for x in seen), default=0)
                    if m and m.group(1) not in seen and (first_x is None or r.x0 < first_x + 15) and \
                            (m.group(2) or m.group(1) == str(last + 1)):
                        first_x = r.x0 if first_x is None else first_x
                        seen.add(m.group(1))
                        # a note added later between two others, "8a.", keeps its printed label: no marker form
                        # names it apart from note 8
                        text = t[m.end():] if m.group(1).isdigit() else t.lstrip()
                        cur = {'page': pn, 'n': m.group(1), 'text': text, 'y': r.y0, 'block': blk}
                        lr_notes.append(cur)
                        lr_at.setdefault((blk, m.group(1)), []).append(cur)
                    elif cur is not None:
                        cur['text'] += ' ' + t
                    else:
                        r.block = k
                        keep.append(r)
                    continue
                inside = False
                r.block = k
                keep.append(r)
            pages[pn] = keep

    # ---- footnote zones: the run of small rows at the bottom of a page
    notes: list[dict] = []          # {'page', 'n', 'text', 'y'}
    note_at: dict[tuple[int, int], dict] = {}
    body_rows: list[Row] = []
    def digits_only(r: Row) -> bool:
        return all(re.fullmatch(r'\s*\d{0,3}\s*', s.text) for s in r.spans) and bool(r.plain.strip())

    def note_start(r: Row, expected: set[int], marks: set[int] = frozenset()) -> tuple[int, list[Span]] | None:
        """(number, the rest of the row) when the row starts a footnote: a small number span, or (in some PDFs) the
        number printed at the text's size and run into its first word ("1Proviso ins. ..."), which is taken only
        when it is the number expected next, so a continuation line starting with a year is not mistaken for one."""
        spans = r.spans
        # stray dots printed before the number (".. 1 Expression inserted by ..." in the Income Tax Ordinance)
        while len(spans) > 1 and re.fullmatch(r'[\s.]*', spans[0].text):
            spans = spans[1:]
        first = spans[0]
        if re.match(r'\s*\.+\s*\d', first.text):
            first = Span(first.x0, first.x1, first.y0, first.y1, first.size, first.bold, re.sub(r'^\s*\.+\s*', '', first.text))
            spans = [first] + spans[1:]
        if re.fullmatch(r'\s*\d{1,3}\s*', first.text) and first.size < 0.92 * r.size and len(spans) > 1:
            return int(first.text), spans[1:]
        if first.text.strip() == 'l' and first.size < 0.8 * r.size and len(spans) > 1:
            return 1, spans[1:]   # a lower-case L typed for the number 1 (seen in a few PDFs)
        if re.fullmatch(r'\s*\d{1,3}\s*', first.text) and int(first.text) in expected and len(spans) > 1 and \
                r.dom <= near and first.size <= r.dom and int(first.text) in marks:
            # the number printed apart, at the note's own size (8pt "3"), when the page's text has a marker of that
            # number (a contents list printed small, "1  Short title", has none)
            return int(first.text), spans[1:]
        m = re.match(r'^\s*(\d{1,3})(?=[^\W\d_]|[\[“"(*‘\'])', first.text)
        if m and int(m.group(1)) in expected:
            s = Span(first.x0, first.x1, first.y0, first.y1, first.size, first.bold, first.text[m.end():])
            return int(m.group(1)), [s] + spans[1:]
        return None

    def small_number_first(r: Row) -> bool:
        spans = [s for s in r.spans if not re.fullmatch(r'[\s.]*', s.text)]
        return len(spans) > 1 and bool(re.fullmatch(r'\s*\.*\s*(\d{1,3}|l)\s*', spans[0].text)) and \
            spans[0].size < 0.8 * body

    page_marks: dict[int, set[int]] = {}   # the marker numbers in each page's text
    # the size footnotes are printed at: the most common size of rows starting with a small number low on a page.
    # Rows a little larger than that (9pt notes under 10pt text, one 11pt letter) can still be notes; rows at a
    # table's size (10pt under 12pt text, notes at 6pt) cannot
    note_doms = Counter(r.dom for pn, rows in enumerate(pages) for r in rows
                        if r.dom <= 0.86 * body and r.y0 > 0.4 * heights[pn] and small_number_first(r))
    note_dom = max(note_doms, key=lambda z: (note_doms[z], -z)) if note_doms else 0.86 * body
    near = min(0.9 * body, 1.15 * note_dom)
    for pn, rows in enumerate(pages):
        small = 0.86 * body
        # notes that ran out of room at the foot of the last page and are printed at the top of this one, before the
        # text resumes (the Mines Act: marker 7 on page 5, note 7 at the top of page 6): small rows at the top of
        # the page, the first starting with the number after the last page's last note
        # A page that prints none of its own notes may have all of them at the top of the next page (the Mines
        # Act, pages 10-12): taken only when those notes are numbered 1..m and the page's markers are exactly 1..m.
        if pn and rows:
            t = 0
            while t < len(rows) and rows[t].dom <= near and rows[t].y1 < 0.3 * heights[pn]:
                t += 1
            first = None
            if t and small_number_first(rows[0]):
                if notes and notes[-1]['page'] == pn - 1 and notes[-1]['n'] + 1 in page_marks.get(pn - 1, ()):
                    first = notes[-1]['n'] + 1
                elif not any(nt['page'] == pn - 1 for nt in notes):
                    nums = [h[0] for h in (note_start(r, set()) for r in rows[:t] if small_number_first(r)) if h]
                    marks = page_marks.get(pn - 1, set())
                    if nums and nums == list(range(1, len(nums) + 1)) and marks == set(nums):
                        first = 1
            hit = note_start(rows[0], {first}) if first else None
            if hit and hit[0] == first:
                for r in rows[:t]:
                    hit = note_start(r, {notes[-1]['n'] + 1} if notes and notes[-1]['page'] == pn - 1 else {1})
                    if hit and small_number_first(r):
                        rest = Row(pn, hit[1], size=r.size)
                        _join(rest)
                        nt = {'page': pn - 1, 'n': hit[0], 'text': rest.text.replace('\x00', ''), 'y': 10000 + r.y0}
                        note_at.setdefault((pn - 1, hit[0]), nt)
                        notes.append(nt)
                    else:
                        notes[-1]['text'] = (notes[-1]['text'] + ' ' + r.text.replace('\x00', '')).strip()
                rows = pages[pn] = rows[t:]
        k = len(rows)
        while k > 0 and rows[k - 1].size <= small:
            k -= 1
        # a footnote row with a word or two at a larger size (an 11pt "I" in "Inserted", a quoted 10pt word) or
        # printed at 9pt under a 10pt text: the zone reaches up to the first row starting with a small number
        # whose letters are mostly smaller than the text, when every row from there down is, and the numbers of
        # the first row's number is not used again by a row below it (a 9pt table row "1[3204.1100" above note 1
        # is not a note)
        i = k
        while i > 0 and rows[i - 1].dom <= near:
            i -= 1
        last_n = notes[-1]['n'] if notes else 0

        def number_not_repeated(x: int) -> bool:
            nums = []
            for r in rows[x:]:
                if small_number_first(r):
                    t = [s for s in r.spans if not re.fullmatch(r'[\s.]*', s.text)][0].text
                    nums.append(1 if t.strip(' .') == 'l' else int(t.strip(' .')))
            # the first number does not come again further down (the note of that number is lower)
            return bool(nums) and nums[0] not in nums[1:]

        up = next((x for x in range(i, k) if small_number_first(rows[x]) and rows[x].y0 > 0.2 * heights[pn] and
                   note_start(rows[x], {1, last_n + 1}) and number_not_repeated(x)), None)
        if up is not None:
            k = up
        zone = rows[k:]
        last_n = notes[-1]['n'] if notes else 0
        marks_here = {int(x) for r in rows[:k] for m in re.findall(r'\x00([^\x00]*)\x00', r.text)
                      for x in (re.findall(r'\d+', m) or ['1'])} | page_marks.get(pn - 1, set())
        numbered = [r for r in zone if note_start(r, {1, last_n + 1}, marks_here) or digits_only(r)]
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
        page_marks[pn] = {int(x) for r in rest_body for m in re.findall(r'\x00([^\x00]*)\x00', r.text)
                          for x in (re.findall(r'\d+', m) or ['1'])}
        pending = None
        page_notes = 0
        # the last page's notes may run on at the foot of this one before this page's own notes, numbered 1 again
        # (Income Tax Ordinance p.347: the end of p.346's note 1, then its notes 2 and 3, then p.347's notes 1-5).
        # A note there is the last page's when it is numbered one after that page's last note, the last page has a
        # marker of that number with no note, and either this page has no such marker or its own notes follow,
        # starting at 1.
        left = min((r.x0 for r in zone), default=0)
        starts = [note_start(r, {1}) for r in zone]
        restart = any(h and h[0] == 1 for h in starts)
        spill = bool(notes) and notes[-1]['page'] == pn - 1
        marks = page_marks[pn] | (page_marks.get(pn - 1, set()) if spill else set())
        for r in zone:
            if digits_only(r) and r.size <= 7:
                pending = int(r.plain.split()[0])
                continue
            expected = {notes[-1]['n'] + 1} if page_notes and not spill else \
                {1, (notes[-1]['n'] + 1) if notes else 1}
            hit = (pending, r.spans) if pending is not None else note_start(r, expected, marks)
            if hit is None and r.x0 <= left + 1:
                # "2 Clause (90) omitted ...": the expected number, a space and a capital, at the notes' margin, when
                # the page has a marker of that number (not a lower-case word: "... A.O. 1964, Art. / 2 and Sch." is
                # a note running on)
                m = re.match(r'^\s*(\d{1,3}) (?=[A-Z“"])', r.spans[0].text)
                if m and int(m.group(1)) in expected and r.dom <= near and int(m.group(1)) in marks:
                    s0 = r.spans[0]
                    hit = int(m.group(1)), [Span(s0.x0, s0.x1, s0.y0, s0.y1, s0.size, s0.bold,
                                                 s0.text[m.end():])] + r.spans[1:]
            pending = None
            if hit:
                n, rest_spans = hit
                owner = pn
                if spill and notes and n == notes[-1]['n'] + 1 and n != 1 and n in page_marks.get(pn - 1, ()) and \
                        (pn - 1, n) not in note_at and (restart or n not in page_marks[pn]):
                    owner = pn - 1
                else:
                    spill = False
                rest = Row(pn, rest_spans, size=r.size)
                _join(rest)
                nt = {'page': owner, 'n': n, 'text': rest.text.replace('\x00', ''),
                      'y': r.y0 + (10000 if owner != pn else 0)}
                note_at.setdefault((owner, n), nt)
                notes.append(nt)
                page_notes += owner == pn
            elif notes:
                notes[-1]['text'] = (notes[-1]['text'] + ' ' + r.text.replace('\x00', '')).strip()
            else:
                body_rows.append(r)
    # a law that numbers its footnotes straight through (1, 2, ... 18 over the whole law, not afresh on each page):
    # each number is then one note, and a marker repeated on a later page (a table that prints "13" on every row)
    # means that note
    nums = [nt['n'] for nt in notes]
    first_on_page = {}
    for nt in notes:
        first_on_page.setdefault(nt['page'], nt['n'])
    through = bool(nums) and all(a < b for a, b in zip(nums, nums[1:])) and \
        any(n > 1 for p, n in first_on_page.items() if p != notes[0]['page'])
    by_number = {nt['n']: nt for nt in notes} if through else {}
    # every note in document order: by page, then by its place on the page
    notes = sorted(notes + lr_notes, key=lambda nt: (nt['page'], nt['y']))
    for i, nt in enumerate(notes, 1):
        nt['g'] = i
        nt['text'] = re.sub(r'\s+', ' ', nt['text']).strip()

    unresolved: list[str] = []

    def resolve(row: Row) -> str:
        """Markers become [^g]; a small number with no footnote of that number on its page stays as printed."""
        def sub(m):
            nums = [int(x) for x in re.findall(r'\d+', m.group(1))] or [1]   # 'l' is the marker 1
            def find(n: int) -> dict | None:
                # a footnote of that number on the row's page; else the note of that number in the LEGAL REFERENCE
                # block the row's markers refer to, when that block has exactly one
                nt = note_at.get((row.page, n))
                if nt is None and row.block >= 0 and len(lr_at.get((row.block, str(n)), [])) == 1:
                    nt = lr_at[(row.block, str(n))][0]
                if nt is None:
                    nt = by_number.get(n)
                return nt
            found = [find(n) for n in nums]
            if any(nt is None for nt in found):
                unresolved.append(f'p{row.page + 1} #{m.group(1).strip()}: {row.plain[:70]}')
                kept = m.group(1).strip()
                # a raised "l" run into the word after it would change that word ("lACT"): keep it apart
                return kept + ' ' if kept == 'l' and re.match(r'[^\W\d_]', row.text[m.end():m.end() + 1]) else kept
            return ''.join(f'[^{nt["g"]}]' for nt in found)
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
            if LR_HEAD.fullmatch(p.text.strip()) and cur is not None:
                cur['lines'] += buf + [p.text]   # the heading of the notes of the sections above: it ends this unit
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

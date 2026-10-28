# Reproducing this repository

Built on 2026-10-28 from the Pakistan Code pages and PDFs retrieved on 2026-10-28, by the scripts in `tools/build/` (copied there as run).

| Script | sha256 |
| --- | --- |
| parse_pdf.py | `64d1c02cd85834eadb4648cde78acc7702c76738bb15deed3bcd61dceb53863f` |
| build.py | `6fb4a07bf63b3f2c5564917a689508d690873e97acaa180f360413b3d8ea59d8` |
| docs.py | `3cd6f0d69c2ae84f77efebc36c22f5d4edfe6bd45e265324e292eb94dee10f56` |
| check_text.py | `b5ab3605269a57232dbff3c1276e6d9df0a7ea4d9e5d50a0a0f690d21f1d1fa8` |

Tools: Python 3.12 with PyMuPDF 2.0 (MuPDF 1.28.5, to read the PDFs), git 2.46, and pdftotext 4.00 (xpdf, for the independent check only). [`data/source-sha256.tsv`](data/source-sha256.tsv) has the sha256 of every listing page, law page and PDF the build read, so a copy of those files can be checked byte for byte before rebuilding. How the files were retrieved is not part of this record.

## Steps

With the retrieved files in place (each matching its sha256 in `data/source-sha256.tsv`), from `tools/build/`:

```sh
# 1. Build. --today is the latest date allowed and is recorded as corpus.json "built"; every commit is dated by the
#    retrieval day, 2026-10-28. The target folder is deleted and rebuilt.
python -X utf8 build.py ../../../pakistan-law-build --today 2026-10-28 --workers 4
# 2. Check every law's letters and digits against its PDF, read by pdftotext.
python -X utf8 check_text.py ../../../pakistan-law-build
# 3. Global preflight.
python scripts/global-law/check_corpus.py ../pakistan-law-build
```

## Terms

See [`SOURCES.md`](SOURCES.md). The site has no terms of use; its footer carries a copyright line and the "under review / for information purposes only" disclaimer. There is no bulk download or API.

## What the build produced

- 1,037 laws listed; 943 built (1 Constitution, 649 Acts, 284 Ordinances, 9 Orders, 0 Regulations); 94 excluded (`data/excluded.csv`): 86 titled as repealed, 0 repeal notices, 4 without a PDF, 4 scans, 0 duplicate listings, 0 other.
- 28,002 unit files: 27,425 sections or Articles and 577 Schedules (plus title.md, contents.md and notes.md per law).
- 944 commits on `main`: 943 consolidated (one per law) and one documentation commit, all dated 2026-10-28 at 12:00 +0500.
- 22,477 footnotes (`data/amendments.csv`): 17,572 name an amending law, 1,423 give a w.e.f. date; 302 markers with no footnote on their page (`data/issues.csv`, with the PDF pages that have no text); 91 PDFs stamped "Updated till".

## Decisions made by hand

- Scope: every law on the 26 alphabetical listing pages (the site's tabs repeat entries; each law page is used once). Left out: laws whose listed title marks them repealed ("Repealed", "(Repealed by Act XIV of 2016)", "(Repeal by Ord. 52 of 2001, s.610)"), but not repealing laws ("Federal Court (Repeal) Act, 2014"), which are kept; one-page repeal notices; PDFs with no text layer, mostly scanned pages with little text, or invisible text (render mode 3, an OCR layer over a scanned gazette: OCR is not the publisher's text) for over 30% of their text; and a second listing of the same PDF. A page-sized picture alone does not exclude a PDF: many Word-made PDFs here carry a background image on every page.
- One commit per law, `Kind: consolidated`, authored by the publisher, dated by the retrieval day: the site gives no consolidation date. `In-force:` and `Consolidated:` give that day; `Updated-till:` keeps a PDF's stamp as printed (one reads "1204.2023"), and is not used as a date.
- Commit times are noon Pakistan time: UTC+5, or UTC+6 in the daylight-saving periods 2002-04-07 to 2002-10-06, 2008-06-01 to 2008-11-01 and 2009-04-15 to 2009-11-01, hard-coded in build.py.
- Text is read with PyMuPDF's page-edge clipping off: some PDFs (the Estacode most) print contents rows and table cells past the edge of the page, and clipped they would read "Governme".
- Rows: spans that overlap vertically are one printed row; spans printed twice on the same spot are kept once; a marker raised so far that it forms a row of its own joins the row below it. Spaces come from the glyph positions (PyMuPDF `rawdict`): a space character is kept only where the next glyph starts over 0.1 x the font size after the last one ends (some PDFs encode a zero-width space inside a word, "execu tion"), a gap of over 0.3 x the size inside a span, or 0.1 x the size between spans, is a space. Removed: "Page x of y", and, in the top 18% or bottom 20% of a page only, a bare page number and one first or last row repeated (digits aside) on at least a third of the pages (odd and even pages often alternate two), never a numbered row such as "16. Repeal" (in a law of one or two pages, only a bare number that is the page's own number); and the "Updated till" (or "Update Till") stamp.
- Footnotes: the run of small rows (at most 9.5 pt and 0.8 x the body size) at the bottom of a page that contains a numbered row; or, where a PDF prints body text below its notes, the small rows from the first numbered one down. A note starts with a small number, a number-only row, or (in some PDFs) the number run into the first word, taken only when it is the next number expected. Unnumbered small rows continue the note above, also across a page. A marker is a digit-only span (or "2,3,4&5") under 0.8 x its row's size; it is matched to the note of that number on its page. The body size is the commonest text size without the footnote rows (in a short law with long notes, the notes would otherwise outweigh the text).
- "LEGAL REFERENCE" blocks (the Customs Act, as the Federal Board of Revenue publishes it): the notes are printed in a block under that heading after a group of sections, numbered afresh in each block, smaller than the text, and running on over pages until the text resumes. A note starts at a row "N." (or "8a.", or "N" with no dot when it is the next number) no further right than the block's first note. A marker with no footnote of its number on its page is matched to the note of that number in the next block, when that block has exactly one. The heading stays at the end of the unit it follows.
- Paragraphs: a new one starts when the gap to the row above is over 1.35 x the law's usual line gap, at a page top unless the text runs on in lower case, at a labelled row "(a)", "(2)" after a row ending in . ; : or a dash, and at headings.
- Units: a section starts at a row "N." or "NA." with a bold heading among its first spans (after any marker and "["); headings centred between the margins in capitals or bold (PART I, CHAPTER II) go on top of the next section. A centred SCHEDULE, ANNEX, ANNEXURE or APPENDIX heading starts a schedule file, and everything after the first one stays in schedules. Text before the first section is title.md; a CONTENTS heading starts contents.md, which runs until the title is printed again (large, bold) or else to the first bold section.
- Article files for the Constitution, and for Orders that say "Article" more often than "section".
- Text is kept as printed apart from collapsed spaces and joined rows (a row ending in a letter and a hyphen joins the next lower-case row without a space).
- The documentation commit is dated by the retrieval day, not the run day, so a rebuild on another day gives the same hashes.

## Checks

```sh
git rev-list --merges --count main      # 0
python -X utf8 check_text.py ../pakistan-law-build
python tools/in_force_on.py 2026-10-28 ordinances/1962/copyright-ordinance section-57
```

Two builds from the same retrieved files give the same `git rev-parse HEAD` (the second with `--fresh`, parsing every PDF again).

Results of `check_text.py` on this build (2026-10-29): 943 laws, 5,818,769 letter tokens and 312,562 digit tokens in the repo.
- 869 laws: the same letter tokens as the PDF.
- 71 laws: the same letters, broken into words differently (a gap one reader takes as a space and the other not, mostly in tables and letter-spaced headings).
- 1 law (the Canal and Drainage Act): a raised "l", the marker 1, run into the word before it ("rulesl"), where the repo has the word and a footnote reference.
- 2 laws (the Control of Narcotic Substances Act and the Estacode): only the number of L's differs, and it is the same on both sides before lone L's are dropped; text printed over other text, which pdftotext interleaves glyph by glyph, makes an L stand alone on one side only.
- No law differs.
- Digits: no law has a digit that pdftotext does not read. In 102 laws the PDF's extra digit tokens are not exactly the number of footnote markers plus footnote numbers, because a marker printed against another number ("1[1956") reads as one number in pdftotext.

## What AI did and did not do

The scripts, documentation and checks were written by Claude Code running Claude Opus 5.5 (`claude-opus-5-5`), following Lexifina's shared rules for these repositories. No AI model wrote or changed any legal text, and no model runs during parsing, building or checking: the text is the publisher's, read from its PDFs and split by fixed rules.

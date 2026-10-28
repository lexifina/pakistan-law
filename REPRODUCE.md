# Reproducing this repository

Built on 2026-10-28 from the Pakistan Code pages and PDFs retrieved on 2026-10-28, by the scripts in `tools/build/` (copied there as run). The scripts live in the Lexifina repository at `scripts/pakistan-law/`.

| Script | sha256 |
| --- | --- |
| fetch.py | `a12a526df58487ec08714e1dad0fbffe63e251120bb1748245beea1ecef62977` |
| parse_pdf.py | `b9f98f009bf46eda95aeb6292a71d87a5b6921a2172788a6a257dddee4b2d989` |
| build.py | `b7dfb4a885b4e451b82908a6d47539657af1887db9d1d334c33c9a3e854c1ae1` |
| docs.py | `739426dc94aefaea783b54624594c35497f6107f1347421cd055e9470acb87ba` |
| check_text.py | `ff89b34d6999d5eb48f0033753267ebf141a1a3c2ac7ddf1f28e823866492b99` |

Tools: Python 3.12 with PyMuPDF 2.0 (MuPDF 1.28.5, to read the PDFs), curl 8.9 (Windows), git 2.46, and pdftotext 4.00 (xpdf, for the independent check only). [`data/source-sha256.tsv`](data/source-sha256.tsv) has the sha256 of every cached listing page, law page and PDF the build read.

## Steps

```sh
# 1. The 26 listing pages, each law's page and its PDF (about 2,100 requests, 3 at a time). Resumable; every
#    answer is cached, errors too.
python fetch.py --workers 3
# 2. Build. --today is the latest date allowed and is recorded as corpus.json "built"; every commit is dated by the
#    retrieval day in .cache/fetched_on.txt. The target folder is deleted and rebuilt.
python -X utf8 build.py ../../../pakistan-law-build --today 2026-10-28
# 3. Check every law's letters and digits against its PDF, read by pdftotext.
python -X utf8 check_text.py ../../../pakistan-law-build
# 4. Global preflight.
python scripts/global-law/check_corpus.py ../pakistan-law-build
```

## robots.txt, terms and fetch rate

See [`SOURCES.md`](SOURCES.md). robots.txt has one group, for googlebot (`Disallow: /pdffiles/`), and no rule for any other agent, AI crawlers included, and no Crawl-delay. The site has no terms of use; its footer carries a copyright line and the "under review / for information purposes only" disclaimer. There is no bulk download or API, hence one request per page and per PDF.

**Fetch rate**: `fetch.py` used curl with `--compressed` and a browser User-Agent, at most 3 requests at a time, each worker waiting for its answer before the next request, so at most 3 open requests to the one host. A failed request was retried up to 4 times, waiting 5, 10, 15 and 20 s. 2,100 requests in all, on 2026-10-28.

## What the build produced

- 1,037 laws listed; 943 built (1 Constitution, 649 Acts, 284 Ordinances, 9 Orders, 0 Regulations); 94 excluded (`data/excluded.csv`): 86 titled as repealed, 0 repeal notices, 4 without a PDF, 4 scans, 0 duplicate listings, 0 other.
- 28,011 unit files: 27,437 sections or Articles and 574 Schedules (plus title.md, contents.md and notes.md per law).
- 944 commits on `main`: 943 consolidated (one per law) and one documentation commit, all dated 2026-10-28 at 12:00 +0500.
- 21,447 footnotes (`data/amendments.csv`): 16,708 name an amending law, 1,407 give a w.e.f. date; 1,721 markers with no footnote on their page (`data/issues.csv`, with the PDF pages that have no text); 91 PDFs stamped "Updated till".

## Decisions made by hand

- Scope: every law on the 26 alphabetical listing pages (the site's tabs repeat entries; each law page is used once). Left out: laws whose listed title marks them repealed ("Repealed", "(Repealed by Act XIV of 2016)", "(Repeal by Ord. 52 of 2001, s.610)"), but not repealing laws ("Federal Court (Repeal) Act, 2014"), which are kept; one-page repeal notices; PDFs with no text layer, mostly scanned pages with little text, or invisible text (render mode 3, an OCR layer over a scanned gazette: OCR is not the publisher's text) for over 30% of their text; and a second listing of the same PDF. A page-sized picture alone does not exclude a PDF: many Word-made PDFs here carry a background image on every page.
- One commit per law, `Kind: consolidated`, authored by the publisher, dated by the retrieval day: the site gives no consolidation date. `In-force:` and `Consolidated:` give that day; `Updated-till:` keeps a PDF's stamp as printed (one reads "1204.2023"), and is not used as a date.
- Commit times are noon Pakistan time: UTC+5, or UTC+6 in the daylight-saving periods 2002-04-07 to 2002-10-06, 2008-06-01 to 2008-11-01 and 2009-04-15 to 2009-11-01, hard-coded in build.py.
- Rows: spans that overlap vertically are one printed row; spans printed twice on the same spot are kept once. Spaces come from the glyph positions (PyMuPDF `rawdict`): a space character is kept only where the next glyph starts over 0.1 x the font size after the last one ends (some PDFs encode a zero-width space inside a word, "execu tion"), a gap of over 0.3 x the size inside a span, or 0.1 x the size between spans, is a space. Removed: "Page x of y", and, in the top 15% or bottom 20% of a page only, a bare page number or a first or last row repeated (digits aside) on at least half the pages; and the "Updated till" stamp.
- Footnotes: the run of small rows (at most 9.5 pt and 0.8 x the body size) at the bottom of a page that contains a numbered row; or, where a PDF prints body text below its notes, the small rows from the first numbered one down. A note starts with a small number, a number-only row, or (in some PDFs) the number run into the first word, taken only when it is the next number expected. Unnumbered small rows continue the note above, also across a page. A marker is a digit-only span (or "2,3,4&5") under 0.8 x its row's size; it is matched to the note of that number on its page.
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

Two builds from the same cache give the same `git rev-parse HEAD` (the second with `--fresh`, parsing every PDF again).

Results of `check_text.py` on this build (2026-10-29): 943 laws, 5,823,784 letter tokens and 317,710 digit tokens in the repo.
- 843 laws: the same letter tokens as the PDF.
- 64 laws: the same letters, broken into words differently (a gap one reader takes as a space and the other not, mostly in tables).
- 36 laws differ, by 955 letters in all (about 0.004% of the letters). The largest: the Estacode (442 letters, in a 1,044-page PDF), the Customs Act and Federal Excise Act (their running titles, "The Customs Act", which the build removes as page furniture and pdftotext keeps), the Control of Narcotic Substances Act and Short Titles Act (rotated or stacked table text), two "Updated till" stamps printed twice on top of each other (pdftotext interleaves the copies), and a few "l"s printed for the footnote number 1 that one side reads as a letter.
- Digits: in 5 laws (among the 36) the repo has one or two digits more than pdftotext reads, not yet explained; `check_text.py` lists them. In 102 laws the PDF's extra digit tokens are not exactly the number of footnote markers plus footnote numbers, because a marker printed against another number ("1[1956") reads as one number in pdftotext.

## What AI did and did not do

The scripts, documentation and checks were written by Claude Code running Claude Opus 5.5 (`claude-opus-5-5`), following Lexifina's shared rules for these repositories. No AI model wrote or changed any legal text, and no model runs during fetching, parsing, building or checking: the text is the publisher's, read from its PDFs and split by fixed rules.

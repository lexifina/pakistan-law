# The laws of Pakistan, as a git repository

The federal laws of Pakistan as the [Pakistan Code](https://pakistancode.gov.pk) publishes them: 943 laws (the Constitution of 1973, 649 Acts, 284 Ordinances and 9 Orders), each split into one file per section or Article and one per Schedule (28,011 files), with one paragraph per line, so `git blame` and `git diff` work line by line. The Pakistan Code is run by the Ministry of Law and Justice.

> **The site's disclaimer applies here too.** The Pakistan Code says: "The content available on this Website is for information purposes only, and is currently under review. If there is any doubt or query, the users may refer to the original source i.e. the relevant Gazette notification(s)." Its earlier wording was: "All laws on the website are currently under review. They are for general informational purposes only, and should not be taken as authentic or error-free legislative instruments." The texts here are copies of those PDFs, so they are not authentic either. For anything that matters, read the Gazette of Pakistan.

**What this repository is not, yet: a history.** The Pakistan Code publishes only the current consolidated PDF of each law and keeps no earlier versions. So each law is a single commit holding its whole text as retrieved on 2026-10-28, and there is no line-by-line history before that day (corpus.json `"history": "current-only"`). Later retrievals will be added as later commits, so the history grows forward from here. The amendment history that the PDFs print as footnotes is kept: in the files, and parsed into [`data/amendments.csv`](data/amendments.csv).

The record holds 943 laws in 944 commits. 94 of the 1,037 laws the site lists are left out, each with its reason, in [`data/excluded.csv`](data/excluded.csv).

## A lawyer's questions as git commands

| Question | Command |
| --- | --- |
| What does Article 25A of the Constitution say? | `python tools/in_force_on.py 2026-10-28 constitution/1973/constitution-of-the-islamic-republic-of-pakistan article-25A` |
| What does section 57 of the Copyright Ordinance say? | `python tools/in_force_on.py 2026-10-28 ordinances/1962/copyright-ordinance section-57` |
| The whole of a law, in order | `python tools/in_force_on.py 2026-10-28 ordinances/1962/copyright-ordinance` |
| Which laws amended a section, and when (by its footnotes) | `grep '^\[\^' ordinances/1962/copyright-ordinance/section-57.md` |
| Everything an amending law touched, by the footnotes | `grep -i 'XX of 1992' data/amendments.csv` |
| What changed in a law since this build (after later builds) | `git log -p -- ordinances/1962/copyright-ordinance` |
| The list of laws, with their numbers and dates | [`laws.csv`](laws.csv) |

## The files

Each law is a folder `<kind>/<year>/<name>/`, where kind is `constitution`, `acts`, `ordinances`, `orders` or `regulations` and year is the law's year. In it:

- `title.md`: the title, the law's number, its date, long title and preamble, as printed (and anything the PDF prints before its contents list);
- `contents.md`: the list of sections the PDF prints;
- `section-12A.md` (or `article-25A.md` in the Constitution and in Orders that number Articles): one file per section, starting with any Part or Chapter headings above it as `##` lines, then one paragraph per line. A number printed twice (an omitted and a new section 5, say) gives `section-5~2.md`;
- `schedule-1.md`, `schedule-2.md` ...: the Schedules, Annexes and Appendices, in order, each with its own heading;
- `notes.md`: every footnote of the law in order; and at the end of each file, the footnotes it cites;
- `index.txt`: the files in the order of the law.

Footnote markers are written `[^12]`, numbered through the whole law (the PDFs number them afresh on every page), and each file ends with its notes: `[^12]: Subs. by Act No. XX of 1992, s. 15.` Text is copied as printed, with spaces collapsed and printed lines joined into paragraphs; nothing is reworded. The PDFs print a dash as two small underscores (`:__`), and that is kept. A marker with no footnote of that number on its page (an error in the PDF, or a superscript such as the 3 of m3) is kept as the digits printed, and listed in [`data/issues.csv`](data/issues.csv) (1,721 of them). Some texts taken from the Federal Board of Revenue (the Customs Act and others marked "Same as on the official website of FBR") print their notes as endnotes, so their markers stay as printed digits.

## The dates, and which one we use

The Pakistan Code gives no date for its consolidations. **Every commit is dated by the day the PDFs were retrieved, 2026-10-28**, at noon Pakistan time (UTC+5), and that date is in the `In-force:` and `Consolidated:` trailers (`Date-source: retrieved`). It says only that this was the published text on that day; it is not the date any amendment took effect. The listing's promulgation date is the `Promulgated:` trailer. 91 PDFs carry a stamp "Updated till dd.mm.yyyy" at the top of the first page; it is kept, as printed, in an `Updated-till:` trailer and in laws.csv. Commencement and "w.e.f." dates printed in footnotes are in [`data/amendments.csv`](data/amendments.csv) (1,407 footnotes give one), which does not convert one kind of date into another.

`tools/in_force_on.py` answers for 2026-10-28 and any later date. For an earlier date it says there is no version, because the source has none.

## What "author" means

Every law-text commit has the same author: `Pakistan Code (Ministry of Law and Justice) <pakistan-code@pakistancode-gov-pk.invalid>`, with the trailer `Kind: consolidated`. The address cannot exist. The author is the publisher of the consolidation, not a lawmaker. No line is credited to an amending law, because without the earlier text nobody can tell which words an amendment wrote. The footnotes say which law substituted, inserted or omitted words; they are kept as text and in data/amendments.csv (21,447 footnotes, 16,708 of which name an amending law), and are not used to credit lines. In the shared design for these repositories, a change is credited to an amending law only when the source shows the text before and after it.

## What it does not show

- Any text before 2026-10-28. The Pakistan Code has none.
- Laws the site lists as repealed (86 whose listed title marks them repealed, "Repealed" or "Repeal by ..."; every PDF that is only a one-page "THIS LAW HAS BEEN REPEALED" notice belongs to one of these; repealing laws such as the Federal Court (Repeal) Act, 2014 are laws in force and are kept), laws with no PDF (4), PDFs that are scans: no text layer, mostly scanned pages, or a scanned gazette whose only text is an invisible OCR layer (4), and second listings of the same PDF (0). All are in [`data/excluded.csv`](data/excluded.csv).
- Provincial laws, rules and statutory orders (SROs): the Pakistan Code's federal list holds Acts, Ordinances, Orders and Regulations.
- Pictures and the layout of tables: a table's cells are read row by row into lines.
- Text the PDF prints in a footer or header (page numbers and running titles).
- PDF pages with no text at all (a scanned page, a picture or a blank page): 26 laws have some; the pages are listed in [`data/issues.csv`](data/issues.csv). PDFs that are mostly such pages are left out.

This is a research aid. It is not legal advice, and it is not the authentic text of any law.

## How it is checked

`tools/build/` holds the build as it was run, and [`data/source-sha256.tsv`](data/source-sha256.tsv) the sha256 of every cached page and PDF it read. The build is deterministic: from the same cache it gives the same commit hashes. See [`REPRODUCE.md`](REPRODUCE.md). Before publishing, the build was checked for these things:
- the letters and digits of every law equal those of its PDF, read by a different program (`check_text.py`, using pdftotext);
- the text `tools/in_force_on.py` prints for sample sections matches the PDF;
- every commit's trailers parse; there are no merges, no dates that go backwards and none after the build date;
- two builds from the same cache give the same HEAD.

## Licence

Source: the Pakistan Code (https://pakistancode.gov.pk), Ministry of Law and Justice, Government of Pakistan. The site's footer reads "© Copyright 2022 - Ministry of Law and Justice" and states no licence. The legal basis for reusing the texts, and its limits, are in [`SOURCES.md`](SOURCES.md): the Copyright Ordinance, 1962, section 57(1)(q)(i). **This repository is private. Read SOURCES.md before making it public.** Lexifina's own contributions (the tools, the arrangement and the commit messages) are CC0. See [`LICENSE`](LICENSE).

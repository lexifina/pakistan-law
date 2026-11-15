# Pakistan: law history in git


The federal law of Pakistan as a git history: one file per section or Article, one commit per version, and the Pakistan Code, the Ministry of Law and Justice's consolidation, as the author of each. The Pakistan Code keeps no earlier versions, so for now each law has one version, the text retrieved on 2026-10-28; later retrievals will be added as new commits, and `git log`, `git blame` and a date will then show what changed and when. The amendments the text already holds are named in its footnotes.

Part of [lexifina/global-law](https://github.com/lexifina/global-law), one git history for every country's law: this is Pakistan's national law, which global-law reads at `pakistan/national/acts/`.

**What is in it now:** the Constitution of 1973 and 942 other federal laws (649 Acts, 284 Ordinances and 9 Orders) as the Pakistan Code consolidates them, one version each, in 28,002 section, Article and Schedule files, with their 22,477 amendment footnotes (17,572 naming the amending law) parsed into [`data/amendments.csv`](data/amendments.csv). [`laws.csv`](laws.csv) lists every law with its number, promulgation date and folder.

Each law is in `<kind>/<year>/<name>/`, with one file per section (or Article) and Schedule, plus `title.md`, `contents.md`, `notes.md` and `index.txt` (`acts/1934/factories-act/section-49B.md` is section 49B, Annual holidays, of the Factories Act, 1934, XXV of 1934); the Constitution is in [`constitution/1973/constitution-of-the-islamic-republic-of-pakistan/`](constitution/1973/constitution-of-the-islamic-republic-of-pakistan/).

The text is in English, as the Pakistan Code's PDFs print it, with footnote markers numbered through each law (`[^44]`) and each file ending with the notes it cites. An Urdu text is not part of this record.

## Questions as git commands

| Question | Command |
| --- | --- |
| Every change to section 49B of the Factories Act | `git log -p --word-diff -- acts/1934/factories-act/section-49B.md` |
| Who is credited with each line of section 49B? | `git blame acts/1934/factories-act/section-49B.md` |
| Every version of the Factories Act, with the day each is dated | `git log --format="%h %(trailers:key=In-force,valueonly,separator=) %an" -- acts/1934/factories-act` |
| Section 49B as this record has it on 1 November 2026 | `python tools/in_force_on.py 2026-11-01 acts/1934/factories-act section-49B` |

The laws that amended a section are named in its footnotes: `grep '^\[\^' acts/1934/factories-act/section-49B.md`.

**Outside git**, we also host this record publicly, for free:

- **[Ask Claude about Pakistani law](https://global-law.lexifina.com/v1/try_claude?country=pakistan)**: opens Claude with a first question ready.
- **[Ask ChatGPT](https://global-law.lexifina.com/v1/try_chatgpt?country=pakistan)**: the same question in ChatGPT.
- **[Search Pakistani law on our site](https://lexifina.com/law?country=pakistan&q=annual+leave)**: a search for "annual leave", with each provision's text and its versions, no account needed.
- **[Developer REST API](https://global-law.lexifina.com/v1/search_law?query=annual+leave&jurisdiction=pakistan)**: the same search as JSON, with no key. See the [documentation here](https://lexifina.com/api/global-law).

Both assistants read the record through the free Global law connector (MCP, `https://global-law.lexifina.com/mcp`); the first time, the chat gives you the link that adds it. Ask in English.

**Host it yourself easily.** All it takes is git and Python, and the tools run on your machine:

```sh
git clone --depth 1 https://github.com/lexifina/global-law && cd global-law
python3 tools/countries.py add pakistan/national/acts
python3 tools/law.py show 2026-11-01 pakistan/national/acts/acts/1934/factories-act/section-49B.md
```

Opened in Claude Code, Cursor, VS Code or Codex, the clone also starts a local MCP server with the same tools ([MCP.md](https://github.com/lexifina/global-law/blob/main/MCP.md)).

## Dates

The Pakistan Code gives no date for its consolidations, so each law's commit is dated at noon, Pakistan time (UTC+5), on the day its PDF was retrieved, 2026-10-28, and carries that day in its `In-force:` and `Consolidated:` trailers (`Date-source: retrieved`):

- that day says only that this was the published text then, not when any amendment took effect, and `tools/in_force_on.py` has no text for an earlier date;
- the promulgation date is in `Promulgated:`, and the "Updated till" stamp that 91 PDFs print is kept as printed in `Updated-till:`;
- the commencement and "w.e.f." dates printed in 1,423 footnotes are in `data/amendments.csv`, not used as commit dates.

Every law's commit is credited to its publisher, `Pakistan Code (Ministry of Law and Justice)`, with `Kind: consolidated`: without the earlier text nobody can tell which words an amendment wrote, so no line is credited to an amending law.

## How it is checked

- `tools/build/check_text.py` compares the letters and digits of every law with its PDF read by a different program (pdftotext): 869 laws have the same letters, 71 the same letters split into words differently, and the other 3 differ only where a footnote marker touches a word or text is printed over text (see [`REPRODUCE.md`](REPRODUCE.md)).
- The text `tools/in_force_on.py` prints for sample sections was compared with the PDF.
- Every commit's trailers parse; there are no merges, no dates that go backwards and none after the build day.
- Two builds from the same retrieved files gave the same HEAD; [`data/source-sha256.tsv`](data/source-sha256.tsv) has the sha256 of every page and PDF the build read.

## What it does not show

- **Any text before 2026-10-28.** The Pakistan Code publishes only the current consolidated PDF of each law.
- **The authentic text.** The Pakistan Code says its content "is for information purposes only, and is currently under review"; the Gazette of Pakistan is authoritative.
- **94 of the 1,037 laws the site lists**: 86 titled as repealed, 4 with no PDF and 4 scanned PDFs, each with its reason in [`data/excluded.csv`](data/excluded.csv).
- **Provincial laws, rules and SROs.** The federal list holds none; Balochistan's and Khyber Pakhtunkhwa's laws are in [pakistan-balochistan-law](https://github.com/lexifina/pakistan-balochistan-law) and [pakistan-khyber-pakhtunkhwa-law](https://github.com/lexifina/pakistan-khyber-pakhtunkhwa-law).
- **Pictures and table layout**: a table's cells are read row by row; pages with no text in 26 laws are listed in [`data/issues.csv`](data/issues.csv).

## Sources

| Source | Kind | Past versions | Notes |
| --- | --- | --- | --- |
| [Pakistan Code](https://pakistancode.gov.pk) (Ministry of Law and Justice) | Consolidated federal laws, one PDF per law | no, the current text only | The text, the footnotes naming each amending law, and the list of laws with their numbers and promulgation dates; not the authentic text |

## Licence

See [`LICENSE`](LICENSE). Reproducing and publishing matter published in the Gazette of Pakistan is not an infringement of copyright under the Copyright Ordinance, 1962, section 57(1)(q)(i); the Ministry's consolidation and footnotes are not expressly covered by that clause ([`SOURCES.md`](SOURCES.md) sets out the basis and its limits). The tools, arrangement, commit messages and documentation are CC0 1.0.

No AI model wrote or changed any legal text, and none runs while the laws are parsed, built or checked; the scripts, documentation and checks were written by an AI model (see [`REPRODUCE.md`](REPRODUCE.md)).

## More

From [lexifina/global-law](https://github.com/lexifina/global-law):

- [FEATURES.md](https://github.com/lexifina/global-law/blob/main/FEATURES.md): every feature, and what every corpus must support (`git blame`, `law.py`, the MCP tools)
- [FAQ.md](https://github.com/lexifina/global-law/blob/main/FAQ.md): questions and answers · [CONTRIBUTING.md](https://github.com/lexifina/global-law/blob/main/CONTRIBUTING.md): proposing changes · [MCP.md](https://github.com/lexifina/global-law/blob/main/MCP.md): the MCP server · [REPRODUCE.md](https://github.com/lexifina/global-law/blob/main/REPRODUCE.md): how it was built · [CHANGELOG.md](https://github.com/lexifina/global-law/blob/main/CHANGELOG.md)
- [FRESHNESS.md](https://github.com/lexifina/global-law/blob/main/FRESHNESS.md): how current each corpus is · [Monitoring](https://github.com/lexifina/global-law/tree/main/monitoring): whether updates are running · [WATCHING.md](https://github.com/lexifina/global-law/blob/main/WATCHING.md): how each official source is watched for changes
- [performance/](https://github.com/lexifina/global-law/tree/main/performance): how fast the tools are, measured
- [visualisations/](https://github.com/lexifina/global-law/tree/main/visualisations): charts and bridges across the world's law
- [Vulnerabilities](https://github.com/lexifina/global-law/tree/main/vulnerabilities): mistakes in legislation as published

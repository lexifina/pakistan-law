# Sources

| Source | What it gives | Used |
| --- | --- | --- |
| [Pakistan Code](https://pakistancode.gov.pk) (Ministry of Law and Justice) | Every federal law in force, listed by initial letter, each with one consolidated PDF that prints its amendments as footnotes | Yes: the text of every law |
| The site's alphabetical lists of laws | One letter's laws: title, category, number, promulgation date and the link to the law's page | Yes: the list of laws (26 pages) |
| Each law's page | The link to the law's PDF | Yes |
| Each law's PDF | The consolidated text, as a Word-made PDF | Yes |
| [Document Retrieval System](https://drs.molaw.gov.pk) (Ministry of Law and Justice) | Lists "document versions" | No |
| Gazette of Pakistan | The authentic text | No: it is not published as a consolidated, searchable whole |
| [legalize-pk](https://github.com/UmerTariq1/legalize-pk) | A volunteer history of the Constitution | No: an unofficial transcription is not used as the text |

Retrieved {{RETRIEVED}}: {{LISTED}} laws listed on 26 pages; for 5 of them no PDF could be retrieved (listed in data/excluded.csv).

## Terms and history

- **Terms**: the site has no terms of use. Its footer reads "© Copyright 2022 - Ministry of Law and Justice" and carries the disclaimer: "The content available on this Website is for information purposes only, and is currently under review. If there is any doubt or query, the users may refer to the original source i.e. the relevant Gazette notification(s)." (The page source keeps, commented out, an older wording: "All laws on the website are currently under review. They are for general informational purposes only, and should not be taken as authentic or error-free legislative instruments. If you have any questions about the accuracy or completeness of a law, please refer to the original source i.e. the relevant Gazette notification(s).") Nothing forbids automated reading or reuse.
- **History**: none. Each law has one PDF, the current consolidation, with no date of its own; some carry an "Updated till" stamp. Hence `history: "current-only"`.

## Legal basis for reuse

Pakistan has no general exclusion of official texts from copyright. The Copyright Ordinance, 1962 (Ordinance No. XXXIV of 1962) instead makes some uses of them lawful. The text below was read in the Pakistan Code's own PDF of the Ordinance (`ordinances/1962/copyright-ordinance/section-57.md` in this repository).

Section 57(1) begins "The following acts shall not constitute an infringement of copyright, namely:" and clause (q) reads:

> (q) the reproduction or publication of__
> (i) any matter which has been published in any official Gazette, or the report of any committee, commission, council, board or other like body appointed by the Government unless the reproduction or publication of such matter or report is prohibited by the Government;
> (ii) any judgment or order of a court, tribunal or other judicial authority, unless the reproduction or publication of such judgment or order is prohibited by the court, tribunal or other judicial authority, as the case may be;

Federal Acts, Ordinances, President's Orders and Regulations, and the laws amending them, are published in the Gazette of Pakistan (the site itself sends readers to "the relevant Gazette notification(s)"), and no prohibition by the Government of reproducing them was found. So reproducing and publishing the words of the laws, as gazetted, is not an infringement under s.57(1)(q)(i). This was not checked law by law against the Gazette.

The limits of that basis:
- **The consolidation itself.** The Pakistan Code's PDFs are the Ministry's work: it merged the amendments into the text and wrote the footnotes. Section 2 defines a "Government work" as one "made or published by or under the direction or control of__ (i) the Government or any department of the Government", and section 22(1) gives copyright in a Government work, where Government is the first owner, until fifty years after first publication. Section 57(1)(q)(i) covers matter published in the Gazette; it does not in terms cover the Ministry's arrangement and footnotes, which were not. The footnotes record facts (which law changed which words), but their wording is the Ministry's.
- **"Unless ... prohibited by the Government."** None was found; the site's footer notice ("© Copyright 2022 - Ministry of Law and Justice") states ownership but no prohibition and no licence.

**So this repository is private.** Before it is made public, the position of the consolidation and footnotes should be checked, or the Ministry of Law and Justice asked (the site lists dydirectorit@molaw.gov.pk and +92-51-9211976 for queries).

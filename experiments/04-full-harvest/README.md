# Experiment 04: full harvest

Can the metadata and body texts of all theses of the university be harvested from DSpace
in one unattended run, and how many theses have a usable text?

Done, 2026-10-12. Corpus: all thesis collections of DSpace UK as of 2026-10-11. Builds on:
experiments 01 and 02.

| Step | How |
| --- | --- |
| catalog | OAI-PMH `ListRecords` in the `xoai` format for the 17 faculty collections "Kvalifikační práce" and the 17 collections "Kvalifikační práce obhajované před rokem 2006", pages stored raw |
| parse | one line per thesis in `catalog.jsonl.gz`: all metadata, the files of the ORIGINAL and TEXT bundles, the chosen body |
| body | the PDF described as "Text práce" and its TEXT file, or the largest TEXT file (the rule of experiment 01) when no PDF has that description |
| texts | the TEXT file of the body, checked against size and MD5 from the catalog, 3 requests per second |

`xoai` carries what the REST harvester of experiment 02 fetched item by item: metadata
together with every file, its description, size, MD5 and access. A page of 100 records
takes under a second even deep into a set, and the resumption token holds the position
itself, so a restart continues from the token in the last stored page. The catalog of
167,082 theses took 56 minutes for 1,686 pages and 8 minutes to parse. Every set gave
exactly the number of records the server announced. Two theses were listed twice, once
under a stale record with a space after the handle, and the parser merges them.

Every thesis has a PDF described as "Text práce". The largest-TEXT rule of experiment 01
picks a different file for 4,825 of them (2.9 %). In 3,153 of these the TEXT file of the
body is under 1 KB, probably a scan without a text layer, and the old rule took an abstract
or another document instead. In the 592 theses of `eval/v0` the texts are byte for byte
those of experiment 02 except 15, all of them theses where the two rules choose different
files.

| Body text | Theses |
| --- | --- |
| downloaded, 1 KB or more | 157,252 |
| downloaded, under 1 KB (probably scans, 5,376 of them from 2000 to 2009) | 5,790 |
| not openly accessible, not requested | 3,969 |
| no TEXT file | 43 |
| gone from DSpace (HTTP 404) | 28 |

The texts took 16 hours at 2.8 per second and fill 9.6 GB gzipped (27.9 GB raw). The
server answered once with HTTP 504 and the laptop slept once for about five minutes. Both
times the harvest went on by itself within seconds. One text came back empty and arrived
on the retry with `--retry-failed`. The 28 texts with HTTP 404 belong to theses that no
longer have a page in DSpace (6 of 6 checked), although the OAI index still lists them.
Not openly accessible are all 3,233 theses of the collections before 2006, open to
university users only in the records checked, and 736 newer ones. The server answers a
request for such a file with a redirect to an HTML page, not with an error code.

Reproduce: `python -u experiments/04-full-harvest/harvest.py`. A stopped run continues
with the same command, and `harvest.py status` shows what is on disk. Data stays in
`data/04-full-harvest/`, outside the repository: the texts are works of the students and
the metadata names people.

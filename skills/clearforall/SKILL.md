---
name: clearforall
description: Turn complex public-service documents (benefit notices, eligibility rules, government letters, insurance or tax notices, application instructions, policy announcements, 政府通知、补贴政策、医保社保通知、办事指南) into accurate plain-language text and accessible HTML in English and/or Chinese. Every number, deadline and eligibility rule is traced to the source, and anything uncertain is flagged for human review. Use this whenever a nonprofit, caseworker, volunteer, librarian or family member wants to simplify, explain, translate or make accessible an official notice or public-service document, even if they just say "make this easier to read", "easy read version", "explain this letter for my client", "帮我改成老人看得懂的" or "做个简明版". Also use it whenever the accuracy of facts in a simplified or translated version matters.
license: Apache-2.0
compatibility: Python 3.8+ (standard library only, runs offline). Works with any agent that can read files and run Python.
metadata:
  version: "0.1.0"
  languages: "en, zh-Hans, zh-Hant"
---

# ClearForAll

Help people who serve the public turn dense official documents into versions everyone can read:
older people, people with low literacy, people reading in a second language and screen-reader
users. Get it **right** first and make it easy second. A friendly page with a wrong deadline does
more harm than the original notice, because people trust it.

Three commitments shape every step:

1. **No fact is lost or changed.** Numbers, dates, conditions, required documents, contacts and
   consequences survive exactly, and each one can be traced back to a quote in the source.
2. **Uncertainty is shown, not resolved.** Contradictions, hedges ("may", "原则上"), computed values
   and risky translations are flagged for a human. They're never quietly smoothed over.
3. **Private and local.** Work only on local files. Never upload, publish, post, email or share
   anything, and never paste document text into web searches or online tools. Leave personal
   details (names, case numbers, addresses, ID numbers) out of the outputs. Everything produced is
   a **draft** for a person to check.

## Workflow

### 1. Intake

- Get the document into plain UTF-8 text as `source.txt` in a new output folder (default
  `./clearforall-output/<short-name>/`). For PDFs, use whatever local extractor is available
  (`pdftotext -layout`, `pypdf`) and keep the page breaks as `--- page N ---` lines. For
  images or scans, transcribe carefully and note in the ledger that the source is a transcription.
  Never use an online OCR or conversion service.
- **Personal letters** (addressed to one person, with a name, case number or address): don't copy
  them into the output folder. If the original is already plain text, point the validators at it
  with `--source <original path>`. If you had to extract text, keep that file outside the output
  folder and say where it is in the hand-off, so the user can delete it. Leave identifiers out of
  `facts.json` too: quote the sentence that carries the fact, not the address block.
- Work out, and ask only if you really can't tell: audience (seniors? low literacy? new arrivals?),
  output language(s) and Chinese script (简体 `zh-Hans` is the default, 繁体 `zh-Hant` for HK/TW/many
  overseas communities), and whether it's a general notice or a letter to one person.
- Note the document's title, issuer and date or version. If it looks out of date (a past program
  year, "until further notice"), that's a review item.

### 2. Find every critical fact

Run the safety net first so that nothing slips through:

```bash
python <skill-dir>/scripts/extract_facts.py source.txt
```

It lists every line with dates, money, percentages, phone numbers, deadline words, eligibility
words, document words and hedge words, plus ambiguous numeric dates and personal data. Then
**read the whole source yourself**. The script finds candidates; you decide what they mean.

### 3. Build the ledger: `facts.json`

Read `references/fact-ledger.md` and follow its schema. The essentials:

- One entry per critical fact. Each income-table row, each deadline and each document gets its own
  entry. 25–50 entries for a few pages is normal.
- `source_quote` is copied character for character from `source.txt`. The validator rejects
  paraphrased quotes, because a paraphrased "source" can't be traced.
- `value` is canonical (`2027-03-31`, `2610`, `70`, digits-only phone) so the validators can find
  it in any notation or language.
- Set `needs_review` honestly: contradictions, hedges, ambiguity, computed values, translation
  risk, missing or outdated information. Group them into `review_items`, each with a concrete
  question a volunteer could answer with one phone call.

The ledger comes before any writing because it makes you understand the document fully first. It
also gives the reviewer one place to check your reading of it.

### 4. Write the plain-language version(s)

Read `references/plain-language.md`. In short:

- Put what readers act on first: what this is, the deadline, the money, the one thing to do.
- Write short sentences with everyday words, and talk to the reader as "you" / "您".
- Keep the logic of conditions ("all of these" vs "any one of these", "only if", "except").
  This is where most simplification errors happen.
- Write dates with year and weekday, keep money in the source currency, and never round.
- Where the ledger flags something, say so in plain words ("Two different phone numbers appear in
  the notice. We are checking which is right. Try (555) 014-2290 first." / "这一点还在核实").
- For translations, work from the source and the ledger, not from your own simplified text. Keep
  official names in both languages the first time they appear.

Save one Markdown file per language, e.g. `plain-en.md` and `plain-zh.md`. End each with a short
"Where this information comes from" section that names the source document.

### 5. Build the accessible HTML

Copy `assets/template.html` and fill it in. Read `references/accessible-html.md` for the reasons
behind it. Make one page per language (`page-en.html`, `page-zh.html`) that link to each other,
unless the user wants a single page.

- Wrap each critical fact in an element with `data-fact="F#"` whose text contains the exact value,
  and list the fact in the Sources section (`id="src-F#"`, location plus verbatim quote). This is
  what makes every claim traceable from the page itself.
- Mark flagged facts with `data-review="R#"` and the `flag` class, and keep the
  `#cfa-draft-notice` box while any review item is open.
- No external fonts, scripts, images or analytics. The page has to work offline and must not leak
  who opened it.

### 6. Write `review.md`

This is a short, printable checklist for the human reviewer. Give each review item (R1, R2, …)
the question, the source quote with its location, and how the draft currently shows it. Put
general caveats at the end: transcription quality, translation choices, anything you left out on
purpose and why.

### 7. Validate and fix

```bash
python <skill-dir>/scripts/validate_all.py clearforall-output/<short-name>/
```

This runs the fact and traceability check, HTML accessibility lint, readability metrics, a privacy
scan and a review hand-off check, then writes `validation-report.txt`. Fix every FAIL and read every
WARN:

- *quote not found* means you paraphrased. Copy the exact text.
- *missing fact values* means the output dropped or changed a number or date. Restore it.
- *numbers not in the source* means you invented, rounded or computed a value. Remove it, or mark it
  `derived` + `needs_review`.
- *personal data* means you need to remove names, case numbers and addresses (unless the user
  explicitly asked to keep them: `--allow "value"`).
- Readability warnings point at sentences worth splitting. Never fix one by dropping a condition.

Re-run until there are no FAILs. The individual scripts (`check_facts.py`, `check_html.py`,
`readability.py`, `check_privacy.py`) can also be run on their own. Each has `--help`.

### 8. Hand off

Tell the user, in their language:

- where the files are (output folder, file names)
- how many facts were traced and the validation result
- **each open review item**, briefly, because these are what a person must check before sharing
- that the files are drafts that stay on their computer, and that nothing has been published or
  sent

When a person has resolved the review items, they fill in `resolution` in `facts.json`, remove the
draft notice and flag markers, and run `validate_all.py --final`. Offer to do the edits once they
give you the answers. Don't resolve review items yourself by guessing or searching the web.

## Output folder

```
clearforall-output/<short-name>/
├── source.txt              plain-text copy of the original
├── facts.json              fact ledger (traceability + review items)
├── plain-en.md / plain-zh.md
├── page-en.html / page-zh.html
├── review.md               questions for the human reviewer
└── validation-report.txt
```

## When the request is narrower

- **"Just explain this letter to me" (chat answer only):** still build the ledger, then answer
  in chat with the key facts, deadlines first, and flag uncertainties. Offer to make the files.
- **A personal letter for one client:** leave identifying details out by default; "you" is enough.
  If the user asks to keep the name for a private copy, pass `--allow`. Don't save extra copies of
  the letter anywhere.
- **Very long documents (handbooks, 50+ pages):** agree on scope first (which sections matter to
  this audience), then build ledgers per section. Record what's out of scope in `review.md`.
- **Easy Read for people with intellectual disabilities:** one idea per line, sentences under
  about 10 words, and the most important information only. Say in `review.md` what was left out,
  and keep it in the ledger so nothing critical silently disappears.

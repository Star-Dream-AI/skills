# The fact ledger (`facts.json`)

The ledger is the contract between the original document and every simplified version. If a fact
isn't in the ledger, no validator can protect it. If it's in the ledger with a bad quote, nobody can
trace it. Build the ledger before writing any plain-language text.

## Contents

1. What counts as a critical fact
2. Schema
3. Canonical values
4. Uncertainty: when to set `needs_review`
5. Review items
6. Worked example

## 1. What counts as a critical fact

A fact is critical if getting it wrong could make someone miss out, pay the wrong amount, miss a
deadline or turn up without the right papers:

| category | examples |
|---|---|
| `deadline` | application window, postmark vs. received-by date, "within 10 days of…" |
| `date` | interview appointment, benefit start date, coverage period |
| `amount` | fees, benefit amounts, income limits (each row of a table is its own fact), subsidies, fines |
| `eligibility` | residency, age, income, household, citizenship or immigration conditions |
| `exclusion` | who cannot apply, what doesn't count, "except" clauses |
| `requirement` | must-do actions such as reporting changes or attending an interview |
| `document` | each document someone has to bring or send |
| `procedure` | channels (online / mail / in person), order of steps if the order matters |
| `contact` | phone numbers, offices, opening hours, websites (public agency details only) |
| `penalty` | what happens if you miss something: benefits stop, waiting period, repayment |
| `right` | the right to appeal, to an interpreter or to a hearing, and the deadline for it |

When in doubt, include it. A ledger with 40 entries is normal for a 3-page notice.

## 2. Schema

```json
{
  "source": {
    "title": "2026–2027 Home Energy Assistance Program Public Notice",
    "issuer": "Lakeview County Community Action Agency",
    "file": "heap-notice.txt",
    "url": null,
    "version_or_date": "Issued October 1, 2026",
    "language": "en",
    "retrieved": "2026-10-25"
  },
  "facts": [
    {
      "id": "F1",
      "category": "deadline",
      "claim": "Mail-in applications must be received by March 13, 2027.",
      "value_type": "date",
      "value": "2027-03-13",
      "source_quote": "Mail-in applications must be received no later than March 13, 2027.",
      "location": "How to Apply, line 41",
      "confidence": "high",
      "needs_review": false,
      "review_reason": null
    }
  ],
  "review_items": [
    {
      "id": "R1",
      "fact_ids": ["F17"],
      "issue": "Two different phone numbers are given for the same office.",
      "question_for_reviewer": "Which number is correct: (555) 014-2290 (page 1) or (555) 014-2209 (page 3)?",
      "shown_to_reader_as": "Both numbers listed and marked as being checked",
      "resolution": ""
    }
  ]
}
```

Field notes:

- `id`: `F1`, `F2`, … Stable. The HTML refers to these ids.
- `claim`: one plain sentence saying what the fact means. This is your interpretation, so it's what
  the reviewer checks against the quote.
- `source_quote`: **copied character for character** from `source.txt`. Make it the shortest span
  that proves the claim. Line breaks and spacing can differ, but no word can change.
  `check_facts.py` fails if the quote isn't there. Never "tidy up" a quote.
- `location`: something a person can find, like a section heading, page, line number or table row.
- `value_type`: `date`, `money`, `number`, `percent`, `duration`, `phone`, `range`, `text`.
- `value`: the canonical value (see §3). For `text`, leave it empty. Those facts are checked by
  traceability only.
- `confidence`: `high`, `medium` or `low`, as your own honest estimate.
- `derived`: `true` if you computed the value (for example 70% of 400 = 280) instead of reading it.
  A derived fact must also have `needs_review: true`.
- `outputs`: optional list of output file names. Use it when a fact only belongs in some outputs,
  e.g. the English page leaves out a Chinese-only payment channel.

## 3. Canonical values

The validators normalize notation and language, so write values in one neutral form:

| value_type | canonical form | matches in outputs |
|---|---|---|
| `date` | `2027-03-31` | `March 31, 2027`, `31 March 2027`, `2027年3月31日`, `2027/3/31` |
| `money` / `number` | `1250`, `0.5` | `$1,250`, `1250 元`, `1,250.00`, `1250美元`, `0.125万` |
| `percent` | `70` | `70%`, `百分之七十`, `70 percent` |
| `duration` | the number: `90` | `90 days`, `90天`, `九十天` (write the unit in `claim`) |
| `phone` | digits only: `15550142290` | `(555) 014-2290`, `555.014.2290`, `+1 555 014 2290` |
| `range` | `250-1200` | both ends must appear |

## 4. Uncertainty: when to set `needs_review`

Set `needs_review: true` and give a `review_reason` when any of these apply. Being honest here
matters more than anything else in the ledger.

| reason | example |
|---|---|
| contradiction | two different phone numbers, two different deadlines for the same thing |
| ambiguity | "may be automatically enrolled", "原则上在学校所在地参保", unclear "or" vs "and" |
| hedged / discretionary | "subject to available funds", "视情况", "at the agency's discretion" |
| computed | any number you calculated, converted (currency, monthly↔annual) or rounded |
| missing | a deadline is mentioned but no date is given; "see attached" but nothing is attached |
| possibly outdated | the notice is for a past year, or refers to rules "until further notice" |
| poor source text | OCR noise, a cut-off table, illegible digits |
| translation risk | legal terms with no exact equivalent (低保, 特困人员, "qualified non-citizen", "categorically eligible") |
| ambiguous date format | `03/04/2027` with no way to tell the convention |

Keep the uncertainty in what readers see. Don't pick a winner between conflicting numbers and don't
turn "may" into "will". Show both numbers or the hedge, mark the spot (`data-review`), and ask the
reviewer.

## 5. Review items

Group flagged facts into review items, one per question a human can answer. Each item says what's
wrong (`issue`), what to ask (`question_for_reviewer`, ideally answerable with one phone call to the
issuing office) and how the draft currently shows it to readers (`shown_to_reader_as`). Leave
`resolution` empty. Only a person fills it in, after checking. `validate_all.py --final` then
requires every item to have a resolution.

`review.md` is the same list written for a volunteer: short, numbered by review id, with the source
quote and location, so it can be printed and taken to the phone.

## 6. Worked example

Source line 12: `Households receiving SNAP or SSI benefits are categorically eligible regardless of income.`

```json
{
  "id": "F9",
  "category": "eligibility",
  "claim": "If anyone in the household gets SNAP or SSI, the household qualifies no matter what its income is.",
  "value_type": "text",
  "value": "",
  "source_quote": "Households receiving SNAP or SSI benefits are categorically eligible regardless of income.",
  "location": "Who Is Eligible, line 12",
  "confidence": "medium",
  "needs_review": true,
  "review_reason": "translation/interpretation risk: 'categorically eligible' may still require the other conditions (residency, heating costs); the plain version must not imply they are waived."
}
```

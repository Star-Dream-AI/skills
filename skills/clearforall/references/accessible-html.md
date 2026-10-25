# Accessible HTML checklist

Start from `assets/template.html`. It already meets most of these. The list maps to WCAG 2.2 AA.
`check_html.py` checks the items marked ✓auto. The rest need you to look.

## Structure and language
- ✓auto `<html lang>` set (`en`, `zh-Hans`, `zh-Hant`). Any passage in another language gets its
  own `lang`, e.g. `<span lang="en">Form HEAP-1</span>` inside a Chinese page (3.1.1, 3.1.2).
  Without it, screen readers read Chinese with an English voice, or the other way round.
- ✓auto Has a `<title>`, `<meta charset="utf-8">`, and a viewport that allows zoom.
- ✓auto One `<h1>` and headings without skipped levels (1.3.1, 2.4.6).
- ✓auto One `<main>`, and a skip link as the first link (2.4.1).
- Bilingual on one page: give each language its own `<section lang="…">` with its own h2, or
  better, make one page per language and link them both ways ("中文版" / "English version").

## Content
- ✓auto Data tables use `<th scope="col|row">` and a `<caption>`. Don't use tables for layout (1.3.1).
- ✓auto Link text says where the link goes. No "click here" or "点击这里" (2.4.4).
  Phone numbers are `<a href="tel:+15550142290">`.
- ✓auto Images have `alt`. Decorative images get `alt=""` (1.1.1). Avoid images of text.
- Don't rely on colour alone. A flagged item uses a dashed underline **and** the draft notice
  explains it (1.4.1).
- Contrast is at least 4.5:1 for text. The template colours meet this in light and dark mode (1.4.3).
- Base text is at least 16px. The template uses 18px. Text must survive 200% zoom and 320px width
  without horizontal scrolling (1.4.4, 1.4.10).
- Lists are real `<ol>`/`<ul>`. Steps that must happen in order use `<ol>`.
- Write dates in full. Times say am/pm or 上午/下午.

## Privacy and offline use
- ✓auto No external resources: no web fonts, CDN scripts, analytics, embedded maps or remote
  images. The page has to open from a USB stick or a phone with no data, and opening it must not
  tell anyone who looked.
- No forms that submit anywhere. If the source has a form, describe how to get the official one.
- No personal data (see `check_privacy.py`).

## Print
- The template's print styles hide the skip link and print link URLs, so a paper copy still shows
  where to go. The draft notice stays on paper too, because a printed draft is still a draft.

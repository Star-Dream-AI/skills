# Telegram Web A (`web.telegram.org/a/`)

Web A is the second official web client (it started as "WebZ"). It looks closer to Telegram
Desktop and macOS, and some newer features show up here first. Selectors were observed in A builds
from 2024–2025. **Treat them as hints**: check them with a DOM snapshot or
`scripts/web_probe.js`, and prefer roles, aria-labels and visible text.

## Layout

| Area | What it holds | Hint selectors |
|---|---|---|
| Left column | ☰ menu, search, folder tabs, chat list | `#LeftColumn`, `#telegram-search-input`, `.chat-list`, `.ListItem.Chat` (the inner `a` has `href="#<peerId>"`) |
| Middle column | header, messages, composer | `#MiddleColumn`, `.MiddleHeader` (title in `.fullName` / `h3`), `.messages-container`, `.Message` (with `id="message-<id>"` and `data-message-id`), `#editable-message-text`, `.SendButton` / `button.send` |
| Right column | profile, shared media, search | `#RightColumn` |
| Login screen | QR / phone / code / password | `#auth-qr-form`, `#auth-phone-number-form`, `#auth-code-form`, `#auth-password-form` |

- Own messages carry the `own` class on `.Message`.
- The composer `#editable-message-text` is a contenteditable div.

## Navigation by URL

- `https://web.telegram.org/a/#<peerId>` opens a chat you already have (`#777000`,
  `#-1001234567890`).
- Opening a username: `https://web.telegram.org/a/#?tgaddr=tg%3A%2F%2Fresolve%3Fdomain%3Dusername`
  works on current builds. If it doesn't, type the @username into the search box and pick the
  result marked as that exact username.
- The hash route doesn't reload the app. Check the header afterwards.

## Menus

- **☰ (top left)**: Saved Messages, Archived Chats, Contacts, Settings, Night mode, "Switch to K
  version" (wording varies), animations level.
- **Header ⋮**: search, mute, select messages, calls where supported, report, delete or leave.
- **Right-click a message**: reactions on top, then Reply, Copy, Copy Link (groups/channels),
  Forward, Pin, Select, Edit (own), Delete. A also offers **Reply with quote**: select part of
  the message text first.
- **Right-click the send button**: Send without sound, Schedule message.

## Typing and sending (DOM)

```js
await page.goto('https://web.telegram.org/a/#777000');      // or search, see above
await page.waitForSelector('#MiddleColumn .MiddleHeader');
const title = await page.textContent('#MiddleColumn .MiddleHeader .fullName');
await page.click('#editable-message-text');
await page.keyboard.type('Hello!');
await page.keyboard.press('Enter');
await page.waitForSelector('.Message.own >> nth=-1');
```

## Files

The paperclip opens *Photo or Video* or *File*. Use the file-chooser API (`waitForEvent('filechooser')`).
The send dialog has a "compress"/"send as file" option and a caption field. Paste and drop work
as in K.

## Differences from K worth knowing

- The hash is a peer id, not `@username`.
- The settings tree and labels differ, so look for the visible label, not a position.
- A shows a "Reply with quote" flow and topic (forum) view more fully than K on some builds.
- Folders: A shows them as tabs above the chat list. On wide screens K may show them as a
  vertical strip.

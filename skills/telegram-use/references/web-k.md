# Telegram Web K (`web.telegram.org/k/`)

Web K is the default web client: three columns, light and fast, close to the Android look.
Selectors below were observed in K builds from 2024–2025. **Treat them as hints**: check them with
a DOM snapshot or `scripts/web_probe.js`, and fall back to roles, aria-labels and visible text.

## Layout

| Area | What it holds | Hint selectors |
|---|---|---|
| Left column | menu (☰), search, folder tabs, chat list | `#column-left`, `.sidebar-header`, `.input-search input`, `.chatlist`, `a.chatlist-chat[data-peer-id]` |
| Center column | chat header, messages, composer | `#column-center`, `.chat-info` (header), `.bubbles`, `.bubble[data-mid]`, `.input-message-input[contenteditable]`, `.btn-send` |
| Right column | profile / shared media / search results (opens on demand) | `#column-right` |
| Login screen | QR code or phone number form | `.page-signQR`, `.page-sign`, `.page-authCode`, `.page-password` |

- A chat-list item's `data-peer-id` is the peer id: positive for users, negative for groups and
  channels.
- Messages are `.bubble` elements with `data-mid` (message id). Your own messages carry the `is-out`
  class, incoming ones `is-in`.
- The composer is a contenteditable div. It isn't the hidden `<textarea>` some builds also have.

## Navigation by URL

- `https://web.telegram.org/k/#@username` opens a public username.
- `https://web.telegram.org/k/#<peerId>` opens a chat you already have, e.g. `#777000` or
  `#-1001234567890`.
- `https://web.telegram.org/k/#?tgaddr=<url-encoded tg:// link>` opens any tg link, e.g. an invite.
- Changing only the hash doesn't reload the app, which makes it the safest way to jump between
  chats. Afterwards, check the header title.

## Menus

- **☰ (top left)**: Saved Messages, Archived Chats, Contacts, Settings, Night mode, "Switch to A
  version" (wording varies), and on some builds More > Install app.
- **Chat header ⋮**: mute, search, select messages, video/voice call where supported, delete or
  leave.
- **Right-click a message** (or long press): Reply, Copy, Pin, Forward, Select, Edit (own),
  Delete, and a reactions bar on top.
- **Right-click the send button**: Send without sound, Schedule message, Set a reminder (in Saved
  Messages).

## Typing and sending (DOM)

```js
// Playwright example: open the chat by hash, type, check the header, send
await page.goto('https://web.telegram.org/k/#@some_username');
await page.waitForSelector('.chat-info .peer-title');           // header loaded
const title = await page.textContent('.chat-info .peer-title');  // compare with the intended chat
await page.click('.input-message-input[contenteditable="true"]');
await page.keyboard.type('Hello!');                              // real key events
await page.keyboard.press('Enter');                              // or click .btn-send
await page.waitForSelector('.bubble.is-out:last-of-type');       // check it appeared
```

For multi-line text, use `Shift+Enter` between lines, or `page.keyboard.insertText()` for a whole
block (it inserts newlines without sending).

## Files

The paperclip (`.attach-file`) opens a menu: *Photo or Video* (compressed) or *Document* (sent as a
file). With Playwright, use `page.waitForEvent('filechooser')` and `chooser.setFiles(path)`.
Pasting an image (Ctrl+V) or dropping a file also opens the send dialog, where you can add a
caption before sending.

## Quirks

- Right after login, the chat list can take a few seconds to sync. Wait until it stops changing.
- A Service Worker caches the app. After a Telegram update, a reload can briefly show the old UI.
- Notification permission is a browser prompt. Don't accept it unless the user wants it.

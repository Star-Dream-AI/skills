# Telegram Desktop (tdesktop: Windows, Linux, macOS build)

Telegram Desktop is a native Qt app. There's no DOM, and its accessibility tree is thin and differs
by version, so you control it with **screenshots plus mouse and keyboard**. Forks built on it
(Kotatogram, 64Gram, custom-themed builds) have the same layout and shortcuts unless their own
docs say otherwise.

## Layout

- **Left:** ☰ menu (top left), the **Search** field, folder tabs (along the top, or a vertical strip
  on the far left when "folders on the left" is on), the chat list.
- **Right:** chat header (title, status, 🔍 search, 📞 call, ⋮ menu), messages, composer (📎 attach,
  text field, 😊 emoji/stickers, 🎤 voice / ➤ send).
- **Narrow windows** show only one column. Press Esc or the back arrow to get from a chat to the
  list.
- **Side panel** (profile, shared media) opens from the header or ⋮.

## Getting to a chat reliably

1. **Link:** opening `tg://resolve?domain=<username>` (or `https://t.me/<username>`, which hands
   off to the app) jumps straight to that chat. On Windows, `start tg://resolve?domain=durov`; on
   macOS, `open "tg://resolve?domain=durov"`; on Linux, `xdg-open "tg://resolve?domain=durov"`.
   Invite links: `tg://join?invite=<hash>` or `https://t.me/+<hash>`. Telegram shows a preview with
   a Join button and doesn't join by itself.
2. **Search:** click the Search field (or press Esc until no chat is focused, then start typing).
   Type the name or @username and pick the right result: check the subtitle, which shows
   @username or member count.
3. **Saved Messages:** ☰ > Saved Messages, or search "Saved Messages".

Always confirm in a screenshot that the header shows the intended chat before typing.

## Keyboard shortcuts

These are stable across recent versions. If one doesn't work, use the visible UI instead.

| Keys | Action |
|---|---|
| Enter / Shift+Enter | send / new line (can be switched to Ctrl+Enter in Settings > Chat Settings) |
| Esc | close the menu/panel; cancel the reply/edit; leave the chat (back to the list) |
| ↑ in an empty composer | edit your last message |
| Ctrl+↑ / Ctrl+↓ | reply to the previous / next message |
| Ctrl+F | search in the current chat |
| Ctrl+Tab / Ctrl+Shift+Tab, or Alt+↓ / Alt+↑ | next / previous chat |
| Ctrl+B, Ctrl+I, Ctrl+U | bold, italic, underline (selected text) |
| Ctrl+Shift+X, Ctrl+Shift+M, Ctrl+Shift+P | strikethrough, monospace, spoiler |
| Ctrl+K | add a link to the selected text |
| Ctrl+V | paste text, or an image/file from the clipboard (opens the send dialog) |
| Ctrl+L | lock the app (only if a local passcode is set) |
| Ctrl+Q | quit; Ctrl+W closes/hides the window |

On macOS, use Cmd instead of Ctrl.

## Files

- 📎 opens the **native OS file dialog**. Type the full path into the dialog's file-name field
  (Windows: Alt+N focuses it) and press Enter. That's more reliable than clicking through folders.
- Alternatively, copy the file to the clipboard and press Ctrl+V in the composer, or drag it from a
  file manager.
- The send dialog lets you choose **compressed** photo/video or **file** (original quality), add a
  caption, and group several items into an album.
- Downloads go to Settings > Advanced > Download path (default: a `Telegram Desktop` folder inside
  Downloads).

## Menus

- **☰**: profile, New Group, New Channel, Contacts, Calls, Saved Messages, Settings, Night Mode,
  account switcher (several accounts).
- **Right-click a chat in the list**: Pin, Mute, Mark as read/unread, Archive, Add to folder,
  Clear history, Delete.
- **Right-click a message**: Reply, Edit (own), Pin, Copy Text, Copy Link, Forward, Select,
  Delete, Report; the reactions bar sits on top.
- **Right-click the send button**: Send without sound, Schedule message (and "Send when online" in
  private chats).

## Desktop-only abilities

- **Export:** Settings > Advanced > *Export Telegram data* (the whole account), or ⋮ in a chat >
  *Export chat history*. Output is HTML or JSON, saved locally. Confirm the scope with the user
  first: it can be large and private.
- **Multiple accounts:** ☰ > the arrow next to your name > *Add account*.
- **Proxy:** Settings > Advanced > Connection type.
- **Secret chats:** **not available** in Telegram Desktop. If the user needs one, say it has to
  be done on a phone (or in the macOS native app).

## macOS note

macOS has two different apps:

- **Telegram Desktop** (the same as above, Cmd instead of Ctrl).
- **Telegram for macOS** (the native "Swift" app, from the Mac App Store as "Telegram"). It has a
  Mac-style sidebar with a bottom tab bar (Contacts / Calls / Chats / Settings), different menus
  and different shortcuts, and it **does** support secret chats. The recipes in `features.md`
  apply in spirit (right-click menus, paperclip, send-button long-press), but find controls by
  their visible labels.

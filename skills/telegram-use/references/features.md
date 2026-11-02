# Feature recipes

**K** = Web K, **A** = Web A, **D** = Telegram Desktop. Where all three behave the same, there's a
single line. ⚠ marks actions other people can see: confirm them first (SKILL.md, Safety rule 1).

## Contents
1. Find and open a chat
2. Read messages
3. Send text and formatting ⚠
4. Reply, quote, forward, edit, delete, pin, react ⚠
5. Photos, videos, files, voice ⚠
6. Schedule, silent send, Saved Messages
7. Groups and channels ⚠
8. Contacts, mute, archive, folders, read state
9. Settings, sessions, export

## 1. Find and open a chat
- **Known username:** K: go to `#@username`. A: go to `#?tgaddr=tg%3A%2F%2Fresolve%3Fdomain%3D<username>`,
  or use search. D: open `tg://resolve?domain=<username>`.
- **By name:** click the search box at the top left and type the name. Results are grouped (Chats,
  Global search, Messages). Pick an item in the *Chats* group if the user means an existing
  conversation. Global results are public accounts the user hasn't talked to.
- **Folders:** tabs above the chat list (D: possibly a vertical strip). "All chats" is the first
  tab.
- **Archive:** K/A: ☰ > Archived Chats. D: the "Archived chats" row at the top of the list (it may
  be collapsed: right-click it to expand).
- **Check:** the header title (and @username in the profile) matches.

## 2. Read messages
- Scroll the message area. Older messages load as you go. The "↓" button with a counter jumps to
  the newest message or first unread.
- **Search in a chat:** K/A: header 🔍 or ⋮ > Search. D: Ctrl+F. Searching a date: click the date
  badge above messages (or the calendar icon in the search bar) and pick a day.
- **Search everywhere:** the main search box, *Messages* section.
- **Read state:** one tick means delivered to the server, two ticks means read (private chats). In
  groups, two ticks means at least one member read it.
- Reading a chat marks it read for the user's contacts. If the user wants to stay "unread", say
  that opening the chat will clear the unread badge.

## 3. Send text and formatting ⚠
- Click the composer, type, press Enter (or click ➤). Shift+Enter adds a new line.
- **Formatting** by keyboard: select the text, then use the shortcuts in desktop.md (K/A support
  Ctrl+B / Ctrl+I / Ctrl+U / Ctrl+K and show a formatting popup when you select text).
  **Markdown typed as text** also works in D, K and A: `**bold**`, `__italic__`, `` `code` ``,
  ```` ```block``` ````, `~~strike~~`, `||spoiler||`. Check in Saved Messages if unsure.
- **Mentions:** type `@` and choose from the popup. In groups you can mention people without a
  username by picking them from the list.
- **Links** get a preview card. To remove it, click ✕ on the preview above the composer before
  sending.
- **Check after sending:** the bubble shows your exact text and a clock icon (sending), then ticks.
  A red ⚠ means it failed. Don't resend until you've checked it really didn't go.

## 4. Reply, quote, forward, edit, delete, pin, react ⚠
Right-click (D, K, A) the message for its menu.
- **Reply:** menu > Reply (D: also Ctrl+↑). The reply bar appears above the composer. Esc cancels.
- **Quote part:** select the text inside the message, then Reply/Quote (A and D on recent
  versions).
- **Forward:** menu > Forward, then pick the chat in the dialog. The dialog has its own search:
  check the selected chat before confirming. Recent clients offer "hide sender name" in the
  forward options.
- **Edit (own messages):** menu > Edit, or ↑ in an empty composer for the last one. Editing is
  time-limited for ordinary messages, and the edited message shows "edited".
- **Delete:** menu > Delete. Choose "Delete for me" or "Also delete for <name>" / "Delete for
  everyone". You can delete other people's messages only as a group admin (or for yourself only).
  Deleting doesn't undo a notification that's already been delivered.
- **Pin:** menu > Pin. In groups there may be a "notify all members" checkbox: leave it off
  unless asked.
- **React:** hover/right-click and pick from the reactions bar. Double-click (D/K/A) sends the
  default quick reaction. Be careful with stray double-clicks.
- **Select several:** menu > Select, then click others. Bulk Forward/Delete appears in the top or
  bottom bar.

## 5. Photos, videos, files, voice ⚠
- **Attach:** 📎. K: *Photo or Video* / *Document*. A: *Photo or Video* / *File*. D: native dialog
  (type the full path).
- **Compressed vs original:** photos as "photo" are compressed. Use "file"/"document" to keep the
  original. The send dialog shows a toggle.
- **Clipboard / drag-drop:** both open the same send dialog with a caption field.
- **Albums:** select several photos at once. The dialog groups them (up to 10 per album).
- **Voice message:** hold 🎤. In automation, prefer sending an audio file. Hold-to-record needs a
  microphone and real-time interaction.
- **Downloads:** click the file's ⬇. Web saves to the browser's downloads; D saves to its download
  folder (Settings > Advanced).

## 6. Schedule, silent send, Saved Messages
- **Schedule:** type the message, **right-click the send button** > Schedule message, pick the
  date and time and confirm. Scheduled messages sit behind a 📅 icon in the composer until they
  go out, and you can edit or delete them there.
- **Silent:** right-click send > Send without sound (the recipient gets no notification sound).
- **"Send when online"** (private chats, D and some web builds): the same menu.
- **Saved Messages:** a private notes chat, good for testing and for drafts. In Saved Messages,
  "Schedule" is called "Set a reminder".

## 7. Groups and channels ⚠
- **Join by invite link** (`t.me/+hash`, `t.me/joinchat/...`): opening it shows a preview with
  member count and a Join button. Joining is visible to members, so confirm first. Public groups:
  open `@name`, then Join.
- **Pace your joins.** Join one group or channel at a time, and only the ones the user named. Don't
  work through a list of links in a loop. If you see "Too many attempts" / a wait time, stop and
  report it. Retrying makes the wait longer and risks an account limit.
- **"Request to join" instead of "Join":** the group approves members by hand. Send the request
  once (some groups ask a question first: let the user answer it), then tell the user it's pending.
  Re-requesting doesn't speed it up. You'll get a service message when you're accepted.
- **Verification after joining.** Right after joining, read the newest messages before doing
  anything else. Typical checks:
  - a captcha/verification bot reply that mentions you: a button ("I'm not a robot"), a sum to
    solve, an emoji or picture to pick, or "send /start to @SomeBot in private";
  - a pinned message with rules and an "Accept" button, or a requirement to write an introduction;
  - being muted ("you can't send messages here") until verified.

  They usually have a deadline (often 1–5 minutes), and failing means being kicked, sometimes
  banned. Tell the user immediately what is being asked, quoting the message and the time limit.
  The user completes captchas themselves. Only press a plain rules/consent button if the user
  told you to. Never post in the group before verification succeeds, and if you get kicked for
  failing, don't rejoin straight away: ask the user.
- **Leave:** header ⋮ > Leave group / Leave channel (sometimes "Delete and leave"). Confirm.
- **Members and info:** click the header to open the profile panel: members, admins, links, shared
  media.
- **Invite link:** profile > Invite link / Add members (admins). Creating or revoking links is an
  admin action, so confirm.
- **Admin actions** (ban, restrict, delete others' messages, change permissions): only on explicit
  instruction. They affect other people.
- **Topics (forums):** groups with topics show a topic list first. Open the right topic before
  sending.
- **Channels:** only admins can post. Posting to a channel reaches every subscriber, so always
  confirm the text and the channel.

## 8. Contacts, mute, archive, folders, read state
- **Contacts:** K/A: ☰ > Contacts. D: ☰ > Contacts. Adding a contact may share your phone number
  (there's a checkbox), so watch it.
- **Mute:** header ⋮ > Mute (choose duration) or right-click the chat in the list.
- **Archive:** right-click the chat > Archive. Muted archived chats stay archived when new messages
  arrive. Unmuted ones come back.
- **Folders:** Settings > Folders (create, add chats); or right-click a chat > Add to folder.
- **Mark as read/unread:** right-click the chat in the list.

## 9. Settings, sessions, export
- **Open settings:** K/A: ☰ > Settings. D: ☰ > Settings.
- **Notifications, language, chat appearance:** safe to change on request.
- **Privacy and security** (phone number visibility, last seen, who can add you to groups, 2FA):
  explain the effect and confirm before changing.
- **Active sessions:** Settings > Privacy and Security > Active sessions (wording varies; D:
  Settings > Devices). "Terminate all other sessions" logs out every other device, so confirm and
  make sure the user isn't relying on one.
- **Log out:** confirm. Logging out of Web or Desktop doesn't delete anything, but local data
  such as downloaded files may be cleared.
- **Export:** D only (see desktop.md). Web has no export.

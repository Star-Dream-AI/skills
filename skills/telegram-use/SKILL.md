---
name: telegram-use
description: How an AI agent operates Telegram for a user. Covers Telegram Web (web.telegram.org K and A versions), Telegram Desktop, and the Bot API / MTProto client libraries. Explains how to tell which client is in front of you, how to find chats, read and send messages, reply, forward, edit, delete, send files, schedule messages, manage groups and channels, and change settings, plus where Web and Desktop differ. Use this whenever an agent has to do anything in Telegram through a browser, a screenshot-and-click desktop session or code, even if the user only says "message X on Telegram", "check my TG", "发个电报消息", "在 Telegram 网页版里…", "用 Telegram 桌面端…" or "write a Telegram bot". It also covers safety rules for acting in someone's real account.
compatibility: Web parts need browser automation (Playwright, Chrome extension or similar) or screenshot-based computer use. Desktop parts need computer use. API parts need Python 3.8+ and network access to api.telegram.org.
metadata:
  version: "0.1.0"
---

# Telegram use

You're acting inside a real person's Telegram account, or driving their bot. Most actions there are
visible to other people the moment they happen. A message sent to the wrong chat can't really be
taken back: deleting it removes it, but the recipient may already have seen it or got a
notification. So this skill is about being **accurate** and **careful** as much as it is about
where the buttons are.

## Safety rules (read first)

1. **Confirm outward actions.** Before you send, forward, post, react, join, leave, block, delete
   or change privacy settings, state exactly what you'll do and in which chat, and get the user's
   OK. That's unless the user already gave that exact instruction ("send 'on my way' to Mum").
   Reading is fine without asking.
2. **Check the chat header before every send.** Chat names repeat ("Alex", "Family"). Compare the
   title, and if possible the @username or avatar, with what the user meant. The chat list
   reorders itself whenever a message arrives, so a click position you saw earlier may now be a
   different chat.
3. **Login codes and 2FA passwords belong to the user.** Telegram sends login codes as a message
   from the official "Telegram" account (id 777000) and warns never to share them. Never read a
   code out of the chats to log in somewhere else, never forward it and never type it anywhere the
   user didn't ask. Let the user do the login steps (scanning the QR code, entering the code and
   password) unless they explicitly hand them to you.
4. **Test in Saved Messages.** If you're unsure how something behaves (formatting, files,
   scheduling), try it in *Saved Messages* first. Only the user sees that chat.
5. **Don't automate a personal account with scripts unless the user knows the risk.** Mass
   messaging, scraping members or adding people to groups through the user API breaks Telegram's
   terms and can get the account limited or banned. Bots exist for automation.
6. **Don't join groups and channels in quick succession.** Joining many in a short time is a
   classic spam pattern. Telegram answers with "Too many attempts, try again later" / `FLOOD_WAIT`,
   and it can limit the account (the user can no longer message strangers or join anything). Join
   only the groups the user asked for, one at a time, with a pause between them. If Telegram says
   to wait, stop, tell the user how long, and don't retry. There's also a cap on how many channels
   and supergroups one account can be in (about 500; more with Premium).
7. **Many groups make new members pass a check, so handle it, don't skip it.** After joining, look
   for a verification step before doing anything else: a "Request to join" that an admin must
   approve, a captcha/verification bot message ("press the button within 60 seconds", a sum, pick
   an emoji), or rules you must accept. These usually have a **time limit**, and failing means
   being kicked or muted. Tell the user right away what the group asks for, quoting the bot's
   message. Let the user do it, or follow their explicit instruction for a plain "I agree to the
   rules" type button. Don't try to defeat captchas that exist to tell people from bots. Don't
   post in the group until the check is passed. See `references/features.md` §7.
8. **Private content stays private.** Don't copy chat contents, contacts or phone numbers into
   other tools, logs or web searches beyond what the task needs.

## Step 1: work out which client and which control method

| You see / have | Client | Read |
|---|---|---|
| URL `web.telegram.org/k/...` | Telegram Web **K** | `references/web-k.md` |
| URL `web.telegram.org/a/...` | Telegram Web **A** | `references/web-a.md` |
| URL `web.telegram.org/` with no letter | it redirects to K or A, so check again after it loads | |
| A native window titled "Telegram" (Windows/Linux, or the same app on macOS) | **Telegram Desktop** (tdesktop) | `references/desktop.md` |
| Native macOS app with a Mac-style sidebar and Settings in the tab bar | "Telegram for macOS" (a separate app) | `references/desktop.md` §macOS note |
| A bot token (`123456:ABC...`) | Bot API | `references/api.md` |
| api_id / api_hash, or a Telethon/Pyrogram session | MTProto user/bot API | `references/api.md` |

With browser automation on Web, run `scripts/web_probe.js` in the page (see the script header). It
reports the version (K or A), whether the user is logged in, the open chat and the visible chat
list, and which selectors matched. Use it before acting and again after.

How you control the client:

- **DOM / browser automation (Web only):** the most reliable way. Find elements by role, aria-label
  or visible text first, and use the class names in the references as hints. Telegram ships UI
  updates often.
- **Screenshot + mouse/keyboard (Web or Desktop):** take a screenshot, act, then take another
  screenshot to check. Prefer keyboard shortcuts and links (`tg://` / `t.me`) to clicking at
  pixel positions, because positions shift.
- **API (no UI):** the most precise option, but limited. Bots can only talk to people who started
  them, and the user API needs the user's credentials.

## Step 2: the loop for every UI action

1. **Observe.** Take a snapshot or screenshot. Is the user logged in? Which chat is open? Is a
   dialog or menu covering something?
2. **Locate** the target with the most stable handle available: a link/URL, a keyboard shortcut, an
   aria-label or text, and only then coordinates.
3. **Act** once.
4. **Verify.** Is the message in the chat with your text and a clock/tick icon? Did the menu
   close? Was the file attached? If not, observe again before you retry, so you don't send twice.

Things that commonly trip agents up:

- The message box is a **contenteditable div**, not an `<input>`. Click it, then type with real
  keyboard events. Setting `value` or `innerHTML` doesn't update the app's state, and the send
  button won't use the text.
- **Enter sends** by default and **Shift+Enter** adds a new line, in both Web and Desktop. A user
  can switch this to Ctrl+Enter in settings, so look at the hint in the input area if a message
  doesn't go.
- Unread counts and the chat order change while you work. Re-find elements instead of reusing old
  handles or coordinates.
- Large chats load lazily. Messages you scroll past may unload, so search instead of scrolling far.

## Step 3: do the task

`references/features.md` has a recipe for each basic task, with the differences between Web K,
Web A and Desktop:

- Find and open a chat (search, @username link, folders, archive)
- Read: scroll, jump to a date, search inside a chat, unread messages
- Send text and formatting (bold, italic, code, spoiler, links), mentions, emoji
- Reply, quote, forward, edit, delete (for me / for everyone), pin, react, select several
- Send photos, videos and files (compressed or as a file), paste from the clipboard, voice messages
- Schedule a message, send silently, Saved Messages
- Groups and channels: join by link, leave, members, invite links, basic admin actions
- Contacts, mute, archive, folders, mark as read
- Settings: notifications, privacy, language, sessions, and export (Desktop only)

### Web vs Desktop at a glance

| | Web (K / A) | Desktop |
|---|---|---|
| Control | DOM or screenshots | screenshots only (Qt app, very thin accessibility tree) |
| Open chat by username | `https://web.telegram.org/k/#@username`; A uses the chat id in the hash, see refs | `tg://resolve?domain=username` link, or the search box |
| Upload a file | hidden `<input type=file>`: use the automation's file-chooser API | native OS file dialog, or paste/drag-drop |
| Downloads | the browser's download folder | Telegram's download folder (Settings > Advanced) |
| Secret chats | **not available** | **not available** on Windows/Linux (macOS native app and mobile only) |
| Export chat history | not available | Settings > Advanced > Export Telegram data; or ⋮ in a chat > Export chat history |
| Multiple accounts | one per browser profile | several, switch from the side menu |
| Local passcode lock | available in settings | available; Ctrl+L locks when it's set |
| Calls | varies by version, so check the chat header | voice and video calls, plus group calls |

## Step 4: report back

Tell the user what you did and where ("Sent 'on my way' to *Mum* (@mum_k) at 14:02; it shows two
ticks, so it's been read"). Also say what you didn't do and why ("Didn't leave the group: it has
2 chats with that name, which one?"). If something might have gone out twice, say so. Don't hide
it.

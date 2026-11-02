# Telegram without the UI: Bot API and MTProto

## Pick the right API

| Need | Use |
|---|---|
| Automated replies, notifications, a bot people can talk to | **Bot API** (HTTPS + bot token) |
| Act as the user (their chats, their history) | **MTProto user API** (Telethon, Pyrogram, TDLib) with the user's own api_id/api_hash. Only with the user's informed consent, and mind the ToS |
| Read a public channel | MTProto, or open `https://t.me/s/<channel>` in a browser (public preview page) |

## Bot API essentials

- Token from **@BotFather** (`/newbot`). It looks like `123456789:AA...`. Treat it as a password:
  keep it in an env var, never in code you share, and if it leaks, `/revoke` it in BotFather.
- Endpoint: `https://api.telegram.org/bot<TOKEN>/<method>` with JSON or form parameters.
- **Bots cannot start conversations.** A user (or group) has to message or add the bot first. Until
  then, `sendMessage` to them fails with `403 Forbidden: bot can't initiate conversation`.
- **chat_id:** take it from the updates the bot receives (`message.chat.id`). Groups and
  supergroups are negative (`-100…` for supergroups and channels). `@channelusername` works for
  public channels where the bot is an admin.
- **Privacy mode** (on by default): in groups, the bot only sees commands, replies to itself and
  mentions. Turn it off in BotFather (`/setprivacy`) or make the bot an admin to see everything.
- **Receiving updates:** either `getUpdates` (long polling, pass `offset` = last update_id + 1) or a
  webhook (`setWebhook`, HTTPS). You can't use both at once: `getUpdates` returns 409 while a
  webhook is set.
- **Formatting:** `parse_mode: "HTML"` is the least error-prone. With `MarkdownV2`, you have to
  escape `_*[]()~\`>#+-=|{}.!`.
- **Limits:** roughly 1 message/second per chat, about 20 messages/minute in a group, about 30
  messages/second overall. A `429` response includes `retry_after`: wait that long.
- **Files:** send by URL, by `file_id` (already on Telegram) or by multipart upload. Bot uploads are
  capped at 50 MB and downloads via `getFile` at 20 MB unless you run a local Bot API server.

`scripts/bot_api.py` is a stdlib-only helper: `getMe`, `getUpdates`, and `sendMessage` (which
needs `--yes` to actually send). Usage is in its `--help`.

## MTProto user API essentials

- Get **api_id / api_hash** at https://my.telegram.org > API development tools, logged in as the
  user. These identify the app. The **session file** that a library creates after login gives
  **full access to the account**: store it like a password and delete it when you're done.
- Login asks for the phone number, then the code (sent to the user's other Telegram apps), then the
  2FA password if set. The user enters these. You don't fetch the code from their chats.
- Telethon minimal example:

  ```python
  from telethon.sync import TelegramClient
  with TelegramClient("user_session", API_ID, API_HASH) as client:   # prompts for login the first time
      for msg in client.iter_messages("some_username", limit=20):
          print(msg.date, msg.sender_id, msg.text)
      # client.send_message("some_username", "Hello")  # confirm with the user first
  ```

- `FloodWaitError` (or `FLOOD_WAIT_X`) means wait X seconds. Don't retry in a tight loop. Repeated
  floods, mass invites or messaging strangers lead to account limits (`PEER_FLOOD`) or bans.
- Bots can log in through MTProto too (`client.start(bot_token=...)`), which lifts the 50 MB
  upload limit.

## Safety

The same rules as the UI: confirm before anything other people can see, never touch login codes,
and keep tokens and session files out of logs, repos and chat transcripts.

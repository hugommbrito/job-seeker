# 0010. Telegram: linked by polling from the worker, delivered once, quiet hours per user

2026-11-24. Accepted. Settles how "Telegram (one bot, linked per user)" in the implementation
plan, section 7, Phase 1, is built; the deployment part is untested until a bot exists.

## Context

A user links their chat by sending the bot a one-time code. The bot hears about it either from
a webhook (Telegram calls a public route of the app) or by polling `getUpdates`. Messages sent
to the bot are untrusted input. The bot token is the key to the whole bot.

## Decision

- **Polling, from the worker, every minute.** No public route receives Telegram's calls, nothing
  has to be registered with Telegram at deploy time, and it works the same on a laptop. The
  token is a file mounted into the worker alone, like the gateway key (ADR 0008); the api knows
  only the bot's public username, to build the link.
- **The link code proves the user, not the chat.** The deep link carries `<user id>_<code>`.
  The code is random, stored only as a hash in that user's own row, and expires in fifteen
  minutes. The user id only says whose row to look in, under that user's tenant context. Any
  other message to the bot is ignored and never stored.
- **Exactly once.** A notification is unique per (user, dedupe key) in the database. Pushing it
  is a delivery row claimed before the send: a crash between claim and send loses that push,
  where the other order would repeat it. A failed send is retried up to three times; "blocked"
  switches the channel off until the user links again. The in-app notification exists either way.
- **Quiet hours in the user's timezone.** The rental monitor used one fixed zone; here each
  user's profile decides. A push due in quiet hours waits until they end.
- **Plain text.** No parse mode, so nothing a company name or a note contains can become markup.
  The token never appears in a log or a stored error: failures are kept as a short reason.

## Consequences

- Linking takes up to a minute to be noticed. That is the price of not exposing a webhook.
- One `notifications.poll_telegram` run is recorded per minute, which makes it the most
  frequent row in `operations_taskrun`; the 30-day retention keeps that bounded.

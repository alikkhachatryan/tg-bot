# Vacancy source configuration

All values below belong in the local `.env` file. A source is enabled only when its name
appears in `VACANCY_SOURCES`; company-board adapters with an empty board list are skipped.

## Armenia-focused order

1. HH official API results scoped through the live Armenia and Yerevan area entries.
2. Explicit Greenhouse and Lever boards for Armenian employers or international
   employers that accept candidates in Armenia.
3. Remotive vacancies whose geographic restriction allows the candidate's location.
4. Approved Armenian Telegram channels and groups where the bot has been added.

Geographic eligibility is not inferred from the word "remote" alone. The matching stage
will reject a remote vacancy when its `remote_scope` excludes Armenia.

## HH

Register an application with HH and use an identifying user-agent containing a real
contact address. Configure:

```dotenv
VACANCY_SOURCES=hh,remotive,greenhouse,lever
HH_USER_AGENT=tg-job-match-bot/0.1 (your-email@example.com)
HH_ACCESS_TOKEN=your-oauth-access-token
HH_FOCUS_LOCATIONS=Armenia,Yerevan
HH_SEARCH_TERMS=Python,Backend,QA,DevOps
```

The adapter reads `/areas` on each run instead of assuming stable area IDs. It sends the
required HH user-agent header, an OAuth bearer token, a seven-day window,
and at most `HH_PER_PAGE` results per configured search term.

## Greenhouse and Lever

These APIs expose the published jobs of specified companies, not a catalogue of every
company. Add known public board identifiers:

```dotenv
GREENHOUSE_BOARDS=company-one,company-two
LEVER_SITES=company-three,company-four
```

## Remotive

The public feed is requested no more than four times per day by the scheduler. Every
stored origin retains `Remotive` attribution and its original vacancy URL. Do not remove
that attribution from Telegram notifications or later UI output.

## Telegram channels and groups

Telegram sources use an explicit allowlist and are independent of the scheduled HTTP
adapters. Configure stable signed chat IDs whenever possible:

```dotenv
TELEGRAM_VACANCY_CHAT_IDS=-1001234567890,-1009876543210
TELEGRAM_VACANCY_CHAT_USERNAMES=jobs_armenia,remote_jobs
```

Add the bot as an administrator of a channel. In a group or supergroup, add the bot and
grant it access to messages; administrator access avoids BotFather privacy-mode limits.
Run `/chat_id` inside the chat to get its numeric ID. Usernames are normalized without
the leading `@`, but IDs are preferred because usernames can change.

The Bot API delivers new and edited posts after the bot is added; it does not expose
arbitrary channel history. Posts must contain explicit vacancy or hiring language and a
usable application or source link. Public chats use their `t.me` message URL. Private
supergroups and channels use Telegram's private message link; private basic groups without
a canonical message link are skipped. The canonical vacancy stores the chat attribution
and source link, but not the message author's Telegram identity.

## Not supported without permission

Do not add Selenium login automation, CAPTCHA bypasses, userbots, or HTML scrapers for
Staff.am, Job.am, LinkedIn, HH, or unapproved Telegram channels. A new Armenian source
requires an official API, partner feed, written permission, or user-forwarded content,
followed by an isolated adapter and contract tests.

## Manual verification

After PostgreSQL is running and migration `20260806_0006` is applied, run one import:

```bash
python -m app.sources.sync
```

With Docker Compose, run the same module in the scheduler container. The command prints
source names, safe statuses, and item counts; it never prints access tokens or full raw
payloads.

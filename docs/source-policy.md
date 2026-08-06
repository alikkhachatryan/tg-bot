# Vacancy source policy

The product uses one adapter per vacancy source. It does not automate website sessions
when an official API or approved feed is available, and it does not bypass CAPTCHA,
Cloudflare, authentication controls, or access restrictions.

Initial source order for an Armenia-focused combined market:

1. HH.ru through its official API and OAuth, after registering an application.
2. Approved Armenian partner feeds and Telegram channels where the bot is explicitly
   permitted to read posts.
3. Public company postings from selected Greenhouse and Lever job boards.
4. Remotive's public API, with source attribution, original links, and its published
   request-frequency restrictions.
5. Vacancies manually forwarded by users.

Staff.am, Job.am, LinkedIn, and similar services are not scraped. They require an official
API, a partner feed, written permission, or user-forwarded vacancy content before an
adapter is enabled.

All adapters produce the same canonical vacancy structure. Approved Telegram chats are
handled through a strict allowlist; only new and edited posts are received, and sender
identities are not retained. Source references and content hashes are retained so
normalization can merge duplicates while preserving provenance.
Matching ranks vacancies by candidate fit, geography, remote eligibility, salary,
freshness, and explicit preferences rather than by source popularity.

The initial implementation runs at 00:10, 06:10, 12:10, and 18:10 UTC. A failed source
does not stop other adapters. Every run stores only a safe error code and item counts;
access tokens and raw authorization headers are never persisted.

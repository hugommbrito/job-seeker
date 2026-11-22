# Decision log

Part B of the planning package closed on 2026-11-21. See the [README](README.md) for how the package is organised and how later decisions are recorded.

Decisions taken during discovery on 2026-11-20 and 2026-11-21. "Proposal" is the original product proposal. Entries are in the order they were taken; a superseded entry keeps its original choice.

| # | Decision | Options considered | Choice | Why |
| --- | --- | --- | --- | --- |
| 1 | Scope of the discovery session | Plan only; plan and build | Plan only | Implementation starts from a clean context with this package |
| 2 | Phase order | Tracker first as proposed; lean tracker then discovery; lean tracker then application help | Lean tracker, then discovery and ranking, then application help, then email | A tracker has little to track until discovery works, and email reading has the lowest return at low volume |
| 3 | Users | Single user; single user with tenant-ready schema; two users from the start | Two users from the start, isolated | A second person uses it immediately |
| 4 | Showcase | README and screenshots; separate demo instance; guest login on the real instance | Guest login on the real instance | One deployment to maintain. Accepted cost: isolation becomes a Phase 0 requirement |
| 5 | Repository visibility | Private; private but ready to open; public from the first commit | Public from the first commit | The project doubles as a portfolio piece |
| 6 | Language | Portuguese UI; English everywhere | English for code, docs, UI and commits | Public portfolio |
| 7 | Planning documents | Outside git; in the repository | In the repository, as a generic product spec with personal context kept private | The decision process should be traceable without exposing anyone's search |
| 8 | Hosting | Railway; Coolify; home server; local only | Coolify on an existing cloud server, database on the same host | Capacity is already available |
| 9 | Backend stack | Same as the rental monitor; different stack | NestJS, Drizzle, PostgreSQL with pgvector, Zod, Vitest. **Superseded by #29** | Proven conventions and reusable code |
| 10 | Front end | React and Vite with Tailwind and shadcn/ui; the same with MUI; Next.js | React and Vite with Tailwind and shadcn/ui, served by the API | One container; server rendering adds little behind a login |
| 11 | Job queue | BullMQ with Redis; pg-boss | BullMQ with Redis. **Superseded by #29** | First-party NestJS integration, per-queue rate limits, ready-made dashboard |
| 12 | Model gateway | OpenAI-format calls through LiteLLM; Anthropic-format calls through LiteLLM; direct SDK | Anthropic format through LiteLLM with the official SDK | Keeps the gateway's keys, cost tracking and model switching without depending on a translation layer for structured output and caching |
| 13 | Model per task | Opus 5.5 everywhere; tiered from the start; low-cost ceiling | `claude-opus-5-5` everywhere until the eval justifies a cheaper model | Measure before trading quality for cost |
| 14 | Embeddings | OpenAI; Voyage; local | OpenAI through the same gateway | A key is already available |
| 15 | Sources | As proposed | Greenhouse, Lever, Ashby for the watchlist; Adzuna for broad discovery; manual capture for everything else | Official public APIs only |
| 16 | Initial watchlist | Researched and approved; supplied by the owner; start minimal | About 40 companies researched and validated, approved before seeding | Useful from day one without unreviewed data |
| 17 | Capture from sites without an API | Paste text or URL; browser extension; bookmarklet | Paste in the app | No install, works on a phone; the extension stays in the backlog |
| 18 | Career tracks | One profile; several tracks per profile | Several tracks, each with its own target, embedding and CV variant | One person can fit more than one kind of role |
| 19 | Sources for non-tech careers | Decide now; keep it data-driven | Sources and rubric configurable per profile | The second user's field is not defined yet |
| 20 | Mailboxes | IMAP; provider APIs | IMAP with app passwords behind a provider interface | One connector covers both providers in use |
| 21 | Email content and models | Cloud model after filtering; rules first; no cloud model | Cloud model, after a server-side sender filter, with human approval of every change | Invites and scheduling emails vary too much for rules alone |
| 22 | Notification channels | Telegram; email; in-app; web push | Telegram, email and web push, plus the in-app centre | Requested |
| 23 | CV output | PDF from the app; PDF and DOCX; text only | PDF generated from an HTML/CSS template | The app keeps the exact version sent |
| 24 | Larger modules to schedule | Networking CRM; interview prep; salary intelligence; gap map | Interview prep and salary intelligence get a phase; the rest is backlog | Priority |
| 25 | Commute | Offline heuristic; routing API; heuristic plus routing for the shortlist | Offline heuristic: distance from home plus the office's transit tier (subway over streetcar over bus), scaled by days on site | Free, deterministic, and the home location never leaves the server |
| 26 | File storage | S3 bucket; database | Postgres `bytea` behind an interface | Raised in plan review: files are small, and this puts them under row-level security with one less service |
| 27 | Private captures | A flag on the shared catalog; a per-user table | Per-user `user_postings` | Raised in plan review: one missed predicate on a shared table would leak a capture |
| 28 | Experience bank timing | With the CV builder; before ranking | Before ranking | Raised in plan review: the rubric judges against it, so calibrating without it would be invalid |
| 29 | Backend framework, revisited | Stay with NestJS; switch to Django | Django with Django Ninja and Pydantic, Celery with Redis, WeasyPrint for PDFs. The front end stays React and TypeScript | Python serves the model-heavy parts better (evals, text and PDF tooling, Pydantic with the SDK); Django brings authentication, CSRF protection and an admin; no headless browser is needed; the portfolio gains a second backend stack. Accepted costs: the rental monitor's modules are ported instead of copied, API types are generated instead of shared, two toolchains in CI, row-level security written as raw SQL migrations |

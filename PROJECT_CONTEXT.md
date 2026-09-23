# KundaliAI project context

Reviewed 2026-09-23. This is a repository orientation and implementation baseline for subsequent requirements, not a claim that every code path or astrological rule has been independently audited. Recheck affected files before making changes. No application code was changed during this review.

## Working rules

- Root `AGENTS.md` requires reading https://docs.expo.dev/versions/v57.0.0/ before writing code. The exact versioned reference was read during this review.
- Preserve pre-existing untracked files: `.claude/settings.local.json`, prediction comparison CSVs v7-v10, and QA JSON reports v7-v10. Do not treat them as disposable generated output.
- Do not expose `.env`, database contents, credentials, or user chat/profile data in notes. Runtime provider configuration was not read; settings below describe source defaults.

## Architecture

- Frontend: Expo ~57.0.23, React 19.2.3, React Native 0.86.3, TypeScript ~6.0.3, React Navigation 7, Zustand 5, i18next. Uses React Navigation, not Expo Router.
- Backend: Python FastAPI, Pydantic settings/schemas, SQLAlchemy async sessions, Alembic, Swiss Ephemeris (`pyswisseph`), optional OpenAI/Anthropic integrations.
- Source inventory: 91 files under `src`, 131 under `backend/app`, 47 under `backend/tests` at review time.
- Main dependency direction: screens/stores -> `src/api/client.ts` adapters -> `httpClient.ts` -> `/api/v1` routers -> services -> pure `astro` calculations and DB models.
- `backend/README.md` is stale: frontend HTTP integration is implemented; OpenAI support, real optional STT, prediction, and personalization substantially exceed its description and old test count.

## Frontend entry and navigation

- `index.ts` registers `App.tsx`; App loads Mukta/Baloo 2 fonts, initializes i18n, wraps gesture/safe-area/navigation providers, and mounts the global voice player.
- `RootNavigator.tsx` waits for persisted user-store hydration and an 800 ms splash minimum. `hasOnboarded` selects onboarding versus main navigation.
- Onboarding registrations: Welcome, AppInfo, Auth, BirthData, TopicSelection, TopicFollowUp, AiProcessing, Validation, Preferences. Returning users hydrate their server profile in Auth.
- Main tabs: HomeDashboard, CompleteKundali, RishiChat, Charts, Profile. Web substitutes a left sidebar; native uses bottom tabs with a central chat button.
- Other routes: ManglikAnalysis, UpgradePlans, PeriodAnalysis, HoroscopeDetail, GunaMilan, PassStore, Payment, Insights, MyLifeTwin, LifeTimeline, ChartLookup, FollowUpQuestions.
- Shared chart components support north/south Indian layouts; `.web.tsx` implementations exist for NorthIndianChart and DateTimeField.
- Visual design is the dark indigo/gold “Astrolabe Glass” theme in `src/theme/theme.ts`, with GlassSurface, CosmicBackground, StarField, reusable cards/buttons, and web containers. `app.json` still declares light UI and App sets a dark status bar; review platform appearance if changing the theme.

## Frontend state and API contracts

- `useUserStore`: persisted language, auth token, birth data, onboarding, preferences, plan, credits, chart style. AsyncStorage backs persistence. Hydration restores the HTTP token. Authenticated HTTP 401 triggers local logout.
- Birth edits await server success, clear the client complete-kundali memo, and invalidate the Kundali store. Preference saves update locally first and ignore failed server saves.
- `useKundaliStore`: in-memory language/type keyed caches for summary, complete report, Manglik, charts, dasha, validation, identity; loading/error flags per feature.
- `useChatStore`: AsyncStorage conversations keyed by Rishi. Logout/account deletion clear this store. Server history and client transcript persistence are separate mechanisms.
- `useInsightsStore`: local templated insight generation from preferences and summary, not a backend notification feed.
- `useVoiceStore`: on-device `expo-speech`; elapsed duration is estimated, and resume restarts speech rather than seeking.
- `src/api/client.ts` translates snake_case server fields to camelCase UI types in `src/types/kundali.ts`. It also memoizes resolved/in-flight complete-kundali requests per language.
- `httpClient.ts` uses fetch, bearer auth, JSON errors and multipart upload; sends ngrok's skip-warning header. No request timeout is implemented there.
- UI languages are English/Hindi/Hinglish. `toContentLanguage` maps Hinglish to English for bilingual generated reports; chat accepts all three.

## Product features and integration status

- Real backend calls cover email login/signup, profile/birth data/preferences, kundali/identity, D1/D9/D10, ad hoc charts, dasha, daily/focus readings, period analysis, Guna Milan, chat, life context/timeline, personalization, and subscription checkout.
- Six Rishis: Vyasa (default generalist), Vasishtha, Parashara, Gargi, Agastya, Bhrigu. All share `/chat/astro`; specialist domain routing is handled server-side.
- Recording uses `expo-audio`; transcription uploads to `/voice/transcribe`. OpenAI STT is implemented when selected/configured. Stub mode reports unavailability. Backend TTS remains a stub; frontend narration uses device speech.
- CompleteKundali Save only sets component state and displays an alert; PDF Download only displays a preparation alert. No actual PDF export is implemented in those handlers.
- Pass payment is a local timed demo that increments local credits. Subscription upgrade calls the backend, but complete live checkout UX needs review; the screen sets the selected local plan after the call.
- Analytics currently logs to the console.

## Backend routing and persistence

- `app/main.py`: request logging, CORS, SlowAPI rate limits, `/health`, common 500 handler, `/api/v1` router. Dev/test startup creates tables; production is expected to run Alembic.
- Router groups: auth, user, kundali, chart, dasha, horoscope, analysis, prediction, chat, voice, geocode, subscription, admin.
- `api/deps.py`: bearer JWT user resolution, active-user/admin checks, birth-profile requirement, subscription tier dependency.
- DB defaults to local SQLite via aiosqlite; asyncpg dependency supports configurable PostgreSQL. Do not assume which database a running deployment uses.
- Models include users/OTP, encrypted birth profiles, subscription, chat messages/embeddings, life context facts, decisions/events, life state, important dates, prediction feedback/query logs, audit logs, usage counters, and result caches.
- Birth name/date/time/place are Fernet-encrypted; coordinates and time-zone offsets remain queryable plaintext. Selected life-state dates are encrypted too.
- BirthProfile.version increments on edit and participates in cache selection. LifeState.version and algorithm-version metadata invalidate prediction caches. Old birth-version cache rows are retained rather than pruned.
- `cache_utils.py` handles concurrent cache-insert conflicts. Migrations are under `backend/alembic/versions`.

## Calculation and prediction engine

- `astro/ephemeris.py`: Swiss Ephemeris Moshier mode, Lahiri sidereal zodiac; re-applies sidereal mode inside relevant calls because Swiss Ephemeris state is thread-local. CPU work is offloaded by service callers where implemented.
- Whole-sign houses, mean-node Rahu, Ketu opposite Rahu; D1/D9/D10 chart generation and Vimshottari mahadasha/antardasha/pratyantardasha.
- Other pure modules cover additional vargas, panchang, Manglik/doshas, yogas, Guna Milan, natal dignity/strength, Shadbala, Ashtakavarga, transits, Varshaphala/solar returns, event windows, age plausibility, marriage and property analysis.
- `prediction_service.py` orchestrates year/multi-year outlook, marriage/life-event timing, decisions, property analysis, and life theme.
- Timing algorithm version is 20; significator-strength version is 1. Future horizon is 30 years; default past recency is 10 years with broader fallback. Multi-year outlook caps at 3 years.
- Window selection combines dasha rules, house-lord versus karaka evidence, natal strength, transit corroboration/obstruction, and age plausibility. It distinguishes a useful upcoming window from a stronger long-term peak. These are encoded heuristics, not statistical accuracy measurements.
- Life-state gates affect marriage/children/business/promotion/property framing. Expected delivery can anchor an already-known pregnancy rather than predicting a new conception window.
- Property assessment separates natal support, timing, and practical context; evidence records explicitly distinguish classical references from derived scoring. Preserve that distinction when extending it.
- `Ganita.docx` and `Ganita_v2.docx` are calculation references; v2 is a detailed trilingual edition with worked charts. Sampled their text during orientation; their claims/formulas were not independently verified against every current implementation.
- Root prediction QA JSON/CSV files are historical comparison artifacts, not proof of live behavior or empirically validated forecasting accuracy.

## Chat and personalization pipeline

- `api/v1/chat.py` contains substantial orchestration, not merely a thin router.
- Loads chart/dasha/daily facts and recent history (limit 20), handles pending follow-ups, classifies the question, extracts structured context, applies life-state updates, retrieves relevant calculations, and then produces the reply.
- `chat_understanding.py` supports OpenAI classification/extraction and deterministic fallback logic; handles topics, direction, events, decisions, state, feedback and important dates.
- `interpretation/factory.py` uses deterministic templates unless `USE_AI_INTERPRETATION` and a provider key are enabled; OpenAI is preferred over Anthropic if both exist. Calculated facts are supplied to interpreters for prose.
- `life_context_service.py` keeps fact revisions, confidence/source, decisions, outcomes and events. Context is retrieved by relevant domains. Dynamic facts have a 120-day confidence decay step/reconfirmation behavior.
- `chat_memory_service.py` optionally embeds past turns with OpenAI, stores vectors as JSON on chat rows, and ranks in Python by cosine similarity (no pgvector). Embedding availability depends on the OpenAI key separately from prose opt-in; failures degrade to no semantic retrieval.
- Supporting services provide recurring-life-pattern correlation, personalization scores, adaptive onboarding follow-ups, important-date check-ins, and prediction feedback.
- MyLifeTwin exposes editable/removable remembered facts; LifeTimeline displays recorded events.

## Confirmed constraints and follow-up risks

1. Password reset is unauthenticated and verifies no email ownership before changing the password and issuing a token (`api/v1/auth.py`, `services/auth_service.py`). This is a concrete security gap.
2. OTP is a development flow that returns its code; OAuth returns 501. Source defaults include development JWT/encryption keys and permissive CORS. Deployment configuration was not inspected.
3. Frontend `API_BASE_URL` is hard-coded to a temporary ngrok tunnel in `src/config/env.ts`.
4. `ALL_FEATURES_FREE` is true in frontend and backend source defaults. Existing tiers are free < insight < strategy. Coordinate both sides when enabling gating.
5. Razorpay simulates successful checkout if keys are absent; production checkout/webhook behavior needs end-to-end validation before launch.
6. Geocoding uses a backend Google Places proxy when configured. Offline unknown places can silently resolve to New Delhi. Time-zone offsets are fixed/estimated and do not model historical daylight saving; this can affect birth calculations.
7. Potential cross-account cache issue: the complete-kundali API memo is keyed only by language; logout clears Zustand caches but does not visibly call `invalidateKundaliMemo`. Reproduce and address before relying on account-switch isolation.
8. Large concentration of logic in templates, prediction_service, chat router and API adapters makes narrow regression coverage important when changing these areas.

## Verification and development

- Frontend commands: `npm start`, `npm run web`, `npm run android`, `npm run ios`. No frontend test/lint script is declared.
- TypeScript baseline: `node_modules/.bin/tsc.cmd --noEmit` passed on 2026-09-23.
- Backend command: from `backend`, `.venv/Scripts/python.exe -m pytest -q`. Initial sandbox execution could not start the interpreter outside the workspace; rerun used approved escalation.
- Backend baseline: all 976 tests passed in 121.47 seconds on 2026-09-23.
- Tests configure their own SQLite `test_kundaliai.db`, disable real AI keys/prose, and enable tier gating to exercise quotas; separate tests cover the all-free bypass.
- The README recommends Python 3.11 for the Windows pyswisseph environment. Existing virtual environment points to a user-local Python 3.11 installation.
- EAS has development/preview/production channels and app-version runtime policy. No native ios/android directories are tracked in this checkout.
- This review did not launch device/browser UI or exercise paid/live external services. Test success does not establish live provider availability or visual correctness.

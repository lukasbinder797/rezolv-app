# REZOLV — Platformă B2B SaaS & Marketplace pentru Meșteri și Service-uri Auto (Pilot Sibiu)

**REZOLV** este o platformă B2B SaaS de programări și estimări (model tip *Mero.ro* pentru instalații, reparații casnice și mecanică auto în Sibiu & împrejurimi). Clienții rezervă gratuit, iar meșterii verifică CUI-ul (ANAF/ONRC Modulo-11) și plătesc un abonament fix de **39 EUR/lună** cu **0% comision per lucrare**, beneficiind de calendar mobil pentru teren („Dirty Hands” UI >= 58px) și remindere automate SMS la **24h** și **2h** înainte de programare.

---

## 1. Pornire Rapidă (Development & Staging)

```bash
# 1. Pornire mediu Demo / Development (API pe :8787 + Frontend pe :5173)
./run-demo.sh

# 2. Pornire mediu Staging izolat (DB separată + port :8788)
./run-staging.sh

# 3. Rulare suită completă de teste automate (157 teste: Unit, Smoke, Regression, Auth Matrix, AI Evals, 100 A/B Simulations)
python3 -m unittest discover -s backend/tests -v
```

### Conturi Demo Pre-populate (Parola: `Demo1234`)
- **Client Sibiu**: `client@rezolv.ro`
- **Meșter (Instalații Sanitare)**: `mester@rezolv.ro` (Binder Lukas — `LUKAS INSTAL S.R.L.`)
- **Meșter (Mecanică Auto & ITP)**: `auto@rezolv.ro` (Mihai Rădulescu — `AUTOSIB SERVICE S.R.L.`)
- **Super-Admin & SRE Cockpit**: `admin@rezolv.ro`

---

## 2. Arhitectura Proiectului

```text
rezolv app/
├── .github/workflows/ci-cd.yml      # Pipeline CI/CD (Unit, Smoke, Regression, AI Evals, Audit, Build, Backup Test)
├── backend/
│   ├── rezolv/
│   │   ├── config.py                # Configurații env, Spend Caps, SSL/HSTS, SPF/DKIM/DMARC, rotație chei
│   │   ├── core.py                  # PBKDF2-SHA256, tokenuri HMAC cu zero-downtime key rotation, Rate Limiter
│   │   ├── db.py                    # SQLite WAL, Foreign Keys, migrări idempotente
│   │   ├── seed.py                  # Seed Sibiu (12 categorii, meșteri verificabili CUI, sloturi & SMS queue)
│   │   ├── services.py              # Business logic, Booking state-machine, GDPR Export/Delete, Email Verify
│   │   ├── ai_evals.py              # AI Guardrails: anti-Prompt Injection, Token Budget, Circuit Breaker, Golden Evals
│   │   ├── observability.py         # Logging JSON structurat, Error Tracking, Alerte, p50/p95/p99, TTLCache + ETag, Spend Caps
│   │   ├── email_service.py         # Outbox tranzacțional + semnătură criptografică DKIM + verificare SPF/DMARC
│   │   ├── backup.py                # Online SQLite Backup API + SHA-256 manifest + Live Restore Verification
│   │   ├── sms.py                   # Motor SMS Anti No-Show (Twilio 24h & 2h reminders)
│   │   ├── verification.py          # Validare matematică CUI (Modulo-11 Romania) + registru ONRC/ANAF
│   │   └── server.py                # HTTP REST API, HSTS/CSP, ETag/304 Caching, SEO/AEO (/robots.txt, /sitemap.xml, /llms.txt)
│   └── tests/
│       ├── test_api.py              # 31 teste de integrare API & fluxuri B2B/B2C
│       ├── test_unit.py             # 9 teste unitare pure (CUI, Luhn, HMAC key rotation, Prompt Injection, Token Budget)
│       ├── test_smoke.py            # 5 smoke tests (<2s: Health probes, SEO/AEO, Auth, Discovery)
│       ├── test_regression.py       # 9 teste de regresie (Auth pe TOATE rutele, GDPR delete, Email verify, Password reset, Spend caps, Backup/Restore)
│       ├── test_ai_evals.py         # 3 suite AI (Golden Dataset 12 categorii >=85%, Red-Team Prompt Injection 100%, Fallback & Overflow)
│       └── test_100_ab_simulations.py # 100 simulări A/B & interacțiuni Client-Meșter-Admin (toate butoanele, fluxurile și edge-case-urile)
├── frontend/
│   ├── index.html                   # Meta SEO, OpenGraph, Twitter Cards, JSON-LD Schema.org, Favicon SVG
│   ├── public/                      # favicon.svg, og-image.svg, robots.txt, sitemap.xml, llms.txt, manifest.webmanifest
│   └── src/
│       ├── api.ts                   # Client API cu detecție Rețea Lentă (>1.8s), Offline, Timeout (12s) și raportare erori 500
│       ├── App.tsx                  # Aplicația principală (Client, Meșter, Super-Admin) + accesibilitate WCAG 2.1 AA
│       └── components/
│           ├── SuperAdminDashboard.tsx       # White-Glove Onboarding, Unit Economics, SMS Queue, SRE/FinOps/Backup/AI Cockpit
│           └── ProductionComplianceSuite.tsx # Cookie Consent GDPR, Privacy & Terms, Verificare Email, Resetare Parolă, Ștergere Cont, 404/500 Error Boundary
├── scripts/
│   ├── audit_deps.py                # Audit vulnerabilități (npm audit), scanare secrete în cod, rotație chei HMAC
│   ├── backup_restore.py            # CLI pentru backup bază de date și testare reală a restaurării
│   ├── deploy_and_rollback.sh       # Script atomic de deploy cu snapshot pre-deploy, healthcheck și rollback automat
│   └── uptime_monitor.py            # Probe sintetic de uptime (/api/health/ready) cu alertare webhook
├── Caddyfile                        # Configurație Custom Domain (rezolv.ro + staging.rezolv.ro), SSL automat Let's Encrypt, HSTS, Gzip/Zstd
├── dns_email_auth.zone              # Înregistrări DNS pregătite pentru SPF, DKIM, DMARC și CAA
├── .env.example                     # Template variabile de mediu (fără secrete în repo)
└── .env.staging.example             # Template variabile de mediu pentru Staging
```

---

## 3. Runbook Operațional (Comenzi Esențiale)

### A. Teste Automate & Evaluări AI
```bash
# Toate testele (157 teste)
python3 -m unittest discover -s backend/tests -v

# Doar cele 100 de simulări A/B & interacțiuni Client-Meșter
python3 -m unittest backend.tests.test_100_ab_simulations -v

# Doar Smoke Tests
python3 -m unittest backend.tests.test_smoke -v

# Doar AI Evals & Prompt Injection Red-Team
python3 -m unittest backend.tests.test_ai_evals -v
```

### B. Backup Bază de Date & Testare Reală a Restaurării
```bash
# Creează un snapshot atomic cu verificare SHA-256
python3 scripts/backup_restore.py backup --tag manual

# Listează toate backup-urile disponibile
python3 scripts/backup_restore.py list

# Creează un backup și îl restaurează într-un sandbox izolat, rulând PRAGMA integrity_check & foreign_key_check
python3 scripts/backup_restore.py verify-restore
```

### C. Audit de Securitate, Secrete & Rotație Chei Criptografice
```bash
# Rulează scanarea de secrete în cod + npm audit
python3 scripts/audit_deps.py

# Rotează cheia HMAC (backend/data/secret.key) fără downtime (păstrează cheia anterioară în secret.key.prev)
python3 scripts/audit_deps.py --rotate-keys
```

### D. Deploy Atomic & Plan de Rollback
```bash
# Dry-run complet (verifică teste, audit, backup și build frontend)
bash scripts/deploy_and_rollback.sh --dry-run

# Deploy de producție cu healthcheck automat și rollback în caz de eroare
bash scripts/deploy_and_rollback.sh

# Rollback manual imediat la ultimul snapshot valid (cod + baza de date)
bash scripts/deploy_and_rollback.sh --rollback
```

### E. Uptime Monitoring & Health Probes
- `GET /api/health` — Status general și versiune.
- `GET /api/health/live` — Liveness probe (procesul Python răspunde).
- `GET /api/health/ready` — Readiness probe (verifică conexiunea SQLite + latența DB în ms).
```bash
# Rulare verificare sintetică de uptime
python3 scripts/uptime_monitor.py --url http://127.0.0.1:8787 --once
```

---

## 4. Checklist Complet de Producție (39 / 39 Implementate & Verificate)

| # | Cerință | Implementare în REZOLV |
|---|---|---|
| 1 | **CI/CD** | [`.github/workflows/ci-cd.yml`](.github/workflows/ci-cd.yml) — rulează audit, unit, smoke, regression, AI evals, backup/restore test și build frontend la fiecare push/PR. |
| 2 | **Unit Tests** | [`backend/tests/test_unit.py`](backend/tests/test_unit.py) — CUI Modulo-11, Luhn, rotație chei HMAC, anti-Prompt Injection, Token Budget, TTLCache/ETag. |
| 3 | **Smoke Tests** | [`backend/tests/test_smoke.py`](backend/tests/test_smoke.py) — Health probes, SEO/AEO endpoints, autentificare și catalog în <2s. |
| 4 | **Regression Tests** | [`backend/tests/test_regression.py`](backend/tests/test_regression.py) — Matricea de autentificare pe toate rutele, GDPR delete, verificare email, resetare parolă, spend caps. |
| 5 | **SEO & AEO** | `/robots.txt`, `/sitemap.xml`, `/llms.txt`, `/api/seo/structured-data` (JSON-LD `LocalBusiness`, `Service`, `FAQPage`) în [`backend/rezolv/server.py`](backend/rezolv/server.py) și [`frontend/index.html`](frontend/index.html). |
| 6 | **Alerting** | `trigger_alert()` în [`backend/rezolv/observability.py`](backend/rezolv/observability.py) cu deduplicare, persistență în `system_alerts` și webhook extern opțional. |
| 7 | **Performance Monitoring** | `record_request_metric()` și `compute_performance_stats()` (latență `p50`, `p95`, `p99`, slow requests >500ms) + header `X-Response-Time-Ms`. |
| 8 | **Analytics** | Unit economics (MRR, ARR, LTV:CAC), pâlnie conversie estimări, stickiness DAU/WAU și rata anti no-show în `/api/admin/overview`. |
| 9 | **Check Auth on Every Endpoint** | Verificat automat prin `test_01_auth_enforced_on_every_protected_endpoint` în [`backend/tests/test_regression.py`](backend/tests/test_regression.py). |
| 10 | **Dependency Audit** | [`scripts/audit_deps.py`](scripts/audit_deps.py) — zero dependențe externe în backend (stdlib pur) + `npm audit` pe frontend (0 vulnerabilități). |
| 11 | **Multiple Devices** | Responsive CSS (`320px` mobil, `768px` tabletă, `1280px` desktop), safe-area insets iOS și butoane >=58px pentru meșteri pe teren. |
| 12 | **Slow Networks** | [`frontend/src/api.ts`](frontend/src/api.ts) emite evenimente `rezolv:network-status` la cereri >1.8s sau offline, afișând bannerul galben non-intruziv în UI. |
| 13 | **Spend Caps & Billing Alerts** | `check_and_record_spend()` blochează depășirile pentru `MONTHLY_SPEND_CAP_EUR`, `DAILY_SMS_CAP`, `DAILY_AI_CALLS_CAP` și emite alerte la 50%, 80%, 100%. |
| 14 | **Back Up Your Database** | [`backend/rezolv/backup.py`](backend/rezolv/backup.py) — snapshot online SQLite cu manifest SHA-256 și politică de retenție. |
| 15 | **Actually Test a Restore** | `verify_backup_and_restore()` restaurează backup-ul într-un fișier temporar izolat și validează `PRAGMA integrity_check` + `foreign_key_check` + număr rânduri. |
| 16 | **Rollback Plan for Bad Deploys** | [`scripts/deploy_and_rollback.sh`](scripts/deploy_and_rollback.sh) salvează SHA-ul git și baza de date înainte de deploy și face rollback automat dacă `/api/health/ready` eșuează. |
| 17 | **Keep Secrets Out of Repo** | [`.gitignore`](.gitignore), [`.env.example`](.env.example) și scanare automată de secrete în [`scripts/audit_deps.py`](scripts/audit_deps.py). |
| 18 | **Rotate Any Keys That Leaked** | `rotate_secret()` în [`backend/rezolv/core.py`](backend/rezolv/core.py) cu suport dual-key (`secret.key` + `secret.key.prev`) pentru rotație fără invalidarea bruscă a sesiunilor. |
| 19 | **Rate Limiting** | Sliding-window rate limiter per IP + rută (`auth`, `ai`, `write`, `default`) cu răspuns `429` și header standard `Retry-After`. |
| 20 | **Error Tracking** | Tabelul `error_logs`, `capture_error()` în backend și endpointul `POST /api/errors/report` conectat la `AppErrorBoundary` și `window.onerror` din frontend. |
| 21 | **Logging** | `log_structured()` emite JSON structurat cu `request_id`, metodă, cale, status, durată (ms) și redactare automată a câmpurilor sensibile. |
| 22 | **Uptime Monitoring** | [`scripts/uptime_monitor.py`](scripts/uptime_monitor.py) + probele `/api/health/live` și `/api/health/ready`. |
| 23 | **Staging Environment** | [`.env.staging.example`](.env.staging.example) și [`run-staging.sh`](run-staging.sh) cu bază de date izolată (`rezolv_staging.db`) și banner vizual `STAGING`. |
| 24 | **Custom Domain & SSL** | [`Caddyfile`](Caddyfile) pentru `rezolv.ro`, `www.rezolv.ro` și `staging.rezolv.ro` cu TLS 1.3 automat și header `Strict-Transport-Security`. |
| 25 | **Configure Email Auth (SPF/DKIM/DMARC)** | [`dns_email_auth.zone`](dns_email_auth.zone) + semnare criptografică `DKIM-Signature` (`rsa-sha256`) și verificare statut în [`backend/rezolv/email_service.py`](backend/rezolv/email_service.py). |
| 26 | **Real 404, 500, Empty, and Loading States** | Pagina 404 dedicată, `AppErrorBoundary` pentru 500, stări Empty și Loading în aplicație + răspunsuri JSON 404/500 curate în API. |
| 27 | **Write Evals** | [`backend/rezolv/ai_evals.py`](backend/rezolv/ai_evals.py) — Golden Dataset cu 16 cazuri pe toate cele 12 categorii din Sibiu (acuratețe 100%). |
| 28 | **Test for Prompt Injection** | `detect_prompt_injection()` blochează încercările de jailbreak, system prompt leak, SQLi/XSS în promptul de triaj AI (10/10 blocate în teste). |
| 29 | **Fallback When Model API Goes Down** | Circuit breaker în `ai_recommend()` care comută automat și transparent pe motorul determinist local dacă API-ul LLM extern dă timeout sau eroare. |
| 30 | **Handle Token Limits & Context Overflow** | `estimate_tokens()` și `truncate_to_token_budget()` trunchiază în siguranță descrierile foarte lungi la bugetul de tokeni configurat, cu indicator `context_truncated: true`. |
| 31 | **Make It Accessible** | Link „Sari la conținutul principal”, etichete ARIA (`role="dialog"`, `aria-live="polite"`), navigare cu tastatura (`Escape`, `:focus-visible`) și suport `prefers-reduced-motion`. |
| 32 | **Privacy Policy & Terms** | Endpointuri `/api/legal/privacy` și `/api/legal/terms` + modal interactiv complet în [`frontend/src/components/ProductionComplianceSuite.tsx`](frontend/src/components/ProductionComplianceSuite.tsx). |
| 33 | **Cookie Consent** | Banner GDPR ne-intruziv cu opțiuni granulare (*Strict Necesare*, *Analitice*, *Marketing*) salvate atât în `localStorage`, cât și în baza de date (`POST /api/legal/cookie-consent`). |
| 34 | **Let Users Delete Account & Data** | Dreptul la uitare GDPR (`DELETE /api/me` și `POST /api/me/delete` cu verificare parolă) + portabilitatea datelor (`GET /api/me/export`) direct din ecranul Profil. |
| 35 | **Make Sure Password Reset Works** | Flux end-to-end: `POST /api/auth/password-reset` -> email semnat DKIM în outbox -> `POST /api/auth/password-reset/confirm` -> invalidare sesiuni vechi + modal UI dedicat. |
| 36 | **Make Sure Email Verification Works** | Flux end-to-end: `POST /api/auth/verify-email/send` -> `POST /api/auth/verify-email/confirm` -> marchează `email_verified = 1` + banner interactiv în UI. |
| 37 | **Add OG Images & Favicon** | [`frontend/public/favicon.svg`](frontend/public/favicon.svg), [`frontend/public/og-image.svg`](frontend/public/og-image.svg), [`frontend/public/manifest.webmanifest`](frontend/public/manifest.webmanifest) și taguri OpenGraph/Twitter în `index.html`. |
| 38 | **Optimize Images** | Compresie automată pe client în Canvas (`max 960px`, JPEG `0.78`) înainte de upload + `loading="lazy"` și `decoding="async"` pe imaginile din catalog. |
| 39 | **Set Up Caching** | `TTLCache` în memorie cu ETag SHA-256 și răspuns `304 Not Modified` pentru `/api/categories` și `/api/professionals`, invalidat automat la orice modificare a catalogului. |

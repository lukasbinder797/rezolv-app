import { createElement, useCallback, useEffect, useState } from "react"
import {
  api,
  ApiFailure,
  compressImage,
  session,
  type ApiBooking,
  type ApiCalendarDay,
  type ApiPro,
  type ApiQuickSlot,
  type ApiService,
  type ApiUser,
} from "./api"
import { ProB2BCalendar } from "./components/ProB2BCalendar"
import {
  AccountSecurityAndGdprCard,
  AppErrorBoundary,
  CookieConsentBanner,
  LegalModal,
  NetworkStatusBanner,
  NotFoundScreen,
  PasswordResetModal,
} from "./components/ProductionComplianceSuite"
import { SuperAdminDashboard } from "./components/SuperAdminDashboard"

type Role = "client" | "pro"
type ClientTab = "home" | "search" | "bookings" | "profile"
type ProTab = "dashboard" | "services" | "subscription" | "profile"
type Service = [string, string, string, string]
type Professional = ApiPro
type OfferedService = ApiService
type DialogState = {
  title: string
  message: string
  confirmLabel?: string
  onConfirm?: () => void
}

const A = "/assets"

function assetUrl(file: string) {
  const map = typeof window !== "undefined" ? (window as any).__REZOLV_ASSET_MAP__ : undefined
  return (map && map[file]) || `${A}/${file}`
}

const categories: Service[] = [
  ["Instalații Sanitare", "80 – 350 RON", "cat-instalatii-sanitare.svg", "blue"],
  ["Instalații Electrice", "100 – 450 RON", "cat-instalatii-electrice.svg", "gold"],
  ["Mecanică Auto", "120 – 700 RON", "cat-mecanica-auto.svg", "blue"],
  ["Vulcanizare Mobilă", "80 – 250 RON", "cat-vulcanizare-mobila.svg", "green"],
  ["Climatizare & Termice", "150 – 600 RON", "cat-climatizare-termice.svg", "blue"],
  ["Reparații Electrocasnice", "90 – 300 RON", "cat-reparatii-electrocasnice.svg", "green"],
  ["Zugrăveli & Finisaje", "25 – 60 RON/mp", "cat-zugraveli-finisaje.svg", "coral"],
  ["Zidărie & Faianțare", "50 – 120 RON/mp", "cat-zidarie-faiantare.svg", "gold"],
  ["Montaj Mobilă", "100 – 400 RON", "cat-montaj-mobila.svg", "blue"],
  ["Lăcătuș", "100 – 280 RON", "cat-lacatus.svg", "green"],
  ["Acoperișuri & Exterioare", "200 – 1500 RON", "cat-acoperisuri-exterioare.svg", "coral"],
  ["Curățenie", "150 – 450 RON", "cat-curatenie.svg", "gold"],
]

const navIcons = {
  home: "61a6c.svg",
  search: "91214.svg",
  bookings: "c1dcb.svg",
  profile: "0ec89.svg",
  dashboard: "9f829.svg",
  services: "e75a8.svg",
  subscription: "843a4.svg",
}

function Pressable({
  children,
  className = "",
  onClick,
  disabled,
  ariaLabel,
}: {
  children: React.ReactNode
  className?: string
  onClick?: () => void
  disabled?: boolean
  ariaLabel?: string
}) {
  return (
    <div
      aria-disabled={disabled}
      aria-label={ariaLabel}
      className={`pressable ${disabled ? "disabled" : ""} ${className}`}
      onClick={disabled ? undefined : onClick}
      onKeyDown={(event) => {
        if (!disabled && (event.key === "Enter" || event.key === " "))
          onClick?.()
      }}
      role="button"
      tabIndex={disabled ? -1 : 0}
    >
      {children}
    </div>
  )
}

function Field({
  value,
  onChange,
  placeholder,
  type = "text",
  multiline = false,
}: {
  value: string
  onChange: (value: string) => void
  placeholder: string
  type?: string
  multiline?: boolean
}) {
  return createElement(multiline ? "textarea" : "input", {
    className: `field ${multiline ? "textarea" : ""}`,
    onChange: (
      event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>,
    ) => onChange(event.target.value),
    placeholder,
    type,
    value,
  })
}

function PhotoInput({
  onSelect,
}: {
  onSelect: (files: FileList | null) => void
}) {
  return createElement("input", {
    accept: "image/*",
    "aria-label": "Atașează fotografii",
    className: "visually-hidden",
    multiple: true,
    onChange: (event: React.ChangeEvent<HTMLInputElement>) =>
      onSelect(event.target.files),
    type: "file",
  })
}

function ActionDialog({
  action,
  onClose,
}: {
  action: DialogState
  onClose: () => void
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose()
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [onClose])

  const confirm = () => {
    onClose()
    action.onConfirm?.()
  }

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true">
      <div className="modal action-dialog">
        <div className="modal-handle" />
        <div className="modal-title">{action.title}</div>
        <p>{action.message}</p>
        {action.confirmLabel && (
          <Pressable className="primary-button" onClick={confirm}>
            {action.confirmLabel}
          </Pressable>
        )}
        <Pressable className="modal-later" onClick={onClose}>
          {action.confirmLabel ? "Anulează" : "Închide"}
        </Pressable>
      </div>
    </div>
  )
}

function Brand() {
  return (
    <div className="brand">
      <div className="brand-mark">
        <img alt="REZOLV Logo" src={assetUrl("rezolv-logo.png")} />
      </div>
      <div>
        <div className="brand-name">rezolv</div>
        <div className="brand-tagline">SERVICII & MEȘTERI • SIBIU</div>
      </div>
    </div>
  )
}

function Login({ onAuth }: { onAuth: (user: ApiUser) => void }) {
  const [role, setRole] = useState<Role>("client")
  const [mode, setMode] = useState<"login" | "register">("login")
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [name, setName] = useState("")
  const [company, setCompany] = useState("")
  const [cui, setCui] = useState("")
  const [reveal, setReveal] = useState(false)
  const [busy, setBusy] = useState(false)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const [error, setError] = useState("")
  const [dialog, setDialog] = useState<DialogState | null>(null)
  const [resetOpen, setResetOpen] = useState(false)
  const [legalDoc, setLegalDoc] = useState<"privacy" | "terms" | null>(null)

  const submit = async () => {
    if (busy) return
    setBusy(true)
    setError("")
    setFieldErrors({})
    try {
      const res =
        mode === "login"
          ? await api.login(email.trim(), password, role)
          : await api.register({
              role,
              name,
              email: email.trim(),
              password,
              ...(role === "pro" ? { company_name: company, cui } : {}),
            })
      session.set(res.token)
      onAuth(res.user)
    } catch (e) {
      if (e instanceof ApiFailure) {
        setError(e.message)
        setFieldErrors(e.fields)
      } else setError("Eroare neașteptată. Încearcă din nou.")
    } finally {
      setBusy(false)
    }
  }

  const recover = async () => {
    try {
      const res = await api.requestReset(email.trim())
      setDialog({ title: "Verifică emailul", message: res.message })
    } catch (e) {
      setDialog({
        title: "Nu am putut trimite linkul",
        message: e instanceof ApiFailure ? e.message : "Încearcă din nou.",
      })
    }
  }

  const fieldError = (key: string) =>
    fieldErrors[key] ? <div className="field-error">{fieldErrors[key]}</div> : null

  return (
    <main className="login-screen">
      <div className="login-wrap">
        <div className="login-header">
          <Brand />
          <Pressable
            className="help"
            ariaLabel="Ajutor"
            onClick={() =>
              setDialog({
                title: "Cum te putem ajuta?",
                message:
                  "Echipa REZOLV este disponibilă de luni până vineri, între 08:00 și 20:00. Ne poți contacta la suport@rezolv.ro.",
                confirmLabel: "Trimite un email",
                onConfirm: () => {
                  window.location.href =
                    "mailto:suport@rezolv.ro?subject=Ajutor REZOLV"
                },
              })
            }
          >
            ?
          </Pressable>
        </div>

        <section className="login-intro">
          <div className="eyebrow">
            {mode === "login" ? "BINE AI VENIT" : "CREEAZĂ CONT"}
          </div>
          <div className="display-title">
            Găsește ajutorul
            <br />
            de care ai nevoie.
          </div>
          <div className="lead">
            Conectează-te pentru a continua sau creează un cont nou în câteva
            secunde.
          </div>
        </section>

        <section className="login-form">
          {mode === "register" && (
            <div className="form-group">
              <div className="label">Nume complet</div>
              <div className="input-shell">
                <span className="input-icon">
                  <Icon file="b981e.svg" />
                </span>
                <Field value={name} onChange={setName} placeholder="Prenume și nume" />
              </div>
              {fieldError("name")}
            </div>
          )}
          <div className="form-group">
            <div className="label">Adresă de email</div>
            <div className="input-shell">
              <span className="input-icon">
                <Icon file="f10a6.svg" />
              </span>
              <Field
                value={email}
                onChange={setEmail}
                placeholder="exemplu@email.ro"
              />
            </div>
            {fieldError("email")}
          </div>
          <div className="form-group">
            <div className="label-row">
              <div className="label">Parolă</div>
              {mode === "login" && (
                <Pressable
                  className="text-action"
                  onClick={() => setResetOpen(true)}
                >
                  Recuperare parolă
                </Pressable>
              )}
            </div>
            <div className="input-shell">
              <span className="input-icon">
                <Icon file="8de3e.svg" />
              </span>
              <Field
                value={password}
                onChange={setPassword}
                placeholder="Introdu parola"
                type={reveal ? "text" : "password"}
              />
              <Pressable
                ariaLabel="Arată parola"
                className="input-icon trailing"
                onClick={() => setReveal(!reveal)}
              >
                <Icon file="cb07a.svg" />
              </Pressable>
            </div>
            {fieldError("password")}
          </div>
          <div className="form-group">
            <div className="label">Tu ești...</div>
            <div className="role-switch">
              <Pressable
                className={`role-option ${role === "client" ? "active" : ""}`}
                onClick={() => setRole("client")}
              >
                <span className="role-glyph">
                  <Icon file="b981e.svg" />
                </span>{" "}
                Client
              </Pressable>
              <Pressable
                className={`role-option ${role === "pro" ? "active" : ""}`}
                onClick={() => setRole("pro")}
              >
                <span className="role-glyph">
                  <Icon file="da85b.svg" />
                </span>{" "}
                Meșter
              </Pressable>
            </div>
          </div>
          {mode === "register" && role === "pro" && (
            <>
              <div className="form-group">
                <div className="label">Denumirea firmei (SRL / PFA)</div>
                <div className="input-shell">
                  <Field
                    value={company}
                    onChange={setCompany}
                    placeholder="Ex. Instal Pro S.R.L."
                  />
                </div>
                {fieldError("company_name")}
              </div>
              <div className="form-group">
                <div className="label">CUI</div>
                <div className="input-shell">
                  <Field value={cui} onChange={setCui} placeholder="Ex. RO45612301" />
                </div>
                {fieldError("cui")}
              </div>
            </>
          )}
          {error && (
            <div className="form-error" role="alert">
              {error}
            </div>
          )}
          <Pressable
            className="primary-button login-button"
            disabled={busy}
            onClick={submit}
          >
            {busy
              ? "Se procesează..."
              : mode === "login"
                ? "Conectare"
                : "Creează contul"}{" "}
            <span aria-hidden="true">→</span>
          </Pressable>
        </section>

        <div className="login-footer">
          <div className="register-row">
            {mode === "login" ? "Nu ai cont? " : "Ai deja cont? "}
            <Pressable
              onClick={() => {
                setMode(mode === "login" ? "register" : "login")
                setError("")
                setFieldErrors({})
              }}
            >
              {mode === "login" ? "Înregistrează-te" : "Conectează-te"}
            </Pressable>
          </div>
          <small className="terms-row">
            Continuând, accepți{" "}
            <Pressable onClick={() => setLegalDoc("terms")}>
              Termenii și Condițiile
            </Pressable>{" "}
            și{" "}
            <Pressable onClick={() => setLegalDoc("privacy")}>
              Politica de Confidențialitate (GDPR)
            </Pressable>
            .
          </small>
          {!(import.meta as any).env?.VITE_HIDE_DEMO_BAR && (
            <small className="demo-hint">
              Demo: client@rezolv.ro · mester@rezolv.ro · parola Demo1234
            </small>
          )}
        </div>
      </div>
      {resetOpen && (
        <PasswordResetModal
          initialEmail={email}
          onClose={() => setResetOpen(false)}
          onSuccess={(msg) => setDialog({ title: "Parolă schimbată", message: msg })}
        />
      )}
      {legalDoc && <LegalModal kind={legalDoc} onClose={() => setLegalDoc(null)} />}
      {dialog && (
        <ActionDialog action={dialog} onClose={() => setDialog(null)} />
      )}
    </main>
  )
}

function Icon({ file }: { file: string }) {
  return <img alt="" className="icon-image" loading="lazy" decoding="async" src={assetUrl(file)} />
}

function BottomNav<T extends string>({
  items,
  active,
  onChange,
}: {
  items: [T, string, string][]
  active: T
  onChange: (tab: T) => void
}) {
  return (
    <nav className="bottom-nav">
      {items.map(([key, label, icon]) => (
        <Pressable
          className={`nav-item ${active === key ? "active" : ""}`}
          key={key}
          onClick={() => onChange(key)}
        >
          <span className="nav-icon">
            <Icon file={icon} />
          </span>
          <span>{label}</span>
          {(key === "bookings" || key === "subscription") && <i />}
        </Pressable>
      ))}
    </nav>
  )
}

function ProfileShortcut({ onClick }: { onClick: () => void }) {
  return (
    <Pressable
      ariaLabel="Deschide profilul"
      className="profile-shortcut"
      onClick={onClick}
    >
      <img alt="" src={assetUrl("ab11a.png")} />
    </Pressable>
  )
}

const STATUS_LABEL: Record<string, string> = {
  pending: "Cerere trimisă",
  estimated: "Estimare primită",
  accepted: "Slot Confirmat",
  completed: "Finalizată",
  refused: "Refuzată",
  cancelled: "Anulată",
}

function bookingIcon(category: string) {
  return categories.find(([name]) => name === category)?.[2] ?? "386c4.svg"
}

function bookingPrice(b: ApiBooking) {
  return b.quote_price ? `${b.quote_price} RON` : b.price_label
}

function BookingCard({
  booking,
  onClick,
  onAcceptEstimate,
  onDeclineEstimate,
  footer,
}: {
  booking: ApiBooking
  onClick?: () => void
  onAcceptEstimate?: (b: ApiBooking) => void
  onDeclineEstimate?: (b: ApiBooking) => void
  footer?: React.ReactNode
}) {
  const smsScheduled = (booking.sms_reminders ?? []).filter((s) => s.status === "scheduled").length
  const smsSent = (booking.sms_reminders ?? []).filter((s) => s.status === "sent" || s.status === "delivered").length

  return (
    <div className="appointment-card" onClick={onClick}>
      <div className="appointment-top">
        <div className="service-symbol">
          <Icon file={bookingIcon(booking.category)} />
        </div>
        <div className="grow">
          <strong>{booking.service_name}</strong>
          <small>
            Meșter: {booking.professional.name} • 📍 {booking.neighborhood ?? "Sibiu"}
          </small>
        </div>
        <span className={`status ${booking.status}`}>
          {STATUS_LABEL[booking.status] ?? booking.status}
        </span>
      </div>
      <div className="divider" />
      <div className="appointment-meta">
        <span className="inline-meta">
          <Icon file="c1dcb.svg" /> {booking.scheduled_for ?? booking.ago}
        </span>
        <strong>{bookingPrice(booking)}</strong>
      </div>

      {/* 3-Step Estimate Handshake: Client Offer Card */}
      {booking.status === "estimated" && (
        <div className="estimate-offer-box" onClick={(e) => e.stopPropagation()}>
          <div className="estimate-offer-head">
            <span>📋 Estimare Primită de la Meșter</span>
            <span>0% Comision</span>
          </div>
          <div className="estimate-offer-grid">
            <div>
              <small>Preț Estimat</small>
              <strong>{booking.quote_price} RON</strong>
            </div>
            <div>
              <small>Durată Lucrare</small>
              <strong>{booking.quote_duration ?? "1.5 ore"}</strong>
            </div>
            <div>
              <small>Slot Propunere</small>
              <strong>{booking.scheduled_for ?? "Mâine, 11:00"}</strong>
            </div>
          </div>
          {(booking.pro_notes || booking.estimate?.pro_notes) && (
            <p style={{ fontSize: 11, color: "var(--navy)", margin: "0 0 10px" }}>
              <b>Notă meșter:</b> „{booking.pro_notes ?? booking.estimate?.pro_notes}”
            </p>
          )}
          {onAcceptEstimate && (
            <div style={{ display: "grid", gap: 8 }}>
              <Pressable
                className="primary-button field-btn-giant"
                onClick={() => onAcceptEstimate(booking)}
              >
                ✓ Acceptă Estimarea și Blochează Ora în Calendar
              </Pressable>
              {onDeclineEstimate && (
                <Pressable
                  className="outline-button compact"
                  onClick={() => onDeclineEstimate(booking)}
                >
                  Cere altă oră / Revizuiește
                </Pressable>
              )}
            </div>
          )}
        </div>
      )}

      {/* Active Twilio Anti-No-Show SMS Reminders Badge */}
      {booking.status === "accepted" && (smsSent > 0 || smsScheduled > 0) && (
        <div className="sms-pill-row">
          <span className="sms-pill sent">✓ Slot blocat în Calendar</span>
          <span className="sms-pill">
            📲 Anti No-Show SMS (24h & 2h): {smsScheduled} active / {smsSent} trimise
          </span>
        </div>
      )}

      {/* Mutual Contact Details for Client once Accepted */}
      {(booking.status === "accepted" || booking.status === "completed") && booking.professional?.phone && (
        <div
          style={{
            margin: "8px 0",
            padding: "8px 12px",
            background: "#ecfdf5",
            borderRadius: 8,
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            fontSize: 12,
            border: "1px solid #a7f3d0",
          }}
          onClick={(e) => e.stopPropagation()}
        >
          <span>
            📞 Contact meșter: <strong>{booking.professional.phone}</strong>
          </span>
          <a
            href={`tel:${booking.professional.phone.replace(/\s+/g, "")}`}
            style={{
              color: "#065f46",
              fontWeight: "bold",
              textDecoration: "none",
              padding: "4px 8px",
              background: "white",
              borderRadius: 6,
              border: "1px solid #6ee7b7",
            }}
          >
            Sună meșterul
          </a>
        </div>
      )}

      <div className="payment-note">
        <span className="inline-meta">
          <Icon file="4243a.svg" /> Plata direct la meșter la finalizare (0% comision)
        </span>
        <span>→</span>
      </div>
      {footer}
    </div>
  )
}

function ClientHome({
  user,
  bookings,
  onReview,
  onCategory,
  onProfile,
  onOpenBookings,
  onAcceptEstimate,
  onDeclineEstimate,
}: {
  user: ApiUser
  bookings: ApiBooking[]
  onReview: (booking: ApiBooking) => void
  onCategory: (name: string, price: string) => void
  onProfile: () => void
  onOpenBookings: () => void
  onAcceptEstimate: (booking: ApiBooking) => void
  onDeclineEstimate: (booking: ApiBooking) => void
}) {
  const [query, setQuery] = useState("")
  const filtered = categories.filter(([name]) =>
    name.toLowerCase().includes(query.toLowerCase()),
  )
  const reviewable = bookings.find((b) => b.can_review)
  const current =
    bookings.find((b) => b.status === "estimated") ??
    bookings.find((b) => b.status === "accepted") ??
    bookings.find((b) => b.status === "pending") ??
    bookings[0]
  const inProgress = bookings.filter(
    (b) => b.status === "estimated" || b.status === "accepted" || b.status === "pending",
  ).length

  return (
    <div className="screen-content client-home">
      <header className="app-header">
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div
            style={{
              width: 44,
              height: 44,
              borderRadius: 14,
              background: "white",
              padding: 3,
              boxShadow: "0 4px 14px rgba(2,132,199,0.18)",
              display: "grid",
              placeItems: "center",
              flexShrink: 0,
            }}
          >
            <img
              src={assetUrl("rezolv-logo.png")}
              alt="REZOLV"
              style={{ width: 38, height: 38, objectFit: "contain" }}
            />
          </div>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span
                style={{
                  font: "700 11px/14px 'Inter:Bold'",
                  color: "var(--aqua)",
                  letterSpacing: "1px",
                }}
              >
                REZOLV
              </span>
              <span
                style={{
                  fontSize: 9,
                  padding: "1px 6px",
                  background: "#e0f2fe",
                  color: "#0369a1",
                  borderRadius: 6,
                  fontWeight: 700,
                }}
              >
                PILOT SIBIU
              </span>
            </div>
            <div
              className="screen-title"
              style={{ margin: "1px 0 0", font: "18px/22px 'Inter:Bold'" }}
            >
              Bună, {user.name.split(" ")[0]}!
            </div>
            <small style={{ color: "var(--muted)", fontSize: 11 }}>
              📍 {user.neighborhood || "Hipodrom"}, Sibiu
            </small>
          </div>
        </div>
        <Pressable
          ariaLabel="Deschide profilul"
          className="avatar"
          onClick={onProfile}
        >
          <img alt={user.name} src={assetUrl("ab11a.png")} />
        </Pressable>
      </header>

      <div className="search-shell">
        <Icon file="91214.svg" />
        <Field
          value={query}
          onChange={setQuery}
          placeholder="Caută un meșter sau serviciu în Sibiu..."
        />
      </div>

      {/* Trust & Guarantee Bar */}
      <div
        style={{
          display: "flex",
          gap: 6,
          overflowX: "auto",
          padding: "4px 2px 8px",
          scrollbarWidth: "none",
        }}
      >
        <span
          style={{
            whiteSpace: "nowrap",
            fontSize: 10,
            fontWeight: "bold",
            padding: "5px 10px",
            background: "#f0fdf4",
            color: "#166534",
            borderRadius: 999,
            border: "1px solid #bbf7d0",
            display: "inline-flex",
            alignItems: "center",
            gap: 4,
          }}
        >
          🛡️ Firme Verificate CUI
        </span>
        <span
          style={{
            whiteSpace: "nowrap",
            fontSize: 10,
            fontWeight: "bold",
            padding: "5px 10px",
            background: "#eff6ff",
            color: "#1e40af",
            borderRadius: 999,
            border: "1px solid #bfdbfe",
            display: "inline-flex",
            alignItems: "center",
            gap: 4,
          }}
        >
          ⚡ 0% Comision per Lucrare
        </span>
        <span
          style={{
            whiteSpace: "nowrap",
            fontSize: 10,
            fontWeight: "bold",
            padding: "5px 10px",
            background: "#faf5ff",
            color: "#6b21a8",
            borderRadius: 999,
            border: "1px solid #e9d5ff",
            display: "inline-flex",
            alignItems: "center",
            gap: 4,
          }}
        >
          📲 SMS 24h & 2h Anti No-Show
        </span>
        <span
          style={{
            whiteSpace: "nowrap",
            fontSize: 10,
            fontWeight: "bold",
            padding: "5px 10px",
            background: "#f8fafc",
            color: "#334155",
            borderRadius: 999,
            border: "1px solid #e2e8f0",
            display: "inline-flex",
            alignItems: "center",
            gap: 4,
          }}
        >
          💳 Plată Directă la Meșter
        </span>
      </div>

      {reviewable && (
        <Pressable
          className="review-notification"
          onClick={() => onReview(reviewable)}
        >
          <div className="notification-mark">✓</div>
          <div className="grow">
            <strong>Lucrarea a fost finalizată</strong>
            <small>Spune-ne cum a fost experiența cu meșterul.</small>
          </div>
          <span>Evaluează</span>
        </Pressable>
      )}

      <section className="section-block active-section">
        <div className="section-heading">
          <div>{inProgress ? "Cereri & Estimări Active" : "Ultima programare"}</div>
          <span>
            {inProgress ? `${inProgress} în desfășurare` : "Istoric"}
          </span>
        </div>
        {current ? (
          <BookingCard
            booking={current}
            onClick={onOpenBookings}
            onAcceptEstimate={onAcceptEstimate}
            onDeclineEstimate={onDeclineEstimate}
          />
        ) : (
          <div className="list-note">
            Nu ai programări încă. Alege o categorie pentru a găsi un meșter în Sibiu.
          </div>
        )}
      </section>

      <section className="section-block category-section">
        <div className="section-heading">
          <div>Toate Categoriile</div>
          <small>12 servicii disponibile</small>
        </div>
        <div className="category-grid">
          {filtered.map(([name, price, icon, color]) => (
            <Pressable
              className="category-card"
              key={name}
              onClick={() => onCategory(name, price)}
            >
              <div className={`category-icon ${color}`}>
                <Icon file={icon} />
              </div>
              <strong>{name}</strong>
              <small>{price}</small>
            </Pressable>
          ))}
        </div>
      </section>
    </div>
  )
}

function Discovery({
  onAction,
  onBook,
}: {
  onAction: (action: DialogState) => void
  onBook: (category: string, price: string, problemText?: string, photoList?: string[], proId?: string) => void
}) {
  const popular = categories.slice(0, 4)
  const [problem, setProblem] = useState("")
  const [photos, setPhotos] = useState<string[]>([])
  const [analyzing, setAnalyzing] = useState(false)
  const [recommendation, setRecommendation] = useState<{
    category: string
    specialist: string
    reason: string
    price: string
    icon: string
    urgency: string
    stats: string
    proId?: string
  } | null>(null)

  const addPhotos = (files: FileList | null) => {
    if (!files) return
    Array.from(files)
      .slice(0, 4 - photos.length)
      .forEach((file) => {
        compressImage(file)
          .then((base64) => {
            setPhotos((current) => (current.length < 4 ? [...current, base64] : current))
          })
          .catch(() => {
            onAction({ title: "Imagine invalidă", message: "Fotografia selectată nu a putut fi procesată." })
          })
      })
  }

  const analyzeProblem = async () => {
    if (problem.trim().length < 10 || analyzing) return
    setAnalyzing(true)
    setRecommendation(null)
    try {
      const r = await api.aiRecommend(problem.trim(), photos.slice(0, 4))
      setRecommendation({
        category: r.category,
        specialist: r.professional?.name ?? "Meșter verificat",
        reason: r.reason,
        price: r.price,
        icon: bookingIcon(r.category),
        urgency: r.urgency,
        stats: r.professional
          ? `Verificat · ${r.professional.rating} din 5 · ${r.professional.jobs} lucrări`
          : "Verificat",
        proId: r.professional?.id,
      })
    } catch (e) {
      onAction({
        title: "Analiza nu a reușit",
        message: e instanceof ApiFailure ? e.message : "Încearcă din nou.",
      })
    } finally {
      setAnalyzing(false)
    }
  }

  return (
    <div className="screen-content discovery">
      <div className="hero">
        <div className="trust-pill">
          Meșteri verificați · Rezervare gratuită · Plata cash
        </div>
        <div className="hero-title">Ce ai nevoie să rezolvi?</div>
        <div className="problem-composer">
          <div className="composer-label">
            <Icon file="91214.svg" />
            <span>Descrie problema</span>
          </div>
          <Field
            multiline
            value={problem}
            onChange={setProblem}
            placeholder="Ex: Curge apă sub chiuvetă și robinetul nu se mai închide..."
          />
          {photos.length > 0 && (
            <div className="photo-previews">
              {photos.map((photo, index) => (
                <div className="photo-preview" key={photo}>
                  <img alt={`Fotografie atașată ${index + 1}`} src={photo} />
                  <Pressable
                    ariaLabel={`Șterge fotografia ${index + 1}`}
                    onClick={() =>
                      setPhotos((current) =>
                        current.filter((_, photoIndex) => photoIndex !== index),
                      )
                    }
                  >
                    ×
                  </Pressable>
                </div>
              ))}
            </div>
          )}
          <div className="composer-actions">
            <label className="photo-action">
              <PhotoInput onSelect={addPhotos} />
              <span className="camera-icon" />
              <span>
                Atașează poze
                <small>{photos.length}/4</small>
              </span>
            </label>
            <Pressable
              className="analyze-button"
              disabled={problem.trim().length < 10 || analyzing}
              onClick={analyzeProblem}
            >
              {analyzing ? (
                <>
                  <span className="spinner" /> Analizăm...
                </>
              ) : (
                <>Analizează cu AI →</>
              )}
            </Pressable>
          </div>
        </div>
        <div className="ai-card">
          <strong>Asistentul AI identifică serviciul potrivit</strong>
          <span>
            Descrierea și pozele sunt folosite doar pentru această recomandare.
          </span>
        </div>
      </div>
      {recommendation && (
        <section className="ai-result" aria-live="polite">
          <div className="result-kicker">
            <span className="ai-spark">AI</span>
            Recomandare pregătită
          </div>
          <div className="result-service">
            <div className="category-icon blue">
              <Icon file={recommendation.icon} />
            </div>
            <div className="grow">
              <small>AI-ul recomandă</small>
              <strong>{recommendation.category}</strong>
            </div>
            <span>{recommendation.urgency}</span>
          </div>
          <p>{recommendation.reason}</p>
          {photos.length > 0 && (
            <div className="photo-insight">
              <b>{photos.length} fotografii analizate</b>
              <span>Imaginile au crescut precizia recomandării.</span>
            </div>
          )}
          <div className="recommended-pro">
            <div className="avatar">
              <img alt={recommendation.specialist} src={assetUrl("ab11a.png")} />
            </div>
            <div className="grow">
              <small>Meșter recomandat</small>
              <strong>{recommendation.specialist}</strong>
              <span>{recommendation.stats}</span>
            </div>
          </div>
          <div className="result-footer">
            <strong>{recommendation.price}</strong>
            <Pressable
              className="primary-button compact"
              onClick={() =>
                onBook(
                  recommendation.category,
                  recommendation.price,
                  problem.trim(),
                  photos,
                  recommendation.proId,
                )
              }
            >
              Alege meșterul
            </Pressable>
          </div>
        </section>
      )}
      <section className="section-block">
        <div className="section-heading">
          <div>Servicii populare</div>
          <Pressable
            className="section-link"
            onClick={() =>
              onAction({
                title: "Toate serviciile",
                message:
                  "Poți explora toate cele 12 categorii din ecranul Acasă sau poți descrie direct problema asistentului AI.",
              })
            }
          >
            Vezi toate
          </Pressable>
        </div>
        <div className="popular-scroll">
          {popular.map(([name, price, icon]) => (
            <Pressable
              className="popular-card"
              key={name}
              onClick={() => onBook(name, price)}
            >
              <div className="category-icon blue">
                <Icon file={icon} />
              </div>
              <small>SERVICIU POPULAR</small>
              <strong>{name}</strong>
              <span>{price}</span>
              <b>Vezi meșterii →</b>
            </Pressable>
          ))}
        </div>
      </section>
      <section className="section-block how-section">
        <div className="section-heading">
          <div>Cum funcționează</div>
        </div>
        {[
          ["01", "Alege serviciul", "Spune-ne ce ai nevoie și când."],
          ["02", "Rezervă gratuit", "Compară prețuri și alege meșterul."],
          ["03", "Ai rezolvat", "Plătești direct după finalizarea lucrării."],
        ].map(([number, title, detail]) => (
          <div className="step-card" key={number}>
            <b>{number}</b>
            <div>
              <strong>{title}</strong>
              <small>{detail}</small>
            </div>
          </div>
        ))}
      </section>
    </div>
  )
}

function EmptyBookings({ onFind }: { onFind: () => void }) {
  return (
    <div className="screen-content simple-screen">
      <div className="simple-header">
        <span>Programările mele</span>
        <small>Istoric și programări viitoare</small>
      </div>
      <div className="empty-state">
        <div className="empty-icon">
          <Icon file="c1dcb.svg" />
          <span />
        </div>
        <strong>Nicio programare încă</strong>
        <p>Când rezervi un meșter, programarea ta va apărea aici.</p>
        <Pressable className="primary-button compact" onClick={onFind}>
          Găsește un meșter
        </Pressable>
      </div>
    </div>
  )
}

function BookingsList({
  bookings,
  loaded,
  onFind,
  onCancel,
  onReview,
  onAcceptEstimate,
  onDeclineEstimate,
}: {
  bookings: ApiBooking[]
  loaded: boolean
  onFind: () => void
  onCancel: (b: ApiBooking) => void
  onReview: (b: ApiBooking) => void
  onAcceptEstimate: (b: ApiBooking) => void
  onDeclineEstimate: (b: ApiBooking) => void
}) {
  if (loaded && bookings.length === 0)
    return <EmptyBookings onFind={onFind} />
  return (
    <div className="screen-content simple-screen">
      <div className="simple-header">
        <span>Programările mele</span>
        <small>Estimări primite, sloturi confirmate și istoric (Sibiu)</small>
      </div>
      {!loaded && <div className="list-note">Se încarcă...</div>}
      <div style={{ display: "grid", gap: 12 }}>
        {bookings.map((b) => (
          <BookingCard
            key={b.id}
            booking={b}
            onAcceptEstimate={onAcceptEstimate}
            onDeclineEstimate={onDeclineEstimate}
            footer={
              <div className="request-actions" style={{ marginTop: 12 }}>
                {b.can_review && (
                  <Pressable
                    className="primary-button compact"
                    onClick={() => onReview(b)}
                  >
                    Evaluează lucrarea
                  </Pressable>
                )}
                {(b.status === "pending" || b.status === "accepted" || b.status === "estimated") && (
                  <Pressable
                    className="outline-button compact"
                    onClick={() => onCancel(b)}
                  >
                    Anulează
                  </Pressable>
                )}
                {b.review && (
                  <small className="list-note" style={{ padding: 0 }}>
                    Ai evaluat: {"★".repeat(b.review.rating)}
                  </small>
                )}
              </div>
            }
          />
        ))}
      </div>
    </div>
  )
}

function ProfileEditModal({
  user,
  onClose,
  onSaved,
}: {
  user: ApiUser
  onClose: () => void
  onSaved: (user: ApiUser) => void
}) {
  const [name, setName] = useState(user.name)
  const [phone, setPhone] = useState(user.phone ?? "")
  const [address, setAddress] = useState(user.address ?? "")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const [fields, setFields] = useState<Record<string, string>>({})

  const save = async () => {
    setBusy(true)
    setError("")
    try {
      const res = await api.updateMe({ name, phone: phone || undefined, address: address || undefined })
      onSaved(res.user)
      onClose()
    } catch (e) {
      if (e instanceof ApiFailure) {
        setError(e.message)
        setFields(e.fields)
      }
    } finally {
      setBusy(false)
    }
  }
  const row = (label: string, key: string, value: string, set: (v: string) => void, ph: string) => (
    <>
      <div className="label">{label}</div>
      <div className="input-shell">
        <Field value={value} onChange={set} placeholder={ph} />
      </div>
      {fields[key] && <div className="field-error">{fields[key]}</div>}
    </>
  )
  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true">
      <div className="modal quote-modal">
        <div className="modal-handle" />
        <div className="modal-title">Date personale</div>
        <p>Aceste date îi ajută pe meșteri să ajungă la tine.</p>
        {row("Nume complet", "name", name, setName, "Prenume și nume")}
        {row("Telefon", "phone", phone, setPhone, "+40 7xx xxx xxx")}
        {row("Adresă", "address", address, setAddress, "Strada, număr, oraș")}
        {error && <div className="form-error">{error}</div>}
        <Pressable className="primary-button" disabled={busy} onClick={save}>
          {busy ? "Se salvează..." : "Salvează"}
        </Pressable>
        <Pressable className="modal-later" onClick={onClose}>
          Anulează
        </Pressable>
      </div>
    </div>
  )
}

function ClientProfile({
  user,
  onLogout,
  onAction,
  onUserUpdated,
}: {
  user: ApiUser
  onLogout: () => void
  onAction: (action: DialogState) => void
  onUserUpdated: (user: ApiUser) => void
}) {
  const [editing, setEditing] = useState(false)
  const [legalDoc, setLegalDoc] = useState<"privacy" | "terms" | null>(null)
  return (
    <div className="screen-content simple-screen">
      <div className="simple-header">
        <span>Profilul meu</span>
        <small>Preferințe și cont</small>
      </div>
      <div className="profile-card">
        <div className="avatar large">
          <img alt={user.name} loading="lazy" decoding="async" src={assetUrl("ab11a.png")} />
        </div>
        <strong>{user.name}</strong>
        <small>{user.email}</small>
        {user.address && <small>{user.address}</small>}
      </div>
      {["Date personale", "Adrese salvate", "Ajutor și suport"].map((item) => (
        <Pressable
          className="settings-row"
          key={item}
          onClick={() =>
            item === "Ajutor și suport"
              ? onAction({
                  title: item,
                  message:
                    "Consultă răspunsurile frecvente sau contactează echipa noastră la suport@rezolv.ro.",
                  confirmLabel: "Contactează suportul",
                  onConfirm: () => {
                    window.location.href =
                      "mailto:suport@rezolv.ro?subject=Suport client"
                  },
                })
              : setEditing(true)
          }
        >
          <span>{item}</span>
          <b>›</b>
        </Pressable>
      ))}
      <AccountSecurityAndGdprCard
        user={user}
        onUserUpdated={onUserUpdated}
        onAccountDeleted={onLogout}
        onOpenLegal={setLegalDoc}
      />
      <Pressable className="outline-button" onClick={onLogout}>
        Deconectare
      </Pressable>
      {legalDoc && <LegalModal kind={legalDoc} onClose={() => setLegalDoc(null)} />}
      {editing && (
        <ProfileEditModal
          user={user}
          onClose={() => setEditing(false)}
          onSaved={onUserUpdated}
        />
      )}
    </div>
  )
}

type BookingStep = "professionals" | "profile" | "services" | "details" | "review" | "success"

function ServiceBookingFlow({
  category,
  categoryPrice: _categoryPrice,
  initialProblem = "",
  initialPhotos = [],
  initialProId,
  user,
  onClose,
  onCreated,
}: {
  category: string
  categoryPrice: string
  initialProblem?: string
  initialPhotos?: string[]
  initialProId?: string
  user?: ApiUser
  onClose: () => void
  onCreated: () => void
}) {
  const [step, setStep] = useState<BookingStep>("professionals")
  const [selectedProfessional, setSelectedProfessional] =
    useState<Professional | null>(null)
  const [selectedService, setSelectedService] = useState<OfferedService | null>(
    null,
  )
  const [problem, setProblem] = useState(initialProblem)
  const [neighborhood, setNeighborhood] = useState(user?.neighborhood || "Hipodrom")
  const [clientAddress, setClientAddress] = useState(user?.address || "")
  const [clientPhone, setClientPhone] = useState(user?.phone || "")
  const [preferredWindow, setPreferredWindow] = useState("Mâine, 09:00–12:00")
  const [photos, setPhotos] = useState<string[]>(initialPhotos)
  const [pros, setPros] = useState<ApiPro[] | null>(null)
  const [error, setError] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const offeredServices = selectedProfessional?.services ?? []
  const sibiuZones = ["Hipodrom", "Șelimbăr", "Turnișor", "Ștrand", "Vasile Aaron", "Centru Istoric"]
  const windows = ["Urgent Azi", "Mâine, 09:00–12:00", "Mâine, 13:00–17:00"]

  useEffect(() => {
    let alive = true
    api
      .professionals(category)
      .then((r) => {
        if (!alive) return
        setPros(r.professionals)
        if (initialProId && !selectedProfessional) {
          const match = r.professionals.find((p) => p.id === initialProId)
          if (match) {
            setSelectedProfessional(match)
            if (match.services?.length) {
              setSelectedService(match.services[0])
              setStep("details")
            } else {
              setStep("services")
            }
          }
        }
      })
      .catch((e) => {
        if (!alive) return
        setPros([])
        setError(e.message)
      })
    return () => {
      alive = false
    }
  }, [category, initialProId])

  const addPhotos = (files: FileList | null) => {
    if (!files) return
    Array.from(files)
      .slice(0, 4 - photos.length)
      .forEach((file) => {
        compressImage(file)
          .then((data) =>
            setPhotos((current) =>
              current.length < 4 ? [...current, data] : current,
            ),
          )
          .catch(() => setError("Fotografia nu a putut fi încărcată."))
      })
  }

  const submitBooking = async () => {
    if (!selectedService || submitting) return
    setSubmitting(true)
    setError("")
    try {
      await api.createBooking({
        service_id: selectedService.id,
        description: problem.trim(),
        neighborhood,
        address: clientAddress.trim() || undefined,
        client_address: clientAddress.trim() || undefined,
        phone: clientPhone.trim() || undefined,
        client_phone: clientPhone.trim() || undefined,
        urgency_level: preferredWindow === "Urgent Azi" ? "urgent_today" : "normal",
        preferred_window: preferredWindow,
        scheduled_for: preferredWindow,
        photos,
      })
      onCreated()
      setStep("success")
    } catch (e) {
      setError(e instanceof ApiFailure ? e.message : "Eroare neașteptată.")
    } finally {
      setSubmitting(false)
    }
  }

  const goBack = () => {
    if (step === "profile") setStep("professionals")
    if (step === "services") setStep("professionals")
    if (step === "details") setStep("services")
    if (step === "review") setStep("details")
  }

  const selectProfessional = (professional: Professional) => {
    setSelectedProfessional(professional)
    setSelectedService(null)
    setStep("services")
  }

  const showProfile = (professional: Professional) => {
    setSelectedProfessional(professional)
    setStep("profile")
  }

  const progress =
    step === "professionals" || step === "profile"
      ? 1
      : step === "services"
        ? 2
        : step === "details"
          ? 3
          : 4

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true">
      <div className="modal booking-modal">
        <div className="booking-toolbar">
          {step !== "professionals" && step !== "success" ? (
            <Pressable
              ariaLabel="Înapoi"
              className="booking-icon-action"
              onClick={goBack}
            >
              ←
            </Pressable>
          ) : (
            <span className="booking-icon-placeholder" />
          )}
          <div className="booking-toolbar-title">
            {step === "success" ? "Cerere trimisă" : category}
          </div>
          <Pressable
            ariaLabel="Închide"
            className="booking-icon-action"
            onClick={onClose}
          >
            ×
          </Pressable>
        </div>

        {step !== "success" && (
          <div
            className="booking-progress"
            aria-label={`Pasul ${progress} din 4`}
          >
            {[1, 2, 3, 4].map((item) => (
              <i className={item <= progress ? "active" : ""} key={item} />
            ))}
          </div>
        )}

        {step === "professionals" && (
          <div className="booking-step">
            <div className="booking-heading">
              <strong>Alege meșterul potrivit</strong>
              <span>
                Profesioniști verificați pentru{" "}
                {category.toLocaleLowerCase("ro")}
              </span>
            </div>
            <div className="professional-list">
              {pros === null && (
                <div className="booking-note">Se încarcă meșterii...</div>
              )}
              {pros !== null && pros.length === 0 && (
                <div className="booking-note">
                  {error || "Momentan nu există meșteri disponibili pentru această categorie."}
                </div>
              )}
              {(pros ?? []).map((professional, index) => (
                <div className="professional-card" key={professional.id}>
                  <div
                    className={`professional-avatar avatar-tone-${(index % 3) + 1}`}
                  >
                    {professional.initials}
                    <i>✓</i>
                  </div>
                  <div className="grow">
                    <strong>{professional.name}</strong>
                    <span className="professional-rating">
                      ★ {professional.rating} · {professional.reviews} recenzii
                    </span>
                    <small>
                      {professional.distance} · {professional.experience}
                    </small>
                    <b>{professional.availability}</b>
                  </div>
                  <div className="professional-actions">
                    <Pressable
                      className="profile-link"
                      onClick={() => showProfile(professional)}
                    >
                      Profil
                    </Pressable>
                    <Pressable
                      className="choose-button"
                      onClick={() => selectProfessional(professional)}
                    >
                      Alege
                    </Pressable>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {step === "profile" && selectedProfessional && (
          <div className="booking-step">
            <div className="professional-profile">
              <div className="professional-avatar profile-avatar">
                {selectedProfessional.initials}
                <i>✓</i>
              </div>
              <strong>{selectedProfessional.name}</strong>
              <span>Specialist în {category.toLocaleLowerCase("ro")}</span>
              <div className="profile-stats">
                <div>
                  <b>{selectedProfessional.rating}</b>
                  <small>rating</small>
                </div>
                <div>
                  <b>{selectedProfessional.jobs}</b>
                  <small>lucrări</small>
                </div>
                <div>
                  <b>{selectedProfessional.experience.split(" ")[0]}</b>
                  <small>ani experiență</small>
                </div>
              </div>
            </div>
            <div className="profile-detail-card">
              <strong>Despre meșter</strong>
              <p>
                Profesionist verificat de echipa REZOLV, cu identitatea și
                calificările validate. Oferă deviz clar înainte de începerea
                lucrării și garanție pentru serviciile efectuate.
              </p>
              <div className="verified-row">
                <span>✓ Identitate verificată</span>
                <span>✓ Calificări validate</span>
                <span>✓ {selectedProfessional.reviews} recenzii reale</span>
              </div>
            </div>
            <Pressable
              className="primary-button booking-primary"
              onClick={() => selectProfessional(selectedProfessional)}
            >
              Alege acest meșter
            </Pressable>
          </div>
        )}

        {step === "services" && selectedProfessional && (
          <div className="booking-step">
            <div className="booking-heading">
              <strong>Alege serviciul</strong>
              <span>Servicii oferite de {selectedProfessional.name}</span>
            </div>
            <div className="selected-pro-strip">
              <div className="professional-avatar small-avatar">
                {selectedProfessional.initials}
              </div>
              <div className="grow">
                <strong>{selectedProfessional.name}</strong>
                <span>
                  ★ {selectedProfessional.rating} ·{" "}
                  {selectedProfessional.availability}
                </span>
              </div>
              <Pressable
                className="profile-link"
                onClick={() => setStep("profile")}
              >
                Profil
              </Pressable>
            </div>
            <div className="offered-services">
              {offeredServices.map((service) => (
                <Pressable
                  className={`offered-service ${
                    selectedService?.name === service.name ? "selected" : ""
                  }`}
                  key={service.name}
                  onClick={() => setSelectedService(service)}
                >
                  <span className="service-radio" />
                  <div className="grow">
                    <strong>{service.name}</strong>
                    <small>{service.duration}</small>
                  </div>
                  <b>{service.price}</b>
                </Pressable>
              ))}
            </div>
            <Pressable
              className="primary-button booking-primary"
              disabled={!selectedService}
              onClick={() => setStep("details")}
            >
              Continuă
            </Pressable>
          </div>
        )}

        {step === "details" && selectedProfessional && selectedService && (
          <div className="booking-step">
            <div className="booking-heading">
              <strong>Descrie problema</strong>
              <span>Detaliile îl ajută pe meșter să vină pregătit</span>
            </div>
            <div className="booking-selection-summary">
              <div className="category-icon blue">
                <Icon
                  file={
                    categories.find(([name]) => name === category)?.[2] ??
                    "386c4.svg"
                  }
                />
              </div>
              <div className="grow">
                <small>{selectedProfessional.name}</small>
                <strong>{selectedService.name}</strong>
                <span>{selectedService.price}</span>
              </div>
            </div>
            <div className="booking-field-label">Cartierul din Sibiu</div>
            <div className="chip-row">
              {sibiuZones.map((z) => (
                <Pressable
                  key={z}
                  className={`quick-chip ${neighborhood === z ? "active" : ""}`}
                  onClick={() => setNeighborhood(z)}
                >
                  📍 {z}
                </Pressable>
              ))}
            </div>
            <div className="booking-field-label" style={{ marginTop: 8 }}>
              Adresa exactă în Sibiu (stradă, nr., bloc, ap.)
            </div>
            <Field
              value={clientAddress}
              onChange={setClientAddress}
              placeholder="Ex: Str. Nicolae Bălcescu nr. 12, Sc. B, Ap. 15"
            />
            <div className="booking-field-label" style={{ marginTop: 8 }}>
              Telefon mobil (pentru remindere SMS și sosirea meșterului)
            </div>
            <Field
              value={clientPhone}
              onChange={setClientPhone}
              placeholder="Ex: +40 740 123 456"
            />
            <div className="booking-field-label" style={{ marginTop: 8 }}>
              Când preferi intervenția?
            </div>
            <div className="chip-row">
              {windows.map((w) => (
                <Pressable
                  key={w}
                  className={`quick-chip ${preferredWindow === w ? "active" : ""}`}
                  onClick={() => setPreferredWindow(w)}
                >
                  ⏰ {w}
                </Pressable>
              ))}
            </div>
            <div className="booking-field-label" style={{ marginTop: 6 }}>
              Ce trebuie rezolvat?
            </div>
            <Field
              multiline
              value={problem}
              onChange={setProblem}
              placeholder="Ex: Robinetul din bucătărie curge și nu se mai închide complet..."
            />
            <div className="booking-photo-label">
              <strong>Fotografii</strong>
              <span>Opțional · maximum 4</span>
            </div>
            {photos.length > 0 && (
              <div className="photo-previews booking-photo-previews">
                {photos.map((photo, index) => (
                  <div className="photo-preview" key={photo}>
                    <img alt={`Fotografie atașată ${index + 1}`} src={photo} />
                    <Pressable
                      ariaLabel={`Șterge fotografia ${index + 1}`}
                      onClick={() =>
                        setPhotos((current) =>
                          current.filter(
                            (_, photoIndex) => photoIndex !== index,
                          ),
                        )
                      }
                    >
                      ×
                    </Pressable>
                  </div>
                ))}
              </div>
            )}
            {photos.length < 4 && (
              <label className="booking-photo-upload">
                <PhotoInput onSelect={addPhotos} />
                <span className="camera-icon" />
                <span>
                  <strong>Adaugă fotografii</strong>
                  <small>Ajută meșterul să evalueze lucrarea</small>
                </span>
                <b>{photos.length}/4</b>
              </label>
            )}
            <Pressable
              className="primary-button booking-primary"
              disabled={problem.trim().length < 10}
              onClick={() => setStep("review")}
            >
              Verifică solicitarea
            </Pressable>
          </div>
        )}

        {step === "review" && selectedProfessional && selectedService && (
          <div className="booking-step">
            <div className="booking-heading">
              <strong>Confirmă solicitarea</strong>
              <span>Verifică detaliile înainte de trimitere</span>
            </div>
            <div className="booking-review-card">
              <div className="review-line">
                <span>Meșter</span>
                <strong>{selectedProfessional.name}</strong>
              </div>
              <div className="review-line">
                <span>Serviciu</span>
                <strong>{selectedService.name}</strong>
              </div>
              <div className="review-line">
                <span>Preț estimativ</span>
                <strong>{selectedService.price}</strong>
              </div>
              <div className="review-line">
                <span>Adresă intervenție</span>
                <strong>{clientAddress.trim() ? `${clientAddress.trim()} (${neighborhood})` : `Cartier ${neighborhood}, Sibiu`}</strong>
              </div>
              {clientPhone.trim() && (
                <div className="review-line">
                  <span>Telefon contact</span>
                  <strong>{clientPhone.trim()}</strong>
                </div>
              )}
              <div className="review-problem">
                <span>Descrierea problemei</span>
                <p>{problem}</p>
              </div>
              {photos.length > 0 && (
                <div className="review-photos">
                  {photos.map((photo, index) => (
                    <img
                      alt={`Fotografie atașată ${index + 1}`}
                      key={photo}
                      src={photo}
                    />
                  ))}
                </div>
              )}
            </div>
            {error && <div className="booking-note">{error}</div>}
            <div className="booking-note">
              Trimiterea cererii este gratuită. Meșterul va confirma prețul și
              disponibilitatea înainte de programare.
            </div>
            <Pressable
              className="primary-button booking-primary"
              disabled={submitting}
              onClick={submitBooking}
            >
              {submitting ? "Se trimite..." : "Confirmă și trimite"}
            </Pressable>
          </div>
        )}

        {step === "success" && selectedProfessional && selectedService && (
          <div className="booking-success">
            <div className="booking-success-icon">✓</div>
            <strong>Solicitarea a fost trimisă</strong>
            <p>
              {selectedProfessional.name} a primit detaliile pentru „
              {selectedService.name}” și te va contacta după ce verifică
              solicitarea.
            </p>
            <div className="success-status">
              <span>Status</span>
              <b>În așteptarea confirmării</b>
            </div>
            <Pressable
              className="primary-button booking-primary"
              onClick={onClose}
            >
              Înapoi la pagina Acasă
            </Pressable>
          </div>
        )}
      </div>
    </div>
  )
}

function ReviewModal({
  booking,
  onClose,
  onSubmit,
}: {
  booking: ApiBooking
  onClose: () => void
  onSubmit: (rating: number, comment: string) => Promise<void>
}) {
  const [rating, setRating] = useState(0)
  const [review, setReview] = useState("")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const send = async () => {
    setBusy(true)
    setError("")
    try {
      await onSubmit(rating, review)
    } catch (e) {
      setError(e instanceof ApiFailure ? e.message : "Eroare neașteptată.")
      setBusy(false)
    }
  }
  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true">
      <div className="modal">
        <div className="modal-handle" />
        <div className="modal-icon success">✓</div>
        <div className="modal-title">Cum a fost experiența ta?</div>
        <p>
          Lucrarea „{booking.service_name}” a fost finalizată. Evaluează
          serviciul primit.
        </p>
        <div className="stars" aria-label="Evaluare de la 1 la 5">
          {[1, 2, 3, 4, 5].map((star) => (
            <Pressable
              className={rating >= star ? "selected" : ""}
              key={star}
              onClick={() => setRating(star)}
            >
              ★
            </Pressable>
          ))}
        </div>
        <div className="label">Spune-ne mai multe</div>
        <Field
          multiline
          value={review}
          onChange={setReview}
          placeholder="Cum a decurs lucrarea?"
        />
        {error && <div className="form-error">{error}</div>}
        <Pressable
          className="primary-button"
          disabled={rating === 0 || busy}
          onClick={send}
        >
          {busy ? "Se trimite..." : "Trimite recenzia"}
        </Pressable>
        <Pressable className="modal-later" onClick={onClose}>
          Mai târziu
        </Pressable>
      </div>
    </div>
  )
}

function ClientApp({
  user,
  onLogout,
  onUserUpdated,
}: {
  user: ApiUser
  onLogout: () => void
  onUserUpdated: (user: ApiUser) => void
}) {
  const [tab, setTab] = useState<ClientTab>("home")
  const [bookings, setBookings] = useState<ApiBooking[]>([])
  const [loaded, setLoaded] = useState(false)
  const [review, setReview] = useState<ApiBooking | null>(null)
  const [dialog, setDialog] = useState<DialogState | null>(null)
  const [bookingCategory, setBookingCategory] = useState<{
    name: string
    price: string
    problem?: string
    photos?: string[]
    initialProId?: string
  } | null>(null)
  const openCategory = (
    name: string,
    price: string,
    problem?: string,
    photos?: string[],
    initialProId?: string,
  ) => setBookingCategory({ name, price, problem, photos, initialProId })

  const refresh = useCallback(async () => {
    try {
      setBookings((await api.bookings()).bookings)
    } catch (e) {
      if (e instanceof ApiFailure && e.status === 401) onLogout()
    } finally {
      setLoaded(true)
    }
  }, [onLogout])

  useEffect(() => {
    refresh()
    const id = window.setInterval(refresh, 15000)
    return () => window.clearInterval(id)
  }, [refresh])

  const cancel = (b: ApiBooking) =>
    setDialog({
      title: "Anulezi programarea?",
      message: `„${b.service_name}” cu ${b.professional.name} va fi anulată, iar meșterul va fi notificat.`,
      confirmLabel: "Da, anulează",
      onConfirm: async () => {
        try {
          await api.cancel(b.id)
          await refresh()
        } catch (e) {
          setDialog({
            title: "Nu am putut anula",
            message: e instanceof ApiFailure ? e.message : "Încearcă din nou.",
          })
        }
      },
    })

  const acceptEstimate = async (b: ApiBooking) => {
    try {
      const res = await api.acceptEstimate(b.id)
      await refresh()
      setDialog({
        title: "✓ Estimare Acceptată & Slot Blocat!",
        message: `Ai confirmat estimarea de ${res.booking.quote_price} RON (${res.booking.quote_duration}) pe ${res.booking.scheduled_for}. Slotul a fost blocat în calendarul meșterului și vei primi automat remindere SMS cu 24h și 2h înainte de lucrare!`,
      })
    } catch (e) {
      setDialog({
        title: "Nu am putut confirma estimarea",
        message: e instanceof ApiFailure ? e.message : "Încearcă din nou.",
      })
    }
  }

  const declineEstimate = (b: ApiBooking) =>
    setDialog({
      title: "Ceri o altă oră sau revizuire?",
      message: `Meșterul ${b.professional.name} va fi notificat să îți propună un alt interval în calendar.`,
      confirmLabel: "Solicită altă oră",
      onConfirm: async () => {
        try {
          await api.declineEstimate(b.id, "Te rog propune o altă oră disponibilă în calendar.")
          await refresh()
        } catch (e) {
          setDialog({
            title: "Eroare",
            message: e instanceof ApiFailure ? e.message : "Încearcă din nou.",
          })
        }
      },
    })

  return (
    <main className="app-shell">
      {tab === "home" && (
        <ClientHome
          user={user}
          bookings={bookings}
          onReview={setReview}
          onCategory={openCategory}
          onProfile={() => setTab("profile")}
          onOpenBookings={() => setTab("bookings")}
          onAcceptEstimate={acceptEstimate}
          onDeclineEstimate={declineEstimate}
        />
      )}
      {tab === "search" && (
        <Discovery onAction={setDialog} onBook={openCategory} />
      )}
      {tab === "bookings" && (
        <BookingsList
          bookings={bookings}
          loaded={loaded}
          onFind={() => setTab("search")}
          onCancel={cancel}
          onReview={setReview}
          onAcceptEstimate={acceptEstimate}
          onDeclineEstimate={declineEstimate}
        />
      )}
      {tab === "profile" && (
        <ClientProfile
          user={user}
          onLogout={onLogout}
          onAction={setDialog}
          onUserUpdated={onUserUpdated}
        />
      )}
      {tab !== "home" && tab !== "profile" && (
        <ProfileShortcut onClick={() => setTab("profile")} />
      )}
      <BottomNav
        active={tab}
        onChange={setTab}
        items={[
          ["home", "Acasă", navIcons.home],
          ["search", "Căutare", navIcons.search],
          ["bookings", "Programări", navIcons.bookings],
        ]}
      />
      {review && (
        <ReviewModal
          booking={review}
          onClose={() => setReview(null)}
          onSubmit={async (rating, comment) => {
            await api.review(review.id, rating, comment)
            setReview(null)
            await refresh()
            setDialog({
              title: "Recenzie trimisă",
              message:
                "Îți mulțumim. Evaluarea ta îi ajută pe ceilalți clienți să aleagă în siguranță.",
            })
          }}
        />
      )}
      {dialog && (
        <ActionDialog action={dialog} onClose={() => setDialog(null)} />
      )}
      {bookingCategory && (
        <ServiceBookingFlow
          category={bookingCategory.name}
          categoryPrice={bookingCategory.price}
          initialProblem={bookingCategory.problem}
          initialPhotos={bookingCategory.photos}
          initialProId={bookingCategory.initialProId}
          user={user}
          onClose={() => setBookingCategory(null)}
          onCreated={refresh}
        />
      )}
    </main>
  )
}

function ProHeader({
  user,
  unread = 0,
  onNotifications,
  onProfile,
}: {
  user: ApiUser
  unread?: number
  onNotifications: () => void
  onProfile?: () => void
}) {
  return (
    <header className="pro-header">
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <div
          style={{
            width: 42,
            height: 42,
            borderRadius: 13,
            background: "white",
            padding: 3,
            boxShadow: "0 4px 12px rgba(2,132,199,0.18)",
            display: "grid",
            placeItems: "center",
            flexShrink: 0,
          }}
        >
          <img
            src={assetUrl("rezolv-logo.png")}
            alt="REZOLV PRO"
            style={{ width: 36, height: 36, objectFit: "contain" }}
          />
        </div>
        <div className="grow">
          <div className="pro-name" style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
            <span>{user.name}</span>
            {user.pro?.plan === "pro" ? (
              <span style={{ fontSize: 9, padding: "2px 6px", background: "linear-gradient(135deg, #f59e0b, #d97706)", color: "white", borderRadius: 6, fontWeight: "bold" }}>
                ★ PRO 0%
              </span>
            ) : (
              <span style={{ fontSize: 9, padding: "2px 6px", background: "#e2e8f0", color: "#475569", borderRadius: 6 }}>
                ESSENTIAL
              </span>
            )}
          </div>
          <small>{user.pro?.company_name || user.pro?.headline || "Meșter Verificat Sibiu"}</small>
        </div>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <Pressable className="notification" onClick={onNotifications} ariaLabel="Notificări">
          <Icon file="a0521.svg" />
          {unread > 0 && <i />}
        </Pressable>
        <Pressable
          ariaLabel={onProfile ? "Deschide profilul" : "Profil profesional"}
          className="avatar promoted"
          onClick={onProfile}
        >
          <img alt={user.name} src={assetUrl("ab11a.png")} />
        </Pressable>
      </div>
    </header>
  )
}

function QuoteModal({
  booking,
  quickSlots,
  onClose,
  onSentEstimate,
}: {
  booking: ApiBooking
  quickSlots: ApiQuickSlot[]
  onClose: () => void
  onSentEstimate: (data: {
    price: number
    duration: string
    duration_minutes: number
    proposed_start_at?: number
    slot_label?: string
    pro_notes?: string
  }) => Promise<void>
}) {
  const [price, setPrice] = useState(String(booking.quote_price ?? 180))
  const [durationMin, setDurationMin] = useState<number>(booking.duration_minutes ?? 60)
  const [durationLabel, setDurationLabel] = useState<string>(booking.quote_duration ?? "1 oră")
  const [selectedSlot, setSelectedSlot] = useState<ApiQuickSlot | null>(quickSlots[0] ?? null)
  const [notes, setNotes] = useState(
    booking.pro_notes ?? "Include deplasarea în Sibiu și constatarea la fața locului.",
  )
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const valid = Number(price) > 0

  const durationPresets: [number, string][] = [
    [45, "45 min"],
    [60, "1 oră"],
    [90, "1.5 ore"],
    [120, "2 ore"],
    [180, "3 ore"],
  ]
  const pricePresets = [120, 150, 190, 250, 350, 450]

  const adjustPrice = (delta: number) => {
    const next = Math.max(50, (Number(price) || 150) + delta)
    setPrice(String(next))
  }

  const send = async () => {
    setBusy(true)
    setError("")
    try {
      await onSentEstimate({
        price: Number(price),
        duration: durationLabel,
        duration_minutes: durationMin,
        proposed_start_at: selectedSlot?.start_at,
        slot_label: selectedSlot?.full_label,
        pro_notes: notes.trim() || undefined,
      })
    } catch (e) {
      setError(e instanceof ApiFailure ? e.message : "Eroare neașteptată.")
      setBusy(false)
    }
  }

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true">
      <div className="modal quote-modal">
        <div className="modal-handle" />
        <div className="modal-title">Estimare Rapidă (2 Click-uri)</div>
        <p>
          Trimite estimarea către <strong>{booking.client.name}</strong> ({booking.neighborhood ?? "Sibiu"}).
          Când clientul apasă „Acceptă”, slotul se blochează automat în calendarul tău!
        </p>

        <div className="label">1. Slot Disponibil în Calendar (Pre-selectat)</div>
        <div className="chip-row">
          {quickSlots.slice(0, 6).map((slot) => (
            <Pressable
              key={slot.start_at}
              className={`quick-chip ${selectedSlot?.start_at === slot.start_at ? "active" : ""}`}
              onClick={() => setSelectedSlot(slot)}
            >
              📅 {slot.label}
            </Pressable>
          ))}
        </div>

        <div className="label">2. Durată Estimată (Atinge un buton)</div>
        <div className="chip-row">
          {durationPresets.map(([mins, lbl]) => (
            <Pressable
              key={mins}
              className={`quick-chip ${durationMin === mins ? "active" : ""}`}
              onClick={() => {
                setDurationMin(mins)
                setDurationLabel(lbl)
              }}
            >
              ⏱️ {lbl}
            </Pressable>
          ))}
        </div>

        <div className="label">3. Preț Estimat (RON • 0% comision)</div>
        <div className="chip-row" style={{ marginBottom: 8 }}>
          <Pressable className="quick-chip" onClick={() => adjustPrice(-50)}>
            −50 RON
          </Pressable>
          {pricePresets.map((p) => (
            <Pressable
              key={p}
              className={`quick-chip ${Number(price) === p ? "active" : ""}`}
              onClick={() => setPrice(String(p))}
            >
              {p} RON
            </Pressable>
          ))}
          <Pressable className="quick-chip" onClick={() => adjustPrice(50)}>
            +50 RON
          </Pressable>
        </div>
        <div className="input-shell">
          <Field
            value={price}
            onChange={setPrice}
            placeholder="Ex. 190"
            type="number"
          />
          <b>RON</b>
        </div>

        <div className="label">Notă scurtă pentru client (opțional)</div>
        <div className="input-shell">
          <Field
            value={notes}
            onChange={setNotes}
            placeholder="Ex: Include deplasarea în Șelimbăr și garnituri"
          />
        </div>

        {error && <div className="form-error">{error}</div>}
        <Pressable
          className="primary-button field-btn-giant"
          disabled={!valid || busy}
          onClick={send}
        >
          {busy ? "Se trimite estimarea + SMS..." : `✓ Trimite Estimarea (${price} RON • ${durationLabel})`}
        </Pressable>
        <Pressable className="modal-later" onClick={onClose}>
          Anulează
        </Pressable>
      </div>
    </div>
  )
}

type Dashboard = {
  week: { revenue: number; jobs: number; change_pct: number | null }
  plan: { plan: string; status: string; price_eur?: number; renews_in_days: number | null }
  pending: (ApiBooking & { photos?: string[] })[]
  schedule: ApiBooking[]
  calendar?: { days: ApiCalendarDay[]; quick_free_slots: ApiQuickSlot[] }
  verification_status: string
  unread_notifications: number
}

function ProDashboard({
  user,
  data,
  onQuote,
  onRefuse,
  onComplete,
  onAction,
  onGoServices,
  onProfile,
  onNotifications,
  onRefresh,
}: {
  user: ApiUser
  data: Dashboard | null
  onQuote: (booking: ApiBooking) => void
  onRefuse: (booking: ApiBooking) => void
  onComplete: (booking: ApiBooking) => void
  onAction: (action: DialogState) => void
  onGoServices: () => void
  onProfile: () => void
  onNotifications: () => void
  onRefresh: () => void
}) {
  const fmt = (n: number) => n.toLocaleString("ro-RO")
  const pending = data?.pending ?? []
  const planLabel =
    data?.plan.status === "trial"
      ? "Perioadă de probă (Sibiu Pilot)"
      : data?.plan.status === "past_due"
        ? "Plată restantă"
        : "Abonament B2B Activ (39 EUR/lună • 0% comision)"
  return (
    <div className="screen-content pro-dashboard">
      <ProHeader
        user={user}
        unread={data?.unread_notifications}
        onProfile={onProfile}
        onNotifications={onNotifications}
      />
      {user.pro?.verification_status !== "verified" && (
        <div className="request-update" style={{ gridColumn: "1 / -1" }}>
          {user.pro?.verification_status === "rejected"
            ? "Verificarea firmei a fost respinsă. Actualizează datele din Profil → Documente și verificări."
            : "Firma ta este în curs de verificare. Profilul va deveni public după aprobare."}
        </div>
      )}
      <section className="summary-card">
        <div className="summary-top">
          <span>
            REZUMAT SĂPTĂMÂNAL SIBIU
            <br />
            (100% ÎNCASAT DE TINE • 0% COMISION)
          </span>
          <b>
            {data?.week.change_pct == null
              ? "—"
              : `${data.week.change_pct >= 0 ? "+" : ""}${data.week.change_pct}%`}{" "}
            vs săpt.
            <br />
            trecută
          </b>
        </div>
        <div className="revenue">
          {fmt(data?.week.revenue ?? 0)} <small>RON</small>
          <span>• {data?.week.jobs ?? 0} lucrări finalizate</span>
        </div>
        <div className="plan-status">
          {planLabel}{" "}
          <b>
            {data?.plan.renews_in_days != null
              ? `Reînnoire în ${data.plan.renews_in_days} zile`
              : ""}
          </b>
        </div>
      </section>
      <section className="section-block pro-section">
        <div className="section-heading">
          <div>
            Cereri & Estimări{" "}
            <span className="count">{pending.length} Active</span>
          </div>
          <Pressable
            className="section-link aqua"
            onClick={() =>
              onAction({
                title: "Toate cererile din Sibiu",
                message: pending.length
                  ? `Ai ${pending.length} cereri în curs de ofertare sau confirmare.`
                  : "Nu ai cereri în așteptare în acest moment.",
              })
            }
          >
            Vezi toate
          </Pressable>
        </div>
        {!data && <div className="list-note">Se încarcă...</div>}
        {data && pending.length === 0 && (
          <div className="list-note">Nu ai cereri noi. Revino în curând!</div>
        )}
        {pending.map((b, i) => (
          <div className={`request-card ${i === 0 ? "featured" : ""}`} key={b.id}>
            <div className="request-state">
              <span className={b.status === "estimated" ? "muted-badge" : ""}>
                {b.status === "estimated"
                  ? "⏳ Estimare trimisă (așteaptă Accept)"
                  : b.urgency_level === "urgent_today"
                    ? "🚨 URGENT AZI • " + (b.neighborhood ?? "Sibiu")
                    : "📍 Cerere nouă • " + (b.neighborhood ?? "Sibiu")}
              </span>
              <b>{b.ago}</b>
            </div>
            <strong>{b.service_name}</strong>
            <small>
              Client: {b.client.name} • 📍 {b.client.address ?? b.neighborhood ?? "Sibiu"}
              {b.preferred_window ? ` • Interval dorit: ${b.preferred_window}` : ""}
            </small>
            <div className="client-note">
              <b>Notă client:</b> “{b.description}”
            </div>
            {b.status === "estimated" && (
              <div className="sms-pill-row">
                <span className="sms-pill sent">
                  📋 Deviz propus: {b.quote_price} RON ({b.quote_duration}) • {b.scheduled_for}
                </span>
              </div>
            )}
            {b.photos && b.photos.length > 0 && (
              <div className="review-photos">
                {b.photos.map((p, k) => (
                  <img alt={`Fotografie client ${k + 1}`} key={k} src={p} />
                ))}
              </div>
            )}
            <div className="request-actions" style={{ marginTop: 14 }}>
              <Pressable
                className="primary-button field-btn-giant"
                onClick={() => onQuote(b)}
              >
                {b.status === "estimated"
                  ? "✏️ Modifică Estimarea"
                  : "📋 Trimite Estimare (2 Click-uri)"}
              </Pressable>
              <Pressable
                className="field-btn-secondary"
                onClick={() => onRefuse(b)}
              >
                Refuză
              </Pressable>
            </div>
          </div>
        ))}
      </section>
      <div style={{ display: "grid", gap: 18 }}>
        {data?.calendar && (
          <ProB2BCalendar
            days={data.calendar.days}
            quickSlots={data.calendar.quick_free_slots}
            onRefresh={onRefresh}
            onNotice={(msg) => onAction({ title: "Calendar & SMS Actualizat", message: msg })}
            onError={(title, msg) => onAction({ title, message: msg })}
          />
        )}
        <section className="section-block schedule">
          <div className="section-heading">
            <div>Intervenții Confirmate Azi</div>
            <small>{new Date().toLocaleDateString("ro-RO", { weekday: "long", day: "numeric", month: "long" })}</small>
          </div>
          {data && data.schedule.length === 0 && (
            <div className="list-note">Nu ai lucrări programate azi.</div>
          )}
          {(data?.schedule ?? []).map((b) => {
            const done = b.status === "completed"
            return (
              <div className={`schedule-card ${done ? "green-line" : "blue-line"}`} key={b.id}>
                <b>
                  {b.time_label.split(", ").pop()}
                  <small>{done ? "FINALIZAT" : "CONFIRMAT"}</small>
                </b>
                <div className="grow">
                  <strong>
                    {b.service_name} ({b.quote_price} RON)
                  </strong>
                  <small>
                    {b.client.name} • 📍 {b.neighborhood ?? "Sibiu"}
                    {b.client.address ? ` (${b.client.address})` : ""}
                  </small>
                  {done ? (
                    <span>
                      Încasat: {b.quote_price} RON (0% comision) • Clientul poate lăsa o recenzie
                    </span>
                  ) : (
                    <>
                      <span className="schedule-actions">
                        <Pressable
                          onClick={() => {
                            if (b.client.phone)
                              window.location.href = `tel:${b.client.phone.replace(/\s/g, "")}`
                          }}
                        >
                          📞 Sună clientul
                        </Pressable>
                        <Pressable
                          onClick={() =>
                            window.open(
                              `https://www.waze.com/ul?q=${encodeURIComponent(b.client.address ?? "Sibiu")}`,
                              "_blank",
                              "noopener,noreferrer",
                            )
                          }
                        >
                          🗺️ Navigație Waze Sibiu
                        </Pressable>
                      </span>
                      <Pressable className="complete-job-button" onClick={() => onComplete(b)}>
                        ✓ Marchează ca finalizată
                      </Pressable>
                    </>
                  )}
                </div>
              </div>
            )
          })}
        </section>
      </div>
      <div className="add-service-card" style={{ gridColumn: "1 / -1" }}>
        <div className="plus-dot">+</div>
        <strong>Vrei să adaugi un tarif nou pentru Sibiu?</strong>
        <small>Configurează prețurile orientative de pornire pentru estimări rapide.</small>
        <Pressable className="primary-button compact" onClick={onGoServices}>
          Adaugă / Editează servicii
        </Pressable>
      </div>
    </div>
  )
}

function AddServiceModal({
  onClose,
  onAdd,
}: {
  onClose: () => void
  onAdd: (name: string, price: number, duration: string) => Promise<void>
}) {
  const [name, setName] = useState("")
  const [price, setPrice] = useState("")
  const [duration, setDuration] = useState("")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const valid = name.trim().length >= 3 && Number(price) > 0

  const send = async () => {
    setBusy(true)
    setError("")
    try {
      await onAdd(name.trim(), Number(price), duration.trim())
    } catch (e) {
      setError(e instanceof ApiFailure ? e.message : "Eroare neașteptată.")
      setBusy(false)
    }
  }

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true">
      <div className="modal quote-modal">
        <div className="modal-handle" />
        <div className="modal-title">Adaugă un serviciu</div>
        <p>Completează serviciul și tariful afișat clienților în profilul tău.</p>
        <div className="label">Denumirea serviciului</div>
        <div className="input-shell">
          <Field value={name} onChange={setName} placeholder="Ex. Montaj centrală termică" />
        </div>
        <div className="label">Tarif de la</div>
        <div className="input-shell">
          <Field value={price} onChange={setPrice} placeholder="Ex. 250" type="number" />
          <b>RON</b>
        </div>
        <div className="label">Durată estimată</div>
        <div className="input-shell">
          <Field value={duration} onChange={setDuration} placeholder="Ex. 2–3 ore (opțional)" />
        </div>
        {error && <div className="form-error">{error}</div>}
        <Pressable className="primary-button" disabled={!valid || busy} onClick={send}>
          {busy ? "Se publică..." : "Publică serviciul"}
        </Pressable>
        <Pressable className="modal-later" onClick={onClose}>
          Anulează
        </Pressable>
      </div>
    </div>
  )
}

type ProCategory = {
  category: string
  icon: string
  tone: string
  enabled: boolean
  price_label: string
  count: number
}

function Services({
  cats,
  onToggle,
  onAdd,
}: {
  cats: ProCategory[] | null
  onToggle: (cat: ProCategory) => void
  onAdd: () => void
}) {
  return (
    <div className="screen-content simple-screen">
      <div className="simple-header">
        <span>Serviciile mele</span>
        <small>Tarife și disponibilitate</small>
      </div>
      {cats === null && <div className="list-note">Se încarcă...</div>}
      {(cats ?? []).map((c) => (
        <Pressable className="service-row" key={c.category} onClick={() => onToggle(c)}>
          <div className={`category-icon ${c.tone}`}>
            <Icon file={c.icon} />
          </div>
          <div className="grow">
            <strong>{c.category}</strong>
            <small>
              {c.enabled
                ? `Tarif activ: ${c.price_label} • ${c.count} servicii`
                : "Serviciu inactiv"}
            </small>
          </div>
          <div className={`toggle ${c.enabled ? "on" : ""}`}>
            <i />
          </div>
        </Pressable>
      ))}
      <Pressable className="primary-button" onClick={onAdd}>
        Adaugă un serviciu
      </Pressable>
    </div>
  )
}

function Subscription({
  onAction,
  onChanged,
}: {
  onAction: (action: DialogState) => void
  onChanged: () => void
}) {
  const [sub, setSub] = useState<any>(null)
  const load = useCallback(async () => {
    try {
      setSub(await api.subscription())
    } catch (e) {
      onAction({ title: "Eroare", message: e instanceof ApiFailure ? e.message : "Încearcă din nou." })
    }
  }, [onAction])
  useEffect(() => {
    load()
  }, [load])

  const plan = sub?.plan as "essential" | "pro" | undefined
  const days = sub?.renews_in_days

  const choose = (target: "essential" | "pro") => {
    const priceLabel = target === "pro" ? "39 EUR (195 RON)" : "49 RON"
    const name = target === "pro" ? "CRM Pro Sibiu (39 EUR)" : "Start Pilot"
    const card = sub?.payment_method
    onAction({
      title: `Treci la ${name}`,
      message: card
        ? `Confirmi activarea planului ${name} pentru ${priceLabel} pe lună (0% comision per lucrare)? Plata se face cu cardul ${card.brand.toUpperCase()} •••• ${card.last4}.`
        : `Confirmi activarea planului ${name} pentru ${priceLabel} pe lună (0% comision per lucrare)?`,
      confirmLabel: "Confirmă abonamentul",
      onConfirm: async () => {
        try {
          const res = await api.checkout(target)
          setSub(res)
          onChanged()
          onAction({
            title: "Abonament B2B activat",
            message: `Planul ${name} este activ (0% comision). Factura ${res.payments[0]?.invoice_no ?? ""} a fost emisă.`,
          })
        } catch (e) {
          onAction({
            title: "Plata nu a reușit",
            message: e instanceof ApiFailure ? e.message : "Încearcă din nou.",
          })
        }
      },
    })
  }

  return (
    <div className="screen-content simple-screen subscription-screen">
      <div className="simple-header">
        <span>Abonament B2B Meșter</span>
        <small>Model SaaS (0% comision per lucrare • fără dezintermediere)</small>
      </div>
      <div className="pricing-card premium">
        <div className="promoted-ribbon">STANDARD B2B SIBIU</div>
        <div className="tier-head">
          <span>CRM PRO PROMOVAT</span>
          <b>★ 0% Comision</b>
        </div>
        <div className="price">
          39 EUR <small>/ lună (195 RON)</small>
        </div>
        <ul>
          <li>0% comision per lucrare — încasezi 100% direct de la client</li>
          <li>Calendar B2B Mobile-First cu blocare automată de slot</li>
          <li>Motor SMS Anti-No-Show (Twilio 24h & 2h înainte de lucrare)</li>
          <li>Sistem de Ofertare Flexibilă (Estimare Preț + Durată)</li>
          <li>Badge „Meșter Verificat CUI” & Prioritate în Sibiu</li>
        </ul>
        <Pressable
          className="primary-button"
          disabled={!sub || plan === "pro"}
          onClick={() => choose("pro")}
        >
          {plan === "pro" ? "Abonament 39 EUR/lună Activ" : "Activează CRM 39 EUR / lună"}
        </Pressable>
      </div>
      <div className="pricing-card">
        <div className="tier-head">
          <span>START PILOT SIBIU</span>
          <b>{plan === "essential" ? "Activ" : ""}</b>
        </div>
        <div className="price">
          49 <small>RON / lună (promoțional)</small>
        </div>
        <ul>
          <li>Calendar și cereri în cartierele din Sibiu</li>
          <li>Profil profesional verificat ONRC/ANAF</li>
          <li>0% comision pe lucrările efectuate</li>
        </ul>
        {plan === "essential" ? (
          <Pressable
            className="outline-button"
            onClick={() =>
              onAction({
                title: "Planul Start Pilot",
                message:
                  days != null
                    ? `Planul este activ și se reînnoiește în ${days} zile.`
                    : "Planul este activ.",
              })
            }
          >
            Planul actual
          </Pressable>
        ) : (
          <Pressable className="outline-button" disabled={!sub} onClick={() => choose("essential")}>
            Treci la Start Pilot
          </Pressable>
        )}
      </div>
      {sub?.payments?.length > 0 && (
        <div className="profile-detail-card">
          <strong>Istoric facturi B2B</strong>
          {sub.payments.slice(0, 5).map((p: any) => (
            <p key={p.id}>
              {p.invoice_no ?? "Eșuată"} • {p.amount_ron} RON • {p.status === "succeeded" ? "plătită" : "refuzată"}
            </p>
          ))}
        </div>
      )}
    </div>
  )
}

function ProEditModal({
  kind,
  user,
  onClose,
  onSaved,
}: {
  kind: string
  user: ApiUser
  onClose: () => void
  onSaved: (user: ApiUser) => void
}) {
  const pro = user.pro!
  const [headline, setHeadline] = useState(pro.headline ?? "")
  const [bio, setBio] = useState(pro.bio ?? "")
  const [zones, setZones] = useState(pro.zones.join(", "))
  const [hours, setHours] = useState(
    Object.entries(pro.hours)
      .map(([d, h]) => `${d}: ${h}`)
      .join("\n"),
  )
  const [company, setCompany] = useState(pro.company_name)
  const [cui, setCui] = useState(pro.cui)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")

  const save = async () => {
    setBusy(true)
    setError("")
    try {
      let res
      if (kind === "Date companie") res = await api.updateProProfile({ headline, bio })
      else if (kind === "Zone deservite")
        res = await api.updateProProfile({
          zones: zones.split(",").map((z) => z.trim()).filter(Boolean),
        })
      else if (kind === "Program de lucru")
        res = await api.updateProProfile({
          hours: Object.fromEntries(
            hours
              .split("\n")
              .map((l) => l.split(/:(.*)/s))
              .filter((p) => p[0].trim() && p[1]?.trim())
              .map((p) => [p[0].trim(), p[1].trim()]),
          ),
        })
      else res = await api.submitVerification(company, cui)
      onSaved(res.user)
      onClose()
    } catch (e) {
      setError(e instanceof ApiFailure ? Object.values(e.fields)[0] ?? e.message : "Eroare neașteptată.")
      setBusy(false)
    }
  }

  const status = {
    verified: "✓ Firmă verificată",
    pending: "În curs de verificare",
    rejected: "Verificare respinsă",
  }[pro.verification_status]

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true">
      <div className="modal quote-modal">
        <div className="modal-handle" />
        <div className="modal-title">{kind}</div>
        {kind === "Date companie" && (
          <>
            <p>
              {pro.company_name} • CUI {pro.cui}
              <br />
              {status}
            </p>
            <div className="label">Titlu profil</div>
            <div className="input-shell">
              <Field value={headline} onChange={setHeadline} placeholder="Ex. Instalații Sanitare & Termice Sibiu" />
            </div>
            <div className="label">Descriere servicii (afișată clienților)</div>
            <Field multiline value={bio} onChange={setBio} placeholder="Ce oferi, experiență, garanție..." />
          </>
        )}
        {kind === "Zone deservite" && (
          <>
            <p>Separă cartierele din Sibiu prin virgulă.</p>
            <div className="input-shell">
              <Field value={zones} onChange={setZones} placeholder="Hipodrom, Șelimbăr, Turnișor, Centru Istoric" />
            </div>
          </>
        )}
        {kind === "Program de lucru" && (
          <>
            <p>Un interval pe linie, în formatul „Zi: interval”.</p>
            <Field multiline value={hours} onChange={setHours} placeholder="Luni–Vineri: 08:00–18:00" />
          </>
        )}
        {kind === "Documente și verificări" && (
          <>
            <p>
              {status}
              {pro.verification_note ? ` — ${pro.verification_note}` : ""}
            </p>
            {pro.verification_status !== "verified" && (
              <>
                <div className="label">Denumire firmă</div>
                <div className="input-shell">
                  <Field value={company} onChange={setCompany} placeholder="Sibiu Instal Termo S.R.L." />
                </div>
                <div className="label">CUI</div>
                <div className="input-shell">
                  <Field value={cui} onChange={setCui} placeholder="RO45612301" />
                </div>
              </>
            )}
          </>
        )}
        {error && <div className="form-error">{error}</div>}
        {!(kind === "Documente și verificări" && pro.verification_status === "verified") && (
          <Pressable className="primary-button" disabled={busy} onClick={save}>
            {busy ? "Se salvează..." : kind === "Documente și verificări" ? "Retrimite la verificare" : "Salvează"}
          </Pressable>
        )}
        <Pressable className="modal-later" onClick={onClose}>
          Închide
        </Pressable>
      </div>
    </div>
  )
}

function ProProfile({
  user,
  onLogout,
  onAction,
  onNotifications,
  onUserUpdated,
}: {
  user: ApiUser
  onLogout: () => void
  onAction: (action: DialogState) => void
  onNotifications: () => void
  onUserUpdated: (user: ApiUser) => void
}) {
  const [editing, setEditing] = useState<string | null>(null)
  const [legalDoc, setLegalDoc] = useState<"privacy" | "terms" | null>(null)
  const showCard = async () => {
    try {
      const s = await api.subscription()
      const c = s.payment_method
      onAction({
        title: "Metode de plată",
        message: c
          ? `Card salvat: ${c.brand.toUpperCase()} •••• ${c.last4} (exp. ${c.exp}). Este folosit pentru abonamentul lunar B2B.`
          : "Nu ai o metodă de plată salvată. Se va adăuga la prima plată de abonament.",
      })
    } catch (e) {
      onAction({ title: "Eroare", message: e instanceof ApiFailure ? e.message : "Încearcă din nou." })
    }
  }
  return (
    <div className="screen-content simple-screen">
      <ProHeader user={user} onNotifications={onNotifications} />
      {[
        "Date companie",
        "Zone deservite",
        "Program de lucru",
        "Metode de plată",
        "Documente și verificări",
        "Ajutor și suport",
      ].map((item) => (
        <Pressable
          className="settings-row"
          key={item}
          onClick={() =>
            item === "Ajutor și suport"
              ? onAction({
                  title: item,
                  message: "Echipa REZOLV Sibiu pentru profesioniști este disponibilă la parteneri@rezolv.ro.",
                  confirmLabel: "Trimite un email",
                  onConfirm: () => {
                    window.location.href = "mailto:parteneri@rezolv.ro?subject=Suport profesionist Sibiu"
                  },
                })
              : item === "Metode de plată"
                ? showCard()
                : setEditing(item)
          }
        >
          <span>{item}</span>
          <b>›</b>
        </Pressable>
      ))}
      <AccountSecurityAndGdprCard
        user={user}
        onUserUpdated={onUserUpdated}
        onAccountDeleted={onLogout}
        onOpenLegal={setLegalDoc}
      />
      <Pressable className="outline-button" onClick={onLogout}>
        Deconectare
      </Pressable>
      {legalDoc && <LegalModal kind={legalDoc} onClose={() => setLegalDoc(null)} />}
      {editing && (
        <ProEditModal
          kind={editing}
          user={user}
          onClose={() => setEditing(null)}
          onSaved={onUserUpdated}
        />
      )}
    </div>
  )
}

function ProApp({
  user,
  onLogout,
  onUserUpdated,
}: {
  user: ApiUser
  onLogout: () => void
  onUserUpdated: (user: ApiUser) => void
}) {
  const [tab, setTab] = useState<ProTab>("dashboard")
  const [data, setData] = useState<Dashboard | null>(null)
  const [cats, setCats] = useState<ProCategory[] | null>(null)
  const [quote, setQuote] = useState<ApiBooking | null>(null)
  const [dialog, setDialog] = useState<DialogState | null>(null)
  const [addingService, setAddingService] = useState(false)

  const fail = useCallback(
    (e: unknown) => {
      if (e instanceof ApiFailure && e.status === 401) return onLogout()
      setDialog({
        title: "Ceva nu a mers",
        message: e instanceof ApiFailure ? e.message : "Încearcă din nou.",
      })
    },
    [onLogout],
  )

  const refresh = useCallback(async () => {
    try {
      setData(await api.dashboard())
    } catch (e) {
      if (e instanceof ApiFailure && e.status === 401) onLogout()
    }
  }, [onLogout])

  const loadCats = useCallback(async () => {
    try {
      setCats((await api.proCategories()).categories)
    } catch (e) {
      fail(e)
    }
  }, [fail])

  useEffect(() => {
    refresh()
    loadCats()
    const id = window.setInterval(refresh, 15000)
    return () => window.clearInterval(id)
  }, [refresh, loadCats])

  const notifications = async () => {
    try {
      const n = await api.notifications()
      setDialog({
        title: "Notificări",
        message: n.notifications.length
          ? n.notifications.slice(0, 5).map((x) => `${x.title}: ${x.body}`).join(" • ")
          : "Nu ai notificări noi în acest moment.",
      })
      await api.readNotifications()
      refresh()
    } catch (e) {
      fail(e)
    }
  }

  return (
    <main className="app-shell">
      {tab === "dashboard" && (
        <ProDashboard
          user={user}
          data={data}
          onQuote={setQuote}
          onAction={setDialog}
          onGoServices={() => setTab("services")}
          onProfile={() => setTab("profile")}
          onNotifications={notifications}
          onRefresh={refresh}
          onRefuse={(b) =>
            setDialog({
              title: "Refuzi această cerere?",
              message: "Clientul va fi informat și cererea nu mai apare în lista ta.",
              confirmLabel: "Confirmă refuzul",
              onConfirm: async () => {
                try {
                  await api.refuse(b.id)
                  await refresh()
                  setDialog({
                    title: "Cerere refuzată",
                    message: "Clientul a fost informat, iar cererea nu mai apare în lista ta.",
                  })
                } catch (e) {
                  fail(e)
                }
              },
            })
          }
          onComplete={(b) =>
            setDialog({
              title: "Ai finalizat lucrarea?",
              message:
                "Confirmă doar dacă lucrarea este încheiată. Clientul va fi notificat imediat și va putea lăsa o recenzie.",
              confirmLabel: "Da, finalizează lucrarea",
              onConfirm: async () => {
                try {
                  await api.complete(b.id)
                  await refresh()
                  setDialog({
                    title: "Lucrare finalizată",
                    message: "Clientul a fost notificat și poate lăsa acum o recenzie pentru serviciul oferit.",
                  })
                } catch (e) {
                  fail(e)
                }
              },
            })
          }
        />
      )}
      {tab === "services" && (
        <Services
          cats={cats}
          onAdd={() => setAddingService(true)}
          onToggle={async (c) => {
            try {
              setCats((await api.setCategory(c.category, !c.enabled)).categories)
              setDialog({
                title: c.enabled ? "Serviciu dezactivat" : "Serviciu activat",
                message: `${c.category} ${c.enabled ? "nu va mai apărea" : "va apărea acum"} în profilul tău profesional.`,
              })
            } catch (e) {
              fail(e)
            }
          }}
        />
      )}
      {tab === "subscription" && <Subscription onAction={setDialog} onChanged={refresh} />}
      {tab === "profile" && (
        <ProProfile
          user={user}
          onLogout={onLogout}
          onAction={setDialog}
          onNotifications={notifications}
          onUserUpdated={onUserUpdated}
        />
      )}
      {tab !== "dashboard" && tab !== "profile" && (
        <ProfileShortcut onClick={() => setTab("profile")} />
      )}
      <BottomNav
        active={tab}
        onChange={setTab}
        items={[
          ["dashboard", "Panou & Calendar", navIcons.dashboard],
          ["services", "Servicii", navIcons.services],
          ["subscription", "Abonament 39€", navIcons.subscription],
        ]}
      />
      {addingService && (
        <AddServiceModal
          onClose={() => setAddingService(false)}
          onAdd={async (name, price, duration) => {
            setCats((await api.addService({ name, price_from: price, duration: duration || undefined })).categories)
            setAddingService(false)
            setDialog({
              title: "Serviciu adăugat",
              message: `${name} este acum activ și vizibil în profilul tău profesional.`,
            })
          }}
        />
      )}
      {quote && (
        <QuoteModal
          booking={quote}
          quickSlots={data?.calendar?.quick_free_slots ?? []}
          onClose={() => setQuote(null)}
          onSentEstimate={async (estData) => {
            await api.sendEstimate(quote.id, estData)
            setQuote(null)
            await refresh()
            setDialog({
              title: "Estimare trimisă prin SMS!",
              message:
                "Clientul a primit estimarea de preț, durată și interval. Imediat ce apasă „Acceptă Estimarea”, slotul se blochează în calendarul tău și se programează reminderele SMS (24h & 2h).",
            })
          }}
        />
      )}
      {dialog && <ActionDialog action={dialog} onClose={() => setDialog(null)} />}
    </main>
  )
}

function InvestorBar({
  currentRole,
  onSwitchRole,
}: {
  currentRole: "client" | "pro" | "admin" | null
  onSwitchRole: (role: "client" | "pro" | "admin") => void
}) {
  const [busy, setBusy] = useState(false)
  const trigger = async (role: "client" | "pro" | "admin") => {
    if (busy) return
    setBusy(true)
    try {
      await onSwitchRole(role)
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="investor-switcher" role="navigation" aria-label="Comutator rapid roluri MVP Sibiu">
      <div style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
        <img
          src={assetUrl("rezolv-logo-64.png")}
          alt="REZOLV"
          style={{ width: 18, height: 18, borderRadius: 4, objectFit: "contain" }}
        />
        <span className="investor-badge">PILOT SIBIU • MVP</span>
      </div>
      <button
        type="button"
        className={currentRole === "client" ? "active" : ""}
        disabled={busy}
        onClick={() => trigger("client")}
      >
        👤 Client (Sibiu)
      </button>
      <button
        type="button"
        className={currentRole === "pro" ? "active" : ""}
        disabled={busy}
        onClick={() => trigger("pro")}
      >
        🔧 Meșter B2B (Calendar 2-Click)
      </button>
      <button
        type="button"
        className={currentRole === "admin" ? "active" : ""}
        disabled={busy}
        onClick={() => trigger("admin")}
      >
        🛡️ Super-Admin (White-Glove & KPI)
      </button>
    </div>
  )
}

export default function App() {
  const initialDemoUser =
    typeof window !== "undefined" ? ((window as any).__REZOLV_INITIAL_USER__ as ApiUser | undefined) : undefined
  const [user, setUser] = useState<ApiUser | null>(initialDemoUser ?? null)
  const [booting, setBooting] = useState(!initialDemoUser && Boolean(session.get()))
  const [legalDoc, setLegalDoc] = useState<"privacy" | "terms" | null>(null)
  const [isNotFound, setIsNotFound] = useState(() => {
    if (typeof window === "undefined") return false
    const p = window.location.pathname
    return window.location.hash === "#/404" || (p !== "/" && p !== "/index.html" && !p.endsWith(".html"))
  })

  useEffect(() => {
    const onHash = () => setIsNotFound(window.location.hash === "#/404")
    window.addEventListener("hashchange", onHash)
    return () => window.removeEventListener("hashchange", onHash)
  }, [])

  useEffect(() => {
    if (initialDemoUser || !session.get()) return
    api
      .me()
      .then((r) => setUser(r.user))
      .catch(() => session.clear())
      .finally(() => setBooting(false))
  }, [initialDemoUser])

  const logout = useCallback(() => {
    session.clear()
    setUser(null)
  }, [])

  const switchRole = useCallback(async (role: "client" | "pro" | "admin") => {
    const res = await api.demoSwitch(role)
    session.set(res.token)
    setUser(res.user)
  }, [])

  if (booting) {
    return (
      <main className="app-shell" role="status" aria-live="polite" style={{ padding: 36, textAlign: "center" }}>
        <div className="empty-state" style={{ marginTop: 64 }}>
          <strong style={{ display: "block", marginBottom: 8 }}>Se încarcă REZOLV Sibiu...</strong>
          <small style={{ opacity: 0.75 }}>Se verifică sesiunea securizată</small>
        </div>
      </main>
    )
  }

  return (
    <AppErrorBoundary>
      <a href="#main-content" className="visually-hidden">
        Sari la conținutul principal
      </a>
      <NetworkStatusBanner />
      {!(import.meta as any).env?.VITE_HIDE_DEMO_BAR && (
        <InvestorBar currentRole={user?.role ?? null} onSwitchRole={switchRole} />
      )}
      <div id="main-content">
        {isNotFound ? (
          <NotFoundScreen
            onGoHome={() => {
              window.location.hash = ""
              if (window.location.pathname !== "/") window.history.pushState({}, "", "/")
              setIsNotFound(false)
            }}
          />
        ) : !user ? (
          <Login onAuth={setUser} />
        ) : user.role === "admin" ? (
          <SuperAdminDashboard
            user={user}
            onSwitchRole={(r) => switchRole(r)}
            onLogout={logout}
            onNotice={(msg) => alert(`ℹ️ ${msg}`)}
            onError={(title, msg) => alert(`❌ ${title}: ${msg}`)}
          />
        ) : user.role === "client" ? (
          <ClientApp user={user} onLogout={logout} onUserUpdated={setUser} />
        ) : (
          <ProApp user={user} onLogout={logout} onUserUpdated={setUser} />
        )}
      </div>
      <CookieConsentBanner onOpenLegal={setLegalDoc} />
      {legalDoc && <LegalModal kind={legalDoc} onClose={() => setLegalDoc(null)} />}
    </AppErrorBoundary>
  )
}

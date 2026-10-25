import React, { Component, useEffect, useState } from "react"
import { api, ApiFailure, type ApiUser } from "../api"

// ------------------------------------------------------------------ 1. Real 500 Error Boundary
type ErrorBoundaryProps = { children: React.ReactNode }
type ErrorBoundaryState = { hasError: boolean; message: string }

export class AppErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props)
    this.state = { hasError: false, message: "" }
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, message: error?.message || "Eroare neașteptată în interfață." }
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    api.reportError(error.message, info.componentStack || error.stack, "react_error_boundary")
  }

  render() {
    if (this.state.hasError) {
      return (
        <main className="app-shell" role="alert" aria-live="assertive" style={{ padding: 28, textAlign: "center" }}>
          <div className="empty-state" style={{ marginTop: 48 }}>
            <div style={{ fontSize: 44, marginBottom: 12 }}>⚠️ 500</div>
            <strong>Ceva nu a funcționat corect</strong>
            <p style={{ margin: "10px 0 18px", opacity: 0.85 }}>
              Echipa tehnică REZOLV Sibiu a primit automat raportul de eroare ({this.state.message}).
            </p>
            <button
              type="button"
              className="primary-button"
              onClick={() => {
                this.setState({ hasError: false, message: "" })
                window.location.hash = ""
              }}
            >
              Reîncearcă aplicația
            </button>
          </div>
        </main>
      )
    }
    return this.props.children
  }
}

// ------------------------------------------------------------------ 2. Real 404 Not Found Screen
export function NotFoundScreen({ onGoHome }: { onGoHome: () => void }) {
  return (
    <main className="app-shell" role="main" aria-labelledby="not-found-title" style={{ padding: 28 }}>
      <div className="empty-state" style={{ marginTop: 48, textAlign: "center" }}>
        <div style={{ fontSize: 48, fontWeight: 800, color: "#38bdf8", marginBottom: 8 }}>404</div>
        <strong id="not-found-title" style={{ fontSize: 20 }}>
          Pagina nu a fost găsită
        </strong>
        <p style={{ margin: "10px 0 20px", opacity: 0.85 }}>
          Adresa pe care ai încercat să o accesezi nu există sau a fost mutată în cadrul platformei REZOLV Sibiu.
        </p>
        <button type="button" className="primary-button" onClick={onGoHome}>
          ← Înapoi la pagina principală
        </button>
      </div>
    </main>
  )
}

// ------------------------------------------------------------------ 3. Slow Network & Offline Banner
export function NetworkStatusBanner() {
  const [offline, setOffline] = useState(typeof navigator !== "undefined" ? !navigator.onLine : false)
  const [slowInfo, setSlowInfo] = useState<{ latencyMs: number } | null>(null)

  useEffect(() => {
    const onOffline = () => setOffline(true)
    const onOnline = () => setOffline(false)
    const onSlow = (e: Event) => {
      const detail = (e as CustomEvent).detail
      setSlowInfo({ latencyMs: detail?.latencyMs ?? 1500 })
      window.setTimeout(() => setSlowInfo(null), 6000)
    }
    window.addEventListener("offline", onOffline)
    window.addEventListener("online", onOnline)
    window.addEventListener("rezolv:slow-network", onSlow)
    return () => {
      window.removeEventListener("offline", onOffline)
      window.removeEventListener("online", onOnline)
      window.removeEventListener("rezolv:slow-network", onSlow)
    }
  }, [])

  if (!offline && !slowInfo) return null

  return (
    <div
      role="status"
      aria-live="polite"
      style={{
        background: offline ? "#991b1b" : "#92400e",
        color: "#fff",
        padding: "8px 16px",
        fontSize: 13,
        fontWeight: 600,
        textAlign: "center",
        zIndex: 9999,
      }}
    >
      {offline
        ? "📡 Ești offline. Afișăm datele salvate în cache până la reconectare."
        : `🐢 Conexiune lentă detectată (${slowInfo?.latencyMs} ms). Datele sunt optimizate și comprimate automat.`}
    </div>
  )
}

// ------------------------------------------------------------------ 4. Legal Viewer Modal (Privacy & Terms)
export function LegalModal({
  kind,
  onClose,
}: {
  kind: "privacy" | "terms"
  onClose: () => void
}) {
  const [doc, setDoc] = useState<any>(null)

  useEffect(() => {
    const fn = kind === "privacy" ? api.legalPrivacy : api.legalTerms
    fn()
      .then(setDoc)
      .catch(() =>
        setDoc({
          title:
            kind === "privacy"
              ? "Politică de Confidențialitate (GDPR)"
              : "Termeni și Condiții — REZOLV Sibiu",
          sections: [
            {
              heading: "Protecția datelor & Transparență",
              body: "REZOLV Sibiu respectă Regulamentul (UE) 2016/679 (GDPR). Îți poți exporta sau șterge contul și datele în orice moment din secțiunea Profil.",
            },
          ],
        }),
      )
  }, [kind])

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="Document legal">
      <div className="modal quote-modal" style={{ maxHeight: "84vh", overflowY: "auto" }}>
        <div className="modal-handle" />
        <div className="modal-title">{doc?.title ?? "Se încarcă..."}</div>
        {doc?.controller && (
          <small style={{ display: "block", marginBottom: 12, opacity: 0.75 }}>{doc.controller}</small>
        )}
        {(doc?.sections ?? []).map((s: any, i: number) => (
          <div key={i} style={{ marginBottom: 14, textAlign: "left" }}>
            <strong style={{ display: "block", marginBottom: 4 }}>{s.heading}</strong>
            <p style={{ margin: 0, fontSize: 13.5, lineHeight: 1.5, opacity: 0.9 }}>{s.body}</p>
          </div>
        ))}
        <button type="button" className="primary-button" onClick={onClose}>
          Am înțeles
        </button>
      </div>
    </div>
  )
}

// ------------------------------------------------------------------ 5. GDPR Cookie Consent Banner
export function CookieConsentBanner({
  onOpenLegal,
}: {
  onOpenLegal: (kind: "privacy" | "terms") => void
}) {
  const [visible, setVisible] = useState(() => {
    try {
      return !localStorage.getItem("rezolv_cookie_consent")
    } catch {
      return false
    }
  })

  if (!visible) return null

  const choose = (mode: "all" | "essential") => {
    try {
      localStorage.setItem("rezolv_cookie_consent", mode)
    } catch {
      // ignore storage errors
    }
    setVisible(false)
    api.saveCookieConsent(mode === "all", false).catch(() => {})
  }

  return (
    <aside
      role="region"
      aria-label="Consimțământ module cookie (GDPR)"
      style={{
        position: "fixed",
        bottom: 14,
        left: 14,
        right: 14,
        maxWidth: 560,
        margin: "0 auto",
        background: "rgba(11, 25, 44, 0.97)",
        color: "#f8fafc",
        border: "1px solid rgba(56, 189, 248, 0.35)",
        borderRadius: 16,
        padding: "14px 16px",
        boxShadow: "0 16px 40px rgba(0,0,0,0.45)",
        zIndex: 9500,
        fontSize: 13,
      }}
    >
      <div style={{ fontWeight: 700, marginBottom: 4 }}>🍪 Confidențialitate &amp; Cookie-uri (GDPR)</div>
      <p style={{ margin: "0 0 10px", opacity: 0.88, lineHeight: 1.45 }}>
        Folosim cookie-uri strict necesare pentru sesiunea de autentificare și, cu acordul tău, telemetrie anonimă
        pentru îmbunătățirea platformei în Sibiu. Citește{" "}
        <button
          type="button"
          onClick={() => onOpenLegal("privacy")}
          style={{ background: "none", border: "none", color: "#38bdf8", textDecoration: "underline", padding: 0, cursor: "pointer" }}
        >
          Politica de Confidențialitate
        </button>{" "}
        și{" "}
        <button
          type="button"
          onClick={() => onOpenLegal("terms")}
          style={{ background: "none", border: "none", color: "#38bdf8", textDecoration: "underline", padding: 0, cursor: "pointer" }}
        >
          Termenii
        </button>
        .
      </p>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <button
          type="button"
          onClick={() => choose("all")}
          style={{
            background: "#0284c7",
            color: "#fff",
            border: "none",
            borderRadius: 10,
            padding: "8px 14px",
            fontWeight: 700,
            cursor: "pointer",
          }}
        >
          Acceptă toate
        </button>
        <button
          type="button"
          onClick={() => choose("essential")}
          style={{
            background: "rgba(255,255,255,0.1)",
            color: "#e2e8f0",
            border: "1px solid rgba(255,255,255,0.2)",
            borderRadius: 10,
            padding: "8px 14px",
            fontWeight: 600,
            cursor: "pointer",
          }}
        >
          Doar esențiale
        </button>
      </div>
    </aside>
  )
}

// ------------------------------------------------------------------ 6. End-to-End Password Reset Modal
export function PasswordResetModal({
  initialEmail,
  onClose,
  onSuccess,
}: {
  initialEmail: string
  onClose: () => void
  onSuccess: (msg: string) => void
}) {
  const [email, setEmail] = useState(initialEmail)
  const [step, setStep] = useState<"request" | "confirm">("request")
  const [token, setToken] = useState("")
  const [newPassword, setNewPassword] = useState("")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const [info, setInfo] = useState("")

  const sendRequest = async () => {
    setBusy(true)
    setError("")
    try {
      const res = await api.requestReset(email.trim())
      setInfo(res.message)
      if (res.dev_token) {
        setToken(res.dev_token)
      }
      setStep("confirm")
    } catch (e) {
      setError(e instanceof ApiFailure ? e.message : "Nu am putut trimite codul.")
    } finally {
      setBusy(false)
    }
  }

  const confirmNewPassword = async () => {
    setBusy(true)
    setError("")
    try {
      const res = await api.confirmReset(token.trim(), newPassword)
      onSuccess(res.message)
      onClose()
    } catch (e) {
      setError(e instanceof ApiFailure ? e.message : "Token invalid sau parolă neconformă.")
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="Resetare parolă">
      <div className="modal quote-modal">
        <div className="modal-handle" />
        <div className="modal-title">Resetare parolă</div>
        {step === "request" ? (
          <>
            <p>Introdu adresa de email asociată contului tău pentru a primi codul de resetare.</p>
            <div className="label">Adresă de email</div>
            <div className="input-shell">
              <input
                className="field"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="exemplu@email.ro"
              />
            </div>
            {error && <div className="form-error">{error}</div>}
            <button type="button" className="primary-button" disabled={busy || !email.trim()} onClick={sendRequest}>
              {busy ? "Se trimite..." : "Trimite codul de resetare"}
            </button>
          </>
        ) : (
          <>
            <p>{info || "Introdu codul primit pe email și noua parolă (minim 8 caractere, litere și cifre)."}</p>
            <div className="label">Cod / Token de resetare</div>
            <div className="input-shell">
              <input
                className="field"
                type="text"
                value={token}
                onChange={(e) => setToken(e.target.value)}
                placeholder="Codul primit pe email"
              />
            </div>
            <div className="label">Parolă nouă</div>
            <div className="input-shell">
              <input
                className="field"
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                placeholder="Minim 8 caractere (litere + cifre)"
              />
            </div>
            {error && <div className="form-error">{error}</div>}
            <button
              type="button"
              className="primary-button"
              disabled={busy || !token.trim() || newPassword.length < 8}
              onClick={confirmNewPassword}
            >
              {busy ? "Se salvează..." : "Schimbă parola"}
            </button>
          </>
        )}
        <button type="button" className="modal-later" onClick={onClose} style={{ background: "none", border: "none", width: "100%" }}>
          Anulează
        </button>
      </div>
    </div>
  )
}

// ------------------------------------------------------------------ 7. Email Verification + GDPR Export & Account Deletion
export function AccountSecurityAndGdprCard({
  user,
  onUserUpdated,
  onAccountDeleted,
  onOpenLegal,
}: {
  user: ApiUser
  onUserUpdated: (u: ApiUser) => void
  onAccountDeleted: () => void
  onOpenLegal: (kind: "privacy" | "terms") => void
}) {
  const [verifying, setVerifying] = useState(false)
  const [verToken, setVerToken] = useState("")
  const [confirmingDelete, setConfirmingDelete] = useState(false)
  const [notice, setNotice] = useState("")
  const [busy, setBusy] = useState(false)

  const startVerifyEmail = async () => {
    setBusy(true)
    setNotice("")
    try {
      const res = await api.sendVerifyEmail()
      if (res.already_verified) {
        setNotice("Adresa de email este deja verificată.")
      } else {
        setVerifying(true)
        if (res.dev_token) setVerToken(res.dev_token)
        setNotice(res.message)
      }
    } catch (e) {
      setNotice(e instanceof ApiFailure ? e.message : "Nu am putut trimite emailul.")
    } finally {
      setBusy(false)
    }
  }

  const submitVerifyToken = async () => {
    setBusy(true)
    try {
      const res = await api.confirmVerifyEmail(verToken.trim())
      onUserUpdated(res.user)
      setVerifying(false)
      setNotice("✓ Adresa de email a fost verificată cu succes!")
    } catch (e) {
      setNotice(e instanceof ApiFailure ? e.message : "Cod invalid.")
    } finally {
      setBusy(false)
    }
  }

  const exportGdpr = async () => {
    setBusy(true)
    setNotice("")
    try {
      const data = await api.exportMyData()
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" })
      const url = URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      a.download = `rezolv-gdpr-export-${user.id}.json`
      a.click()
      URL.revokeObjectURL(url)
      setNotice("✓ Arhiva cu datele tale personale (GDPR JSON) a fost descărcată.")
    } catch (e) {
      setNotice(e instanceof ApiFailure ? e.message : "Exportul nu a putut fi generat.")
    } finally {
      setBusy(false)
    }
  }

  const executeDeleteAccount = async () => {
    setBusy(true)
    try {
      await api.deleteMyAccount()
      onAccountDeleted()
    } catch (e) {
      setNotice(e instanceof ApiFailure ? e.message : "Nu am putut șterge contul.")
      setBusy(false)
    }
  }

  const isVerified = user.email_verified !== false

  return (
    <section
      className="profile-detail-card"
      aria-label="Securitate, Verificare Email și Drepturi GDPR"
      style={{ marginTop: 12, display: "grid", gap: 10 }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
        <strong>Securitate &amp; Date Personale (GDPR)</strong>
        <span
          style={{
            fontSize: 12,
            padding: "3px 10px",
            borderRadius: 99,
            fontWeight: 700,
            background: isVerified ? "rgba(16,185,129,0.16)" : "rgba(245,158,11,0.18)",
            color: isVerified ? "#10b981" : "#f59e0b",
          }}
        >
          {isVerified ? "✓ Email verificat" : "⚠️ Email neverificat"}
        </span>
      </div>

      {!isVerified && !verifying && (
        <button type="button" className="outline-button compact" disabled={busy} onClick={startVerifyEmail}>
          Trimite cod de verificare pe email
        </button>
      )}

      {verifying && (
        <div style={{ display: "grid", gap: 8 }}>
          <div className="input-shell">
            <input
              className="field"
              value={verToken}
              onChange={(e) => setVerToken(e.target.value)}
              placeholder="Cod verificare email"
            />
          </div>
          <button type="button" className="primary-button compact" disabled={busy || !verToken.trim()} onClick={submitVerifyToken}>
            Confirmă adresa de email
          </button>
        </div>
      )}

      {notice && (
        <div role="status" aria-live="polite" style={{ fontSize: 13, color: "#38bdf8", fontWeight: 600 }}>
          {notice}
        </div>
      )}

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <button type="button" className="outline-button compact" disabled={busy} onClick={exportGdpr}>
          📥 Exportă datele mele (GDPR)
        </button>
        <button
          type="button"
          className="outline-button compact"
          style={{ borderColor: "rgba(239,68,68,0.45)", color: "#ef4444" }}
          disabled={busy}
          onClick={() => setConfirmingDelete(true)}
        >
          🗑️ Șterge contul și datele
        </button>
      </div>

      <div style={{ display: "flex", gap: 14, fontSize: 12.5, opacity: 0.8 }}>
        <button
          type="button"
          onClick={() => onOpenLegal("privacy")}
          style={{ background: "none", border: "none", color: "inherit", textDecoration: "underline", padding: 0, cursor: "pointer" }}
        >
          Politică de Confidențialitate (GDPR)
        </button>
        <button
          type="button"
          onClick={() => onOpenLegal("terms")}
          style={{ background: "none", border: "none", color: "inherit", textDecoration: "underline", padding: 0, cursor: "pointer" }}
        >
          Termeni și Condiții
        </button>
      </div>

      {confirmingDelete && (
        <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="Confirmare ștergere cont">
          <div className="modal action-dialog">
            <div className="modal-handle" />
            <div className="modal-title">Ștergi definitiv contul și datele?</div>
            <p>
              Conform Art. 17 GDPR (Dreptul la ștergere), contul tău ({user.email}), istoricul programărilor și
              datele personale vor fi șterse ireversibil.
            </p>
            <button
              type="button"
              className="primary-button"
              style={{ background: "#dc2626" }}
              disabled={busy}
              onClick={executeDeleteAccount}
            >
              {busy ? "Se șterg datele..." : "Da, șterge definitiv contul meu"}
            </button>
            <button
              type="button"
              className="modal-later"
              onClick={() => setConfirmingDelete(false)}
              style={{ background: "none", border: "none", width: "100%" }}
            >
              Anulează
            </button>
          </div>
        </div>
      )}
    </section>
  )
}

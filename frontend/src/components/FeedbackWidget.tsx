import { useState } from "react"
import { api } from "../api"
import { SvgIcon } from "./SvgIcon"

export function FeedbackWidget({ user }: { user?: any }) {
  const [isOpen, setIsOpen] = useState(false)
  const [rating, setRating] = useState<number>(5)
  const [hoverRating, setHoverRating] = useState<number | null>(null)
  const [category, setCategory] = useState<"idea" | "bug" | "praise" | "general">("idea")
  const [message, setMessage] = useState("")
  const [name, setName] = useState(user?.name || "")
  const [email, setEmail] = useState(user?.email || "")
  const [submitting, setSubmitting] = useState(false)
  const [submitted, setSubmitted] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (message.trim().length < 3) {
      setError("Te rugăm să adaugi câteva cuvinte în mesaj.")
      return
    }

    setSubmitting(true)
    setError(null)

    try {
      const deviceInfo =
        typeof window !== "undefined"
          ? `${navigator.userAgent.includes("iPhone") ? "iPhone" : navigator.userAgent.includes("Android") ? "Android" : "Desktop/Mac"} · ${window.innerWidth}x${window.innerHeight}`
          : "Web"

      await api.submitFeedback({
        rating,
        category,
        message: message.trim(),
        name: name.trim() || user?.name || "Utilizator",
        email: email.trim() || user?.email || undefined,
        device_info: deviceInfo,
      })

      setSubmitted(true)
    } catch (err: any) {
      setError(err?.message || "Nu am putut trimite feedback-ul. Încearcă din nou.")
    } finally {
      setSubmitting(false)
    }
  }

  const resetAndClose = () => {
    setIsOpen(false)
    setTimeout(() => {
      setSubmitted(false)
      setMessage("")
      setError(null)
      setRating(5)
    }, 200)
  }

  const categories = [
    { id: "idea", label: "Propunere funcționalitate" },
    { id: "bug", label: "Raportare eroare" },
    { id: "praise", label: "Apreciere" },
    { id: "general", label: "Observație generală" },
  ] as const

  return (
    <>
      <button
        type="button"
        onClick={() => setIsOpen(true)}
        className="feedback-floating-btn"
        aria-label="Trimite feedback despre aplicație"
        title="Trimite feedback despre REZOLV Sibiu"
      >
        <span className="feedback-btn-icon">
          <SvgIcon name="message" size={14} />
        </span>
        <span className="feedback-btn-text">Feedback</span>
        <span className="feedback-btn-badge">Sibiu</span>
      </button>

      {isOpen && (
        <div className="feedback-modal-overlay" onClick={resetAndClose}>
          <div
            className="feedback-modal-card"
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-labelledby="feedback-title"
          >
            <div className="feedback-modal-header">
              <div>
                <h3 id="feedback-title" style={{ margin: 0, fontSize: 16, fontWeight: 600 }}>
                  Feedback platformă
                </h3>
                <small style={{ color: "var(--text-secondary)", fontSize: 12 }}>
                  Observațiile sunt înregistrate direct în panoul tehnic REZOLV Sibiu.
                </small>
              </div>
              <button
                type="button"
                className="feedback-modal-close"
                onClick={resetAndClose}
                aria-label="Închide fereastra"
              >
                <SvgIcon name="close" size={14} />
              </button>
            </div>

            {submitted ? (
              <div className="feedback-success-state">
                <h4 style={{ margin: "0 0 6px 0", fontSize: 15, fontWeight: 600 }}>
                  Feedback înregistrat
                </h4>
                <p style={{ margin: "0 0 16px 0", color: "var(--text-secondary)", fontSize: 13 }}>
                  Mesajul și evaluarea au fost salvate în jurnalul platformei.
                </p>
                <button
                  type="button"
                  className="primary-button"
                  onClick={resetAndClose}
                  style={{ width: "100%" }}
                >
                  Închide
                </button>
              </div>
            ) : (
              <form onSubmit={handleSubmit} className="feedback-form">
                <div className="feedback-field">
                  <label
                    style={{
                      fontSize: 12,
                      fontWeight: 500,
                      color: "var(--text-secondary)",
                      display: "block",
                      marginBottom: 6,
                    }}
                  >
                    Evaluare experiență
                  </label>
                  <div className="feedback-stars">
                    {[1, 2, 3, 4, 5].map((star) => {
                      const active = (hoverRating ?? rating) >= star
                      return (
                        <button
                          key={star}
                          type="button"
                          className={`star-btn ${active ? "active" : ""}`}
                          onMouseEnter={() => setHoverRating(star)}
                          onMouseLeave={() => setHoverRating(null)}
                          onClick={() => setRating(star)}
                          aria-label={`${star} din 5`}
                        >
                          ★
                        </button>
                      )
                    })}
                    <span className="star-label tabular">{rating} / 5</span>
                  </div>
                </div>

                <div className="feedback-field">
                  <label
                    style={{
                      fontSize: 12,
                      fontWeight: 500,
                      color: "var(--text-secondary)",
                      display: "block",
                      marginBottom: 6,
                    }}
                  >
                    Categorie
                  </label>
                  <div className="feedback-categories">
                    {categories.map((c) => (
                      <button
                        key={c.id}
                        type="button"
                        className={`cat-chip ${category === c.id ? "selected" : ""}`}
                        onClick={() => setCategory(c.id)}
                      >
                        {c.label}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="feedback-field">
                  <label
                    style={{
                      fontSize: 12,
                      fontWeight: 500,
                      color: "var(--text-secondary)",
                      display: "block",
                      marginBottom: 6,
                    }}
                  >
                    Detalii
                  </label>
                  <textarea
                    rows={4}
                    value={message}
                    onChange={(e) => setMessage(e.target.value)}
                    placeholder="Descrie observația, propunerea sau comportamentul întâlnit..."
                    className="feedback-textarea"
                    required
                  />
                </div>

                <div className="feedback-row" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                  <div>
                    <label style={{ fontSize: 11, color: "var(--text-muted)", display: "block", marginBottom: 4 }}>
                      Nume (opțional)
                    </label>
                    <input
                      type="text"
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      placeholder="Ex. Andrei"
                      className="feedback-input"
                    />
                  </div>
                  <div>
                    <label style={{ fontSize: 11, color: "var(--text-muted)", display: "block", marginBottom: 4 }}>
                      Contact (opțional)
                    </label>
                    <input
                      type="text"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder="Email sau telefon"
                      className="feedback-input"
                    />
                  </div>
                </div>

                {error && <div className="feedback-error-banner">{error}</div>}

                <div className="feedback-modal-actions">
                  <button type="button" className="outline-button" onClick={resetAndClose} disabled={submitting}>
                    Anulează
                  </button>
                  <button type="submit" className="primary-button" disabled={submitting || message.trim().length < 3}>
                    {submitting ? "Se trimite..." : "Trimite feedback"}
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}
    </>
  )
}

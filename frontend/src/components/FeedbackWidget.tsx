import { useState } from "react"
import { api } from "../api"

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
      setError("Te rugăm să scrii cel puțin câteva cuvinte în mesaj.")
      return
    }

    setSubmitting(true)
    setError(null)

    try {
      const deviceInfo = typeof window !== "undefined"
        ? `${navigator.userAgent.includes("iPhone") ? "iPhone" : navigator.userAgent.includes("Android") ? "Android" : "Desktop/Mac"} • ${window.innerWidth}x${window.innerHeight}`
        : "Web"

      await api.submitFeedback({
        rating,
        category,
        message: message.trim(),
        name: name.trim() || user?.name || "Tester Anonim",
        email: email.trim() || user?.email || undefined,
        device_info: deviceInfo,
      })

      setSubmitted(true)
      setTimeout(() => {
        // keep open until user closes or after a bit
      }, 500)
    } catch (err: any) {
      setError(err?.message || "Nu am putut trimite feedback-ul. Te rugăm să încerci din nou.")
    } finally {
      setSubmitting(false)
    }
  }

  const resetAndClose = () => {
    setIsOpen(false)
    // reset form after transition
    setTimeout(() => {
      setSubmitted(false)
      setMessage("")
      setError(null)
      setRating(5)
    }, 300)
  }

  const categories = [
    { id: "idea", label: "💡 Idee nouă", desc: "Ce ar trebui adăugat" },
    { id: "bug", label: "🐛 Am găsit un bug", desc: "Ceva nu a mers corect" },
    { id: "praise", label: "⭐ Ce mi-a plăcut", desc: "Puncte forte" },
    { id: "general", label: "💬 Părere generală", desc: "Impresii despre design" },
  ] as const

  return (
    <>
      {/* Floating trigger button */}
      <button
        type="button"
        onClick={() => setIsOpen(true)}
        className="feedback-floating-btn"
        aria-label="Trimite feedback despre aplicație"
        title="Ajută-ne cu o părere despre REZOLV Sibiu"
      >
        <span className="feedback-btn-icon">💬</span>
        <span className="feedback-btn-text">Feedback</span>
        <span className="feedback-btn-badge">Pilot</span>
      </button>

      {/* Modal dialog */}
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
                <h3 id="feedback-title" style={{ margin: 0, fontSize: 18, color: "var(--navy)" }}>
                  💬 Părerea ta contează!
                </h3>
                <small style={{ color: "var(--muted)", fontSize: 12 }}>
                  Testezi REZOLV Sibiu (Pilot MVP). Feedback-ul tău ne ajută direct!
                </small>
              </div>
              <button
                type="button"
                className="feedback-modal-close"
                onClick={resetAndClose}
                aria-label="Închide fereastra"
              >
                ✕
              </button>
            </div>

            {submitted ? (
              <div className="feedback-success-state">
                <div style={{ fontSize: 44, marginBottom: 8 }}>🎉</div>
                <h4 style={{ margin: "0 0 6px 0", color: "var(--navy)", fontSize: 16 }}>
                  Mulțumim mult pentru feedback!
                </h4>
                <p style={{ margin: "0 0 16px 0", color: "var(--muted)", fontSize: 13, lineHeight: "1.4" }}>
                  Mesajul și evaluarea ta au fost înregistrate în baza de date. Echipa REZOLV Sibiu va ține cont de
                  sugestiile tale!
                </p>
                <button
                  type="button"
                  className="primary-button"
                  onClick={resetAndClose}
                  style={{ width: "100%", padding: "10px 0" }}
                >
                  Închide fereastra
                </button>
              </div>
            ) : (
              <form onSubmit={handleSubmit} className="feedback-form">
                {/* 1. Star Rating */}
                <div className="feedback-field">
                  <label style={{ fontSize: 13, fontWeight: 600, color: "var(--navy)", display: "block", marginBottom: 6 }}>
                    Cum evaluezi experiența ta de până acum?
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
                          aria-label={`${star} stele din 5`}
                        >
                          ★
                        </button>
                      )
                    })}
                    <span className="star-label">
                      {rating === 5
                        ? "Excelent! ⭐⭐⭐⭐⭐"
                        : rating === 4
                          ? "Foarte bun! ⭐⭐⭐⭐"
                          : rating === 3
                            ? "Acceptabil ⭐⭐⭐"
                            : rating === 2
                              ? "Necesită îmbunătățiri ⭐⭐"
                              : "Dezamăgitor ⭐"}
                    </span>
                  </div>
                </div>

                {/* 2. Category selection */}
                <div className="feedback-field">
                  <label style={{ fontSize: 13, fontWeight: 600, color: "var(--navy)", display: "block", marginBottom: 6 }}>
                    Despre ce este feedback-ul tău?
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

                {/* 3. Message */}
                <div className="feedback-field">
                  <label style={{ fontSize: 13, fontWeight: 600, color: "var(--navy)", display: "block", marginBottom: 6 }}>
                    Mesajul tău:
                  </label>
                  <textarea
                    rows={4}
                    value={message}
                    onChange={(e) => setMessage(e.target.value)}
                    placeholder={
                      category === "bug"
                        ? "Ce buton ai apăsat sau ce eroare a apărut? Pe ce telefon sau browser ești?"
                        : category === "idea"
                          ? "Ce funcționalitate sau opțiune nouă ai vrea să existe în aplicație?"
                          : category === "praise"
                            ? "Ce anume ți-a plăcut cel mai mult la aplicație?"
                            : "Cum ți se pare interfața, culorile, viteza și cât de ușor e de folosit?"
                    }
                    className="feedback-textarea"
                    required
                  />
                </div>

                {/* 4. Optional user details if not logged in */}
                <div className="feedback-row" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                  <div>
                    <label style={{ fontSize: 11, color: "var(--muted)", display: "block", marginBottom: 3 }}>
                      Numele tău (opțional)
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
                    <label style={{ fontSize: 11, color: "var(--muted)", display: "block", marginBottom: 3 }}>
                      Email / Telefon (opțional)
                    </label>
                    <input
                      type="text"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder="Pentru răspuns"
                      className="feedback-input"
                    />
                  </div>
                </div>

                {error && (
                  <div className="feedback-error-banner" style={{ marginTop: 8 }}>
                    ⚠️ {error}
                  </div>
                )}

                <div className="feedback-modal-actions">
                  <button type="button" className="outline-button" onClick={resetAndClose} disabled={submitting}>
                    Anulează
                  </button>
                  <button type="submit" className="primary-button" disabled={submitting || message.trim().length < 3}>
                    {submitting ? "Se trimite..." : "Trimite Feedback 🚀"}
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

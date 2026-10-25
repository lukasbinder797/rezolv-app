import { useState } from "react"
import {
  api,
  type ApiBooking,
  type ApiCalendarDay,
  type ApiQuickSlot,
} from "../api"

export function ProB2BCalendar({
  days,
  quickSlots,
  onRefresh,
  onNotice,
  onError,
}: {
  days: ApiCalendarDay[]
  quickSlots: ApiQuickSlot[]
  onRefresh: () => void
  onNotice: (msg: string) => void
  onError: (title: string, msg: string) => void
}) {
  const [selectedDayIdx, setSelectedDayIdx] = useState(0)
  const [rescheduleTarget, setRescheduleTarget] = useState<ApiBooking | null>(null)
  const [busyId, setBusyId] = useState<string | null>(null)

  const currentDay = days[selectedDayIdx] ?? days[0]

  const handleQuickReschedule = async (booking: ApiBooking, slot: { start_at?: number; shift_hours?: number; label: string }) => {
    setBusyId(booking.id)
    try {
      await api.reschedule(booking.id, {
        start_at: slot.start_at,
        shift_hours: slot.shift_hours,
        slot_label: slot.label,
      })
      setRescheduleTarget(null)
      onNotice(`Reprogramat din 2 click-uri pe ${slot.label}. SMS-urile de 24h și 2h au fost actualizate!`)
      onRefresh()
    } catch (e: any) {
      onError("Conflict în Calendar", e?.message ?? "Nu am putut reprograma.")
    } finally {
      setBusyId(null)
    }
  }

  const handleTriggerSms = async (booking: ApiBooking) => {
    setBusyId(booking.id)
    try {
      const res = await api.triggerSms(booking.id)
      const count = res.dispatched?.length ?? 0
      onNotice(
        count > 0
          ? `Am expediat instant ${count} SMS-uri anti no-show (24h & 2h) către ${booking.client.name}!`
          : "Toate reminderele SMS pentru această lucrare au fost deja livrate.",
      )
      onRefresh()
    } catch (e: any) {
      onError("Eroare SMS", e?.message ?? "Nu am putut trimite SMS-ul.")
    } finally {
      setBusyId(null)
    }
  }

  const handleComplete = async (booking: ApiBooking) => {
    if (!window.confirm(`Confirmi finalizarea lucrării pentru ${booking.client.name}?`)) return
    setBusyId(booking.id)
    try {
      await api.complete(booking.id)
      onNotice(`Lucrarea #${booking.id.slice(0, 8)} a fost marcată ca finalizată!`)
      onRefresh()
    } catch (e: any) {
      onError("Eroare Finalizare", e?.message ?? "Nu am putut finaliza lucrarea.")
    } finally {
      setBusyId(null)
    }
  }

  const handleNoShow = async (booking: ApiBooking) => {
    if (!window.confirm(`Înregistrezi NO-SHOW pentru ${booking.client.name}? (Clientul nu a răspuns la sosire)`)) return
    setBusyId(booking.id)
    try {
      await api.markNoShow(booking.id, "Clientul nu a răspuns la sosire")
      onNotice(`Programarea #${booking.id.slice(0, 8)} a fost înregistrată ca No-Show.`)
      onRefresh()
    } catch (e: any) {
      onError("Eroare No-Show", e?.message ?? "Nu am putut înregistra no-show.")
    } finally {
      setBusyId(null)
    }
  }

  if (!currentDay) return null

  return (
    <div className="section-block">
      <div className="section-heading">
        <div>
          Calendar Teren B2B <span className="count">2-Click</span>
        </div>
        <small>Sloturi blocate automat + SMS 24h/2h</small>
      </div>

      {/* 5-Day Selector Strip */}
      <div className="cal-day-strip">
        {days.map((d, idx) => {
          const busyCount = d.slots.filter((s) => s.booking && s.booking.status !== "completed").length
          return (
            <div
              key={d.date_iso}
              role="button"
              tabIndex={0}
              className={`pressable cal-day-pill ${idx === selectedDayIdx ? "active" : ""}`}
              onClick={() => setSelectedDayIdx(idx)}
            >
              <strong>{d.day_name}</strong>
              <small>{d.date_short}</small>
              <i>{busyCount > 0 ? `${busyCount} lucr.` : "Liber"}</i>
            </div>
          )
        })}
      </div>

      {/* 2-Click Instant Reschedule Bar when an appointment is tapped */}
      {rescheduleTarget && (
        <div className="estimate-offer-box" style={{ marginBottom: 14 }}>
          <div className="estimate-offer-head">
            <span>CLICK 2: ALEGE NOUA ORĂ PENTRU {rescheduleTarget.client.name.toUpperCase()}</span>
            <span
              className="pressable"
              onClick={() => setRescheduleTarget(null)}
              style={{ cursor: "pointer", textDecoration: "underline" }}
            >
              Închide ✕
            </span>
          </div>
          <p style={{ fontSize: 11, color: "var(--navy)", margin: "6px 0 8px" }}>
            Lucrare: <strong>{rescheduleTarget.service_name}</strong> ({rescheduleTarget.neighborhood ?? "Sibiu"}).
            Atinge un slot liber pentru a muta programarea și a trimite automat SMS clientului:
          </p>
          <div className="chip-row">
            <div
              role="button"
              tabIndex={0}
              className="pressable quick-chip active"
              onClick={() => handleQuickReschedule(rescheduleTarget, { shift_hours: 1, label: "Decalat +1 oră" })}
            >
              ⏱️ +1 oră mai târziu
            </div>
            <div
              role="button"
              tabIndex={0}
              className="pressable quick-chip"
              onClick={() => handleQuickReschedule(rescheduleTarget, { shift_hours: 2, label: "Decalat +2 ore" })}
            >
              ⏱️ +2 ore mai târziu
            </div>
            {quickSlots.slice(0, 5).map((qs) => (
              <div
                key={qs.start_at}
                role="button"
                tabIndex={0}
                className="pressable quick-chip"
                onClick={() => handleQuickReschedule(rescheduleTarget, { start_at: qs.start_at, label: qs.full_label })}
              >
                📅 {qs.label}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Hourly Slot Grid */}
      <div className="cal-slot-list">
        {currentDay.slots.map((slot) => {
          const bk = slot.booking
          if (!bk) {
            return (
              <div key={slot.hour} className="cal-slot-row slot-free">
                <div className="cal-slot-hour">{slot.hour}</div>
                <div className="grow">
                  <small style={{ color: "var(--muted)", fontSize: 11 }}>
                    {slot.status === "past" ? "Interval trecut" : "Slot disponibil în calendar"}
                  </small>
                </div>
                <span style={{ fontSize: 10, color: "var(--aqua)", fontFamily: "Inter:Bold" }}>LIBER</span>
              </div>
            )
          }

          const isEst = bk.status === "estimated"
          const isDone = bk.status === "completed"
          const smsScheduled = (bk.sms_reminders ?? []).filter((s) => s.status === "scheduled").length
          const smsSent = (bk.sms_reminders ?? []).filter((s) => s.status === "sent" || s.status === "delivered").length

          return (
            <div
              key={slot.hour}
              className={`cal-slot-row ${isEst ? "slot-estimated" : "slot-accepted"}`}
            >
              <div className="cal-slot-hour">
                {slot.hour}
                <small style={{ display: "block", fontSize: 9, color: "var(--muted)" }}>
                  {bk.quote_duration ?? "1 oră"}
                </small>
              </div>
              <div className="grow">
                <strong style={{ fontSize: 13 }}>
                  {bk.service_name} • {bk.quote_price ?? "—"} RON
                </strong>
                <small style={{ color: "var(--muted)", fontSize: 10, marginTop: 2, display: "block" }}>
                  Client: <strong>{bk.client.name}</strong> • 📍 {bk.neighborhood ?? "Sibiu"}
                  {bk.client_address ? ` • 🏠 ${bk.client_address}` : bk.client.address ? ` • 🏠 ${bk.client.address}` : ""}
                  {bk.client_phone ? ` • 📞 ${bk.client_phone}` : bk.client.phone ? ` • 📞 ${bk.client.phone}` : ""}
                </small>

                {/* Quick Field Navigation & Direct Client Call */}
                {!isDone && (
                  <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 4 }}>
                    {(bk.client_phone || bk.client.phone) && (
                      <a
                        href={`tel:${(bk.client_phone || bk.client.phone)!.replace(/\s+/g, "")}`}
                        style={{
                          fontSize: 11,
                          textDecoration: "none",
                          padding: "3px 8px",
                          background: "#e8f5e9",
                          color: "#2e7d32",
                          borderRadius: 6,
                          fontWeight: "bold",
                        }}
                      >
                        📞 Sună Clientul
                      </a>
                    )}
                    <a
                      href={`https://waze.com/ul?q=${encodeURIComponent((bk.client_address || bk.client.address || bk.neighborhood || "Sibiu") + ", Sibiu, Romania")}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{
                        fontSize: 11,
                        textDecoration: "none",
                        padding: "3px 8px",
                        background: "#e0f2fe",
                        color: "#0369a1",
                        borderRadius: 6,
                        fontWeight: "bold",
                      }}
                    >
                      🚙 Waze Sibiu
                    </a>
                    <a
                      href={`https://www.google.com/maps/search/?api=1&query=${encodeURIComponent((bk.client_address || bk.client.address || bk.neighborhood || "Sibiu") + ", Sibiu, Romania")}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{
                        fontSize: 11,
                        textDecoration: "none",
                        padding: "3px 8px",
                        background: "#f1f5f9",
                        color: "#334155",
                        borderRadius: 6,
                        fontWeight: "bold",
                      }}
                    >
                      🗺️ Maps
                    </a>
                  </div>
                )}

                <div className="sms-pill-row">
                  <span className={`sms-pill ${smsSent > 0 ? "sent" : ""}`}>
                    💬 {smsSent} SMS trimise
                  </span>
                  {smsScheduled > 0 && (
                    <span className="sms-pill">
                      ⏰ {smsScheduled} remindere (24h & 2h) în coadă
                    </span>
                  )}
                  {isEst && (
                    <span className="sms-pill" style={{ background: "#fef3c7", color: "#b45309" }}>
                      ⏳ Așteaptă Acceptul Clientului
                    </span>
                  )}
                </div>
              </div>
              {!isDone && (
                <div style={{ display: "flex", flexDirection: "column", gap: 6, alignItems: "flex-end" }}>
                  <div
                    role="button"
                    tabIndex={0}
                    className="pressable choose-button"
                    style={{ padding: "8px 12px", minHeight: 34, background: "var(--navy)", fontSize: 12 }}
                    onClick={() => setRescheduleTarget(bk)}
                  >
                    {busyId === bk.id ? "..." : "Reprogramează"}
                  </div>
                  <div style={{ display: "flex", gap: 4 }}>
                    <button
                      type="button"
                      className="chip-button"
                      style={{ fontSize: 10, padding: "4px 8px", background: "#dcfce7", color: "#166534", border: "none" }}
                      onClick={() => handleComplete(bk)}
                      title="Marchează lucrarea ca finalizată"
                    >
                      ✓ Finalizează
                    </button>
                    <button
                      type="button"
                      className="chip-button"
                      style={{ fontSize: 10, padding: "4px 8px", background: "#fee2e2", color: "#991b1b", border: "none" }}
                      onClick={() => handleNoShow(bk)}
                      title="Raportează client absent (No-Show)"
                    >
                      🚫 No-Show
                    </button>
                  </div>
                  {smsScheduled > 0 && (
                    <div
                      role="button"
                      tabIndex={0}
                      className="pressable"
                      style={{ fontSize: 10, color: "var(--blue)", fontFamily: "Inter:Bold", textDecoration: "underline" }}
                      onClick={() => handleTriggerSms(bk)}
                    >
                      Trimite SMS acum
                    </div>
                  )}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

import { useState } from "react"
import {
  api,
  type ApiBooking,
  type ApiCalendarDay,
  type ApiQuickSlot,
} from "../api"
import { SvgIcon } from "./SvgIcon"

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
  const [showManualModal, setShowManualModal] = useState(false)
  const [manualClientName, setManualClientName] = useState("")
  const [manualClientPhone, setManualClientPhone] = useState("+40 74")
  const [manualService, setManualService] = useState("Intervenție și reparație la domiciliu")
  const [manualNeighborhood, setManualNeighborhood] = useState("Hipodrom")
  const [manualAddress, setManualAddress] = useState("")
  const [manualPrice, setManualPrice] = useState(250)
  const [manualDuration, setManualDuration] = useState(60)
  const [manualSlotStart, setManualSlotStart] = useState<number | undefined>(quickSlots[0]?.start_at)
  const [manualSlotLabel, setManualSlotLabel] = useState<string>(quickSlots[0]?.full_label ?? "Mâine, 10:00")
  const [manualSaving, setManualSaving] = useState(false)

  const currentDay = days[selectedDayIdx] ?? days[0]
  const sibiuZones = ["Hipodrom", "Șelimbăr", "Turnișor", "Ștrand", "Vasile Aaron", "Centru Istoric"]

  const openManualForSlot = (startAt?: number, label?: string) => {
    if (startAt) setManualSlotStart(startAt)
    else if (quickSlots[0]) setManualSlotStart(quickSlots[0].start_at)
    if (label) setManualSlotLabel(label)
    else if (quickSlots[0]) setManualSlotLabel(quickSlots[0].full_label)
    setShowManualModal(true)
  }

  const handleCreateManualBooking = async () => {
    if (manualClientName.trim().length < 2) {
      onError("Date incomplete", "Introdu numele clientului (ex: Mircea Dobre).")
      return
    }
    if (manualClientPhone.replace(/\D/g, "").length < 9) {
      onError("Telefon invalid", "Introdu numărul de telefon al clientului pentru reminderele SMS (24h și 2h).")
      return
    }
    setManualSaving(true)
    try {
      await api.createManualProBooking({
        client_name: manualClientName.trim(),
        client_phone: manualClientPhone.trim(),
        service_name: manualService.trim() || "Intervenție telefonică (CRM)",
        neighborhood: manualNeighborhood,
        address: manualAddress.trim() || `${manualNeighborhood}, Sibiu`,
        price_ron: manualPrice,
        duration_minutes: manualDuration,
        start_at: manualSlotStart,
        slot_label: manualSlotLabel,
      })
      setShowManualModal(false)
      setManualClientName("")
      setManualAddress("")
      onNotice(
        `Lucrare telefonică adăugată în CRM (${manualSlotLabel}). Clientul ${manualClientName} a primit SMS-ul de confirmare, iar reminderele de 24h și 2h au fost programate.`,
      )
      onRefresh()
    } catch (e: any) {
      onError("Nu am putut salva programarea", e?.message ?? "Verifică datele și încearcă din nou.")
    } finally {
      setManualSaving(false)
    }
  }

  const handleQuickReschedule = async (
    booking: ApiBooking,
    slot: { start_at?: number; shift_hours?: number; label: string },
  ) => {
    setBusyId(booking.id)
    try {
      await api.reschedule(booking.id, {
        start_at: slot.start_at,
        shift_hours: slot.shift_hours,
        slot_label: slot.label,
      })
      setRescheduleTarget(null)
      onNotice(`Programare mutată pe ${slot.label}. Reminderele SMS de 24h și 2h au fost actualizate.`)
      onRefresh()
    } catch (e: any) {
      onError("Conflict în calendar", e?.message ?? "Nu am putut reprograma.")
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
          ? `Am expediat ${count} remindere SMS (24h și 2h) către ${booking.client.name}.`
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
      onNotice(`Lucrarea #${booking.id.slice(0, 8)} a fost marcată ca finalizată.`)
      onRefresh()
    } catch (e: any) {
      onError("Eroare finalizare", e?.message ?? "Nu am putut finaliza lucrarea.")
    } finally {
      setBusyId(null)
    }
  }

  const handleNoShow = async (booking: ApiBooking) => {
    if (!window.confirm(`Înregistrezi neprezentare (No-Show) pentru ${booking.client.name}?`)) return
    setBusyId(booking.id)
    try {
      await api.markNoShow(booking.id, "Clientul nu a răspuns la sosire")
      onNotice(`Programarea #${booking.id.slice(0, 8)} a fost înregistrată ca neprezentare (No-Show).`)
      onRefresh()
    } catch (e: any) {
      onError("Eroare No-Show", e?.message ?? "Nu am putut înregistra statusul.")
    } finally {
      setBusyId(null)
    }
  }

  if (!currentDay) return null

  return (
    <div className="section-block" style={{ padding: 16 }}>
      <div className="section-heading" style={{ marginTop: 0 }}>
        <div>
          Calendar teren B2B <span className="count">2-Click</span>
        </div>
        <small>Blocare automată · SMS 24h / 2h</small>
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

      {/* CRM Mode: Add Phone Call Client + Auto SMS 24h/2h */}
      <div style={{ margin: "12px 0" }}>
        <div
          role="button"
          tabIndex={0}
          className="pressable primary-button field-btn-giant"
          style={{ marginTop: 0 }}
          onClick={() => openManualForSlot()}
        >
          <SvgIcon name="phone" size={16} />
          <span>Adaugă programare telefonică (CRM · SMS)</span>
        </div>
      </div>

      {/* Fast Field CRM Form for Phone Bookings */}
      {showManualModal && (
        <div className="estimate-offer-box" style={{ marginBottom: 16 }}>
          <div className="estimate-offer-head">
            <span>Programare telefonică în calendarul B2B</span>
            <span
              className="pressable"
              onClick={() => setShowManualModal(false)}
              style={{ color: "var(--navy)", fontWeight: 600, fontSize: 12 }}
            >
              Închide
            </span>
          </div>
          <p style={{ fontSize: 12, color: "var(--text-secondary)", margin: "4px 0 12px" }}>
            Înregistrează rapid un client care a sunat direct. Slotul se blochează în agendă și se programează automat
            SMS-ul de confirmare și reminderele la 24h și 2h.
          </p>

          <div style={{ display: "grid", gap: 12 }}>
            <div>
              <small style={{ fontSize: 12, fontWeight: 500, color: "var(--text-secondary)" }}>
                1. Intervalul din agendă
              </small>
              <div className="chip-row" style={{ marginTop: 6 }}>
                {quickSlots.slice(0, 6).map((qs) => (
                  <div
                    key={qs.start_at}
                    role="button"
                    tabIndex={0}
                    className={`pressable quick-chip ${manualSlotStart === qs.start_at ? "active" : ""}`}
                    onClick={() => {
                      setManualSlotStart(qs.start_at)
                      setManualSlotLabel(qs.full_label)
                    }}
                  >
                    <SvgIcon name="calendar" size={13} />
                    <span>{qs.label}</span>
                  </div>
                ))}
              </div>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
              <div>
                <small style={{ fontSize: 12, fontWeight: 500, color: "var(--text-secondary)" }}>2. Nume client</small>
                <div className="input-shell" style={{ marginTop: 4 }}>
                  <input
                    className="field"
                    placeholder="Ex: Mircea Dobre"
                    value={manualClientName}
                    onChange={(e) => setManualClientName(e.target.value)}
                  />
                </div>
              </div>
              <div>
                <small style={{ fontSize: 12, fontWeight: 500, color: "var(--text-secondary)" }}>
                  3. Telefon client (SMS)
                </small>
                <div className="input-shell" style={{ marginTop: 4 }}>
                  <input
                    className="field"
                    placeholder="+40 742 889 102"
                    value={manualClientPhone}
                    onChange={(e) => setManualClientPhone(e.target.value)}
                  />
                </div>
              </div>
            </div>

            <div>
              <small style={{ fontSize: 12, fontWeight: 500, color: "var(--text-secondary)" }}>
                4. Cartier și adresă în Sibiu
              </small>
              <div className="chip-row" style={{ marginTop: 6 }}>
                {sibiuZones.map((z) => (
                  <div
                    key={z}
                    role="button"
                    tabIndex={0}
                    className={`pressable quick-chip ${manualNeighborhood === z ? "active" : ""}`}
                    onClick={() => setManualNeighborhood(z)}
                  >
                    {z}
                  </div>
                ))}
              </div>
              <div className="input-shell" style={{ marginTop: 8 }}>
                <input
                  className="field"
                  placeholder={`Adresă opțională (ex: Str. Rahovei nr. 14, ${manualNeighborhood})`}
                  value={manualAddress}
                  onChange={(e) => setManualAddress(e.target.value)}
                />
              </div>
            </div>

            <div>
              <small style={{ fontSize: 12, fontWeight: 500, color: "var(--text-secondary)" }}>
                5. Lucrare și tarif estimat (RON)
              </small>
              <div className="input-shell" style={{ marginTop: 4 }}>
                <input
                  className="field"
                  placeholder="Ex: Înlocuire robinet trecere / Revizie centrală"
                  value={manualService}
                  onChange={(e) => setManualService(e.target.value)}
                />
              </div>
              <div className="chip-row" style={{ marginTop: 8 }}>
                {[150, 200, 250, 350, 500].map((p) => (
                  <div
                    key={p}
                    role="button"
                    tabIndex={0}
                    className={`pressable quick-chip tabular ${manualPrice === p ? "active" : ""}`}
                    onClick={() => setManualPrice(p)}
                  >
                    {p} RON
                  </div>
                ))}
                {[60, 90, 120].map((m) => (
                  <div
                    key={m}
                    role="button"
                    tabIndex={0}
                    className={`pressable quick-chip tabular ${manualDuration === m ? "active" : ""}`}
                    onClick={() => setManualDuration(m)}
                  >
                    {m} min
                  </div>
                ))}
              </div>
            </div>

            <div
              role="button"
              tabIndex={0}
              className="pressable primary-button field-btn-giant"
              style={{ marginTop: 4 }}
              onClick={manualSaving ? undefined : handleCreateManualBooking}
            >
              <SvgIcon name="check" size={16} />
              <span>
                {manualSaving
                  ? "Se blochează slotul și se trimite SMS..."
                  : `Blochează ${manualSlotLabel} și trimite SMS`}
              </span>
            </div>
          </div>
        </div>
      )}

      {/* 2-Click Instant Reschedule Bar */}
      {rescheduleTarget && (
        <div className="estimate-offer-box" style={{ marginBottom: 12 }}>
          <div className="estimate-offer-head">
            <span>Reprogramare rapidă · {rescheduleTarget.client.name}</span>
            <span
              className="pressable"
              onClick={() => setRescheduleTarget(null)}
              style={{ color: "var(--navy)", fontWeight: 600, fontSize: 12 }}
            >
              Închide
            </span>
          </div>
          <p style={{ fontSize: 12, color: "var(--text-secondary)", margin: "4px 0 8px" }}>
            Lucrare: <strong>{rescheduleTarget.service_name}</strong> ({rescheduleTarget.neighborhood ?? "Sibiu"}).
            Alege noul interval pentru a muta programarea și a actualiza automat SMS-ul clientului:
          </p>
          <div className="chip-row">
            <div
              role="button"
              tabIndex={0}
              className="pressable quick-chip active"
              onClick={() => handleQuickReschedule(rescheduleTarget, { shift_hours: 1, label: "Decalat +1 oră" })}
            >
              <SvgIcon name="clock" size={13} />
              <span>+1 oră</span>
            </div>
            <div
              role="button"
              tabIndex={0}
              className="pressable quick-chip"
              onClick={() => handleQuickReschedule(rescheduleTarget, { shift_hours: 2, label: "Decalat +2 ore" })}
            >
              <SvgIcon name="clock" size={13} />
              <span>+2 ore</span>
            </div>
            {quickSlots.slice(0, 5).map((qs) => (
              <div
                key={qs.start_at}
                role="button"
                tabIndex={0}
                className="pressable quick-chip"
                onClick={() => handleQuickReschedule(rescheduleTarget, { start_at: qs.start_at, label: qs.full_label })}
              >
                <SvgIcon name="calendar" size={13} />
                <span>{qs.label}</span>
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
            const isPast = slot.status === "past"
            return (
              <div
                key={slot.hour}
                role={isPast ? undefined : "button"}
                tabIndex={isPast ? -1 : 0}
                className={`cal-slot-row slot-free ${isPast ? "" : "pressable"}`}
                onClick={
                  isPast
                    ? undefined
                    : () => openManualForSlot(slot.start_at, slot.label || `${currentDay.day_name}, ${slot.hour}`)
                }
              >
                <div className="cal-slot-hour">{slot.hour}</div>
                <div className="grow">
                  <small style={{ color: "var(--text-muted)", fontSize: 12 }}>
                    {isPast ? "Interval încheiat" : "Interval disponibil · adaugă programare"}
                  </small>
                </div>
                <span
                  style={{
                    fontSize: 11,
                    color: isPast ? "var(--text-muted)" : "var(--navy)",
                    fontFamily: "var(--font-mono)",
                    fontWeight: 500,
                  }}
                >
                  {isPast ? "Închis" : "+ Rezervă"}
                </span>
              </div>
            )
          }

          const isEst = bk.status === "estimated"
          const isDone = bk.status === "completed"
          const smsScheduled = (bk.sms_reminders ?? []).filter((s) => s.status === "scheduled").length
          const smsSent = (bk.sms_reminders ?? []).filter(
            (s) => s.status === "sent" || s.status === "delivered",
          ).length

          return (
            <div
              key={slot.hour}
              className={`cal-slot-row ${isEst ? "slot-estimated" : "slot-accepted"}`}
            >
              <div className="cal-slot-hour">
                {slot.hour}
                <small style={{ display: "block", fontSize: 11, color: "var(--text-muted)", fontWeight: 400 }}>
                  {bk.quote_duration ?? "60 min"}
                </small>
              </div>
              <div className="grow" style={{ minWidth: 0 }}>
                <strong style={{ fontSize: 13, display: "block" }} className="tabular">
                  {bk.service_name} · {bk.quote_price ?? "—"} RON
                </strong>
                <small style={{ color: "var(--text-secondary)", fontSize: 12, marginTop: 2, display: "block" }}>
                  {bk.client.name} · {bk.neighborhood ?? "Sibiu"}
                  {bk.client_address
                    ? ` · ${bk.client_address}`
                    : bk.client.address
                      ? ` · ${bk.client.address}`
                      : ""}
                  {bk.client_phone
                    ? ` · ${bk.client_phone}`
                    : bk.client.phone
                      ? ` · ${bk.client.phone}`
                      : ""}
                </small>

                {/* Quick Field Navigation & Direct Client Call */}
                {!isDone && (
                  <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 6 }}>
                    {(bk.client_phone || bk.client.phone) && (
                      <a
                        href={`tel:${(bk.client_phone || bk.client.phone)!.replace(/\s+/g, "")}`}
                        className="chip-button"
                        style={{ textDecoration: "none", minHeight: 28, padding: "2px 8px", fontSize: 11 }}
                      >
                        <SvgIcon name="phone" size={12} />
                        <span>Apel client</span>
                      </a>
                    )}
                    <a
                      href={`https://waze.com/ul?q=${encodeURIComponent((bk.client_address || bk.client.address || bk.neighborhood || "Sibiu") + ", Sibiu, Romania")}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="chip-button"
                      style={{ textDecoration: "none", minHeight: 28, padding: "2px 8px", fontSize: 11 }}
                    >
                      <SvgIcon name="navigation" size={12} />
                      <span>Waze</span>
                    </a>
                    <a
                      href={`https://www.google.com/maps/search/?api=1&query=${encodeURIComponent((bk.client_address || bk.client.address || bk.neighborhood || "Sibiu") + ", Sibiu, Romania")}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="chip-button"
                      style={{ textDecoration: "none", minHeight: 28, padding: "2px 8px", fontSize: 11 }}
                    >
                      <SvgIcon name="pin" size={12} />
                      <span>Hărți</span>
                    </a>
                  </div>
                )}

                <div className="sms-pill-row">
                  <span className={`sms-pill ${smsSent > 0 ? "sent" : ""}`}>
                    SMS livrate: {smsSent}
                  </span>
                  {smsScheduled > 0 && (
                    <span className="sms-pill">
                      În coadă (24h/2h): {smsScheduled}
                    </span>
                  )}
                  {isEst && (
                    <span className="sms-pill" style={{ background: "var(--soft-amber)", color: "var(--amber)" }}>
                      Așteaptă confirmarea clientului
                    </span>
                  )}
                </div>
              </div>
              {!isDone && (
                <div className="cal-slot-actions" style={{ display: "flex", flexDirection: "column", gap: 6, alignItems: "flex-end" }}>
                  <div
                    role="button"
                    tabIndex={0}
                    className="pressable choose-button"
                    style={{ marginTop: 0 }}
                    onClick={() => setRescheduleTarget(bk)}
                  >
                    {busyId === bk.id ? "..." : "Reprogramează"}
                  </div>
                  <div style={{ display: "flex", gap: 4 }}>
                    <button
                      type="button"
                      className="chip-button"
                      style={{
                        minHeight: 28,
                        fontSize: 11,
                        padding: "2px 8px",
                        background: "var(--soft-green)",
                        color: "var(--green)",
                        borderColor: "rgba(21, 128, 61, 0.22)",
                      }}
                      onClick={() => handleComplete(bk)}
                      title="Marchează lucrarea ca finalizată"
                    >
                      Finalizat
                    </button>
                    <button
                      type="button"
                      className="chip-button"
                      style={{
                        minHeight: 28,
                        fontSize: 11,
                        padding: "2px 8px",
                        background: "var(--soft-red)",
                        color: "var(--red)",
                        borderColor: "rgba(220, 38, 38, 0.22)",
                      }}
                      onClick={() => handleNoShow(bk)}
                      title="Raportează client absent (No-Show)"
                    >
                      Absent
                    </button>
                  </div>
                  {smsScheduled > 0 && (
                    <div
                      role="button"
                      tabIndex={0}
                      className="pressable"
                      style={{ fontSize: 11, color: "var(--navy)", fontWeight: 500 }}
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

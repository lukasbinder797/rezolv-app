import { useState } from "react"
import {
  api,
  type ApiBooking,
  type ApiCalendarDay,
  type ApiQuickSlot,
} from "../api"
import { SvgIcon } from "./SvgIcon"
import {
  addBookingToNativeCalendar,
  syncAllBookingsToNativeCalendar,
} from "../utils/calendarAndGeo"

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
    <div className="section-block cal-section-container">
      <div className="cal-section-header">
        <div className="cal-header-title-row">
          <div className="cal-title-wrap">
            <h3 className="cal-title">Calendar teren B2B</h3>
            <span className="cal-badge-2click nowrap">2-Click</span>
          </div>
          <span className="cal-header-sub nowrap">Blocare automată · SMS 24h / 2h</span>
        </div>
      </div>

      {/* 5-Day Selector Strip */}
      <div className="cal-day-strip">
        {days.map((d, idx) => {
          const busyCount = d.slots.filter((s) => s.booking && s.booking.status !== "completed").length
          const shortDay = d.day_name === "Sâmbătă" ? "Sâm" : d.day_name === "Duminică" ? "Dum" : d.day_name
          return (
            <div
              key={d.date_iso}
              role="button"
              tabIndex={0}
              className={`pressable cal-day-pill ${idx === selectedDayIdx ? "active" : ""}`}
              onClick={() => setSelectedDayIdx(idx)}
            >
              <strong>{shortDay}</strong>
              <small>{d.date_short}</small>
              <i>{busyCount > 0 ? `${busyCount} lucr.` : "Liber"}</i>
            </div>
          )
        })}
      </div>

      {/* CRM Mode: Add Phone Call Client + Auto SMS 24h/2h + 1-Click Native Phone Calendar Sync */}
      <div className="cal-crm-actions">
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
        <button
          type="button"
          className="outline-button cal-sync-btn"
          onClick={() => {
            const allBooked = days
              .flatMap((d) => d.slots.map((s) => s.booking).filter((b): b is ApiBooking => Boolean(b)))
              .filter((b, i, arr) => arr.findIndex((x) => x.id === b.id) === i)
            if (!allBooked.length) {
              onError("Agendă goală", "Nu există încă lucrări programate pentru export în calendar.")
              return
            }
            syncAllBookingsToNativeCalendar(allBooked, "pro")
          }}
        >
          <SvgIcon name="calendar" size={15} />
          <span className="nowrap">Sincronizează agenda în Calendar (.ics)</span>
        </button>
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
              <small style={{ fontSize: 12, fontWeight: 500, color: "var(--text-secondary)", display: "block", marginBottom: 6 }}>
                4. Adresa intervenției în Sibiu
              </small>
              <div className="chip-row" style={{ marginBottom: 8 }}>
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
              <div className="input-shell">
                <input
                  className="field"
                  placeholder={`Ex: Str. Rahovei nr. 14, bl. 2, ap. 8, ${manualNeighborhood}, Sibiu`}
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
                className={`cal-slot-free-row ${isPast ? "is-past" : "pressable"}`}
                onClick={
                  isPast
                    ? undefined
                    : () => openManualForSlot(slot.start_at, slot.label || `${currentDay.day_name}, ${slot.hour}`)
                }
              >
                <div className="cal-slot-free-hour">{slot.hour}</div>
                <div className="cal-slot-free-text">
                  {isPast ? "Interval încheiat" : "Interval disponibil · adaugă programare"}
                </div>
                <div className="cal-slot-free-badge nowrap">
                  {isPast ? "Închis" : "+ Rezervă"}
                </div>
              </div>
            )
          }

          const isEst = bk.status === "estimated"
          const isDone = bk.status === "completed"
          const smsScheduled = (bk.sms_reminders ?? []).filter((s) => s.status === "scheduled").length
          const smsSent = (bk.sms_reminders ?? []).filter(
            (s) => s.status === "sent" || s.status === "delivered",
          ).length
          const clientPhone = bk.client_phone || bk.client.phone
          const clientAddr = bk.client_address || bk.client.address || ""
          const rawAddr = (clientAddr || bk.neighborhood || "Sibiu").trim()
          const routeDest = /sibiu/i.test(rawAddr) ? `${rawAddr}, România` : `${rawAddr}, Sibiu, România`

          return (
            <div
              key={slot.hour}
              className={`cal-booking-card ${isEst ? "slot-estimated" : "slot-accepted"}`}
            >
              {/* Card Header: Hour, duration, status on left; Price on right */}
              <div className="cal-card-head">
                <div className="cal-card-head-left">
                  <span className="cal-card-hour">{slot.hour}</span>
                  <span className="cal-card-duration">({bk.quote_duration ?? "60 min"})</span>
                  <span className={`cal-card-status-badge ${isEst ? "status-est" : "status-ok"} nowrap`}>
                    {isEst ? "Deviz trimis" : "Confirmat"}
                  </span>
                </div>
                <div className="cal-card-price tabular nowrap">
                  {bk.quote_price ?? "—"} RON
                </div>
              </div>

              {/* Card Body: Service name, client name and full address */}
              <div className="cal-card-body">
                <div className="cal-card-service">{bk.service_name}</div>
                <div className="cal-card-client-line">
                  <strong>{bk.client.name}</strong>
                  <span className="cal-card-sep">·</span>
                  <span>
                    {bk.neighborhood ?? "Sibiu"}
                    {clientAddr ? ` · ${clientAddr}` : ""}
                  </span>
                </div>

                {/* Quick Route & Contact chips */}
                {!isDone && (
                  <div className="cal-chips-row">
                    {clientPhone && (
                      <a
                        href={`tel:${clientPhone.replace(/\s+/g, "")}`}
                        className="cal-chip-btn"
                      >
                        <SvgIcon name="phone" size={12} />
                        <span className="nowrap">Apel client</span>
                      </a>
                    )}
                    <a
                      href={`https://waze.com/ul?q=${encodeURIComponent(routeDest)}&navigate=yes`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="cal-chip-btn"
                    >
                      <SvgIcon name="navigation" size={12} />
                      <span className="nowrap">Rută Waze</span>
                    </a>
                    <a
                      href={`https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(routeDest)}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="cal-chip-btn"
                    >
                      <SvgIcon name="pin" size={12} />
                      <span className="nowrap">Rută Maps</span>
                    </a>
                    <button
                      type="button"
                      onClick={() => addBookingToNativeCalendar(bk, "pro")}
                      className="cal-chip-btn cal-chip-cal"
                    >
                      <SvgIcon name="calendar" size={12} />
                      <span className="nowrap">În Calendar</span>
                    </button>
                  </div>
                )}

                {/* SMS Status Badges */}
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

              {/* Card Footer: Pro Management Actions */}
              {!isDone && (
                <div className="cal-card-footer">
                  <div className="cal-footer-left-group">
                    <button
                      type="button"
                      className="cal-footer-btn-resched"
                      onClick={() => setRescheduleTarget(bk)}
                    >
                      <SvgIcon name="clock" size={12} />
                      <span className="nowrap">{busyId === bk.id ? "..." : "Reprogramează"}</span>
                    </button>
                    {smsScheduled > 0 && (
                      <button
                        type="button"
                        className="cal-footer-btn-sms"
                        onClick={() => handleTriggerSms(bk)}
                        title="Trimite SMS manual acum"
                      >
                        <SvgIcon name="phone" size={11} />
                        <span className="nowrap">Trimite SMS</span>
                      </button>
                    )}
                  </div>
                  <div className="cal-footer-right-group">
                    <button
                      type="button"
                      className="cal-footer-btn-complete"
                      onClick={() => handleComplete(bk)}
                      title="Marchează lucrarea ca finalizată"
                    >
                      <SvgIcon name="check" size={12} />
                      <span className="nowrap">Finalizat</span>
                    </button>
                    <button
                      type="button"
                      className="cal-footer-btn-noshow"
                      onClick={() => handleNoShow(bk)}
                      title="Raportează client absent (No-Show)"
                    >
                      <SvgIcon name="close" size={12} />
                      <span className="nowrap">Absent</span>
                    </button>
                  </div>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

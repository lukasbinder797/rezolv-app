import type { ApiBooking } from "../api"

// ============================================================================
// NATIVE PHONE CALENDAR (.ICS RFC 5545 + GOOGLE CALENDAR + IOS BRIDGE)
// ============================================================================

function formatIcsUtc(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0")
  return (
    date.getUTCFullYear() +
    pad(date.getUTCMonth() + 1) +
    pad(date.getUTCDate()) +
    "T" +
    pad(date.getUTCHours()) +
    pad(date.getUTCMinutes()) +
    pad(date.getUTCSeconds()) +
    "Z"
  )
}

function escapeIcsText(raw: string): string {
  return (raw || "")
    .replace(/\\/g, "\\\\")
    .replace(/;/g, "\\;")
    .replace(/,/g, "\\,")
    .replace(/\r?\n/g, "\\n")
}

export function resolveBookingStartEnd(booking: ApiBooking): { start: Date; end: Date } {
  const durationMin = booking.duration_minutes || booking.estimate?.duration_minutes || 90
  const now = new Date()

  if (booking.scheduled_start_at && booking.scheduled_start_at > 1000000000) {
    const start = new Date(booking.scheduled_start_at * 1000)
    const end =
      booking.scheduled_end_at && booking.scheduled_end_at > booking.scheduled_start_at
        ? new Date(booking.scheduled_end_at * 1000)
        : new Date(start.getTime() + durationMin * 60 * 1000)
    return { start, end }
  }

  // Parse human-readable Romanian label (e.g. "Mâine, 09:00–12:00", "Sâmbătă, 24 Oct, 11:00–12:30")
  const label = (booking.scheduled_for || booking.time_label || "").toLowerCase()
  const base = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 10, 0, 0)
  if (!label.includes("azi") && !label.includes("urgent")) {
    base.setDate(base.getDate() + 1)
  }

  const timeMatch = label.match(/(\d{1,2}):(\d{2})(?:\s*[–-]\s*(\d{1,2}):(\d{2}))?/)
  if (timeMatch) {
    const sh = parseInt(timeMatch[1], 10)
    const sm = parseInt(timeMatch[2], 10)
    base.setHours(sh, sm, 0, 0)
    if (timeMatch[3] && timeMatch[4]) {
      const eh = parseInt(timeMatch[3], 10)
      const em = parseInt(timeMatch[4], 10)
      const end = new Date(base)
      end.setHours(eh, em, 0, 0)
      if (end > base) return { start: base, end }
    }
  }

  const end = new Date(base.getTime() + durationMin * 60 * 1000)
  return { start: base, end }
}

function buildVEventBlock(booking: ApiBooking, role: "client" | "pro"): string {
  const { start, end } = resolveBookingStartEnd(booking)
  const nowStamp = formatIcsUtc(new Date())
  const dtStart = formatIcsUtc(start)
  const dtEnd = formatIcsUtc(end)

  const proName = booking.professional?.name || "Meșter REZOLV"
  const proCompany = booking.professional?.company_name ? ` (${booking.professional.company_name})` : ""
  const clientName = booking.client?.name || "Client Sibiu"
  const summary =
    role === "pro"
      ? `Lucrare REZOLV: ${booking.service_name} — ${clientName}`
      : `REZOLV Sibiu: ${booking.service_name} (${proName})`

  const locationStr =
    booking.client_address ||
    booking.client?.address ||
    `${booking.neighborhood || booking.client?.neighborhood || "Hipodrom"}, Sibiu, România`

  const priceStr = booking.quote_price
    ? `${booking.quote_price} RON`
    : booking.price_label || "Deviz la fața locului"

  const contactPhone =
    role === "pro"
      ? booking.client_phone || booking.client?.phone || "+40 721 555 010"
      : booking.professional?.phone || "+40 740 555 084"

  const notes = booking.pro_notes || booking.estimate?.pro_notes || booking.description || ""
  const descLines = [
    `Serviciu: ${booking.service_name} (${booking.category || "Intervenție Sibiu"})`,
    role === "pro" ? `Client: ${clientName}` : `Meșter verificat: ${proName}${proCompany}`,
    `Telefon contact: ${contactPhone}`,
    `Tarif: ${priceStr} (0% comision · plată direct la finalizare)`,
    `Adresă intervenție: ${locationStr}`,
    notes ? `Notă tehnică: ${notes}` : "",
  ].filter(Boolean)

  return [
    "BEGIN:VEVENT",
    `UID:rezolv-${booking.id}@rezolv.ro`,
    `DTSTAMP:${nowStamp}`,
    `DTSTART:${dtStart}`,
    `DTEND:${dtEnd}`,
    `SUMMARY:${escapeIcsText(summary)}`,
    `LOCATION:${escapeIcsText(locationStr)}`,
    `DESCRIPTION:${escapeIcsText(descLines.join("\n"))}`,
    "STATUS:CONFIRMED",
    "BEGIN:VALARM",
    "TRIGGER:-PT24H",
    "ACTION:DISPLAY",
    `DESCRIPTION:${escapeIcsText(`Reminder 24h REZOLV Sibiu: Mâine are loc lucrarea „${booking.service_name}”`)}`,
    "END:VALARM",
    "BEGIN:VALARM",
    "TRIGGER:-PT2H",
    "ACTION:DISPLAY",
    `DESCRIPTION:${escapeIcsText(`Reminder 2h REZOLV Sibiu: Intervenția „${booking.service_name}” începe în 2 ore`)}`,
    "END:VALARM",
    "END:VEVENT",
  ].join("\r\n")
}

export function buildBookingIcs(booking: ApiBooking, role: "client" | "pro" = "client"): string {
  return [
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//REZOLV Sibiu//B2B Field Dispatch//RO",
    "CALSCALE:GREGORIAN",
    "METHOD:PUBLISH",
    "X-WR-CALNAME:REZOLV Sibiu Programări",
    "X-WR-TIMEZONE:Europe/Bucharest",
    buildVEventBlock(booking, role),
    "END:VCALENDAR",
  ].join("\r\n")
}

export function buildMultiBookingIcs(bookings: ApiBooking[], role: "client" | "pro" = "pro"): string {
  const events = bookings.map((b) => buildVEventBlock(b, role)).join("\r\n")
  return [
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//REZOLV Sibiu//B2B Field Dispatch//RO",
    "CALSCALE:GREGORIAN",
    "METHOD:PUBLISH",
    "X-WR-CALNAME:Agenda B2B REZOLV Sibiu",
    "X-WR-TIMEZONE:Europe/Bucharest",
    events,
    "END:VCALENDAR",
  ].join("\r\n")
}

export function buildGoogleCalendarUrl(booking: ApiBooking, role: "client" | "pro" = "client"): string {
  const { start, end } = resolveBookingStartEnd(booking)
  const dates = `${formatIcsUtc(start)}/${formatIcsUtc(end)}`
  const proName = booking.professional?.name || "Meșter REZOLV"
  const clientName = booking.client?.name || "Client Sibiu"
  const title =
    role === "pro"
      ? `Lucrare REZOLV: ${booking.service_name} — ${clientName}`
      : `REZOLV Sibiu: ${booking.service_name} (${proName})`
  const location =
    booking.client_address ||
    booking.client?.address ||
    `${booking.neighborhood || booking.client?.neighborhood || "Hipodrom"}, Sibiu, România`
  const priceStr = booking.quote_price ? `${booking.quote_price} RON` : booking.price_label || ""
  const details = `Serviciu: ${booking.service_name}\nTarif: ${priceStr} (0% comision)\nAdresă: ${location}`

  const params = new URLSearchParams({
    action: "TEMPLATE",
    text: title,
    dates,
    location,
    details,
  })
  return `https://calendar.google.com/calendar/render?${params.toString()}`
}

function triggerIcsDownloadOrSheet(icsContent: string, filename: string) {
  try {
    const w = window as any
    if (w.webkit?.messageHandlers?.rezolvNative) {
      w.webkit.messageHandlers.rezolvNative.postMessage({
        type: "notify",
        title: "Calendar Nativ iOS",
        body: "Programarea REZOLV Sibiu (cu alarme la 24h și 2h) a fost pregătită pentru Calendar.",
      })
    }
  } catch {
    // ignore
  }

  const isIos =
    typeof navigator !== "undefined" &&
    (/iPad|iPhone|iPod/.test(navigator.userAgent) ||
      (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1))

  if (isIos) {
    // On iOS Safari & WebClip, navigating to a data:text/calendar URI invokes the native Apple Calendar sheet directly
    const dataUri = "data:text/calendar;charset=utf-8," + encodeURIComponent(icsContent)
    const link = document.createElement("a")
    link.href = dataUri
    link.download = filename
    document.body.appendChild(link)
    link.click()
    link.remove()
    return
  }

  const blob = new Blob([icsContent], { type: "text/calendar;charset=utf-8" })
  const url = URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 5000)
}

export function addBookingToNativeCalendar(booking: ApiBooking, role: "client" | "pro" = "client"): void {
  const ics = buildBookingIcs(booking, role)
  const safeId = (booking.id || "programare").replace(/[^a-zA-Z0-9_-]/g, "")
  triggerIcsDownloadOrSheet(ics, `rezolv-sibiu-${safeId}.ics`)
}

export function syncAllBookingsToNativeCalendar(bookings: ApiBooking[], role: "client" | "pro" = "pro"): void {
  if (!bookings.length) return
  const ics = buildMultiBookingIcs(bookings, role)
  triggerIcsDownloadOrSheet(ics, "agenda-rezolv-sibiu.ics")
}

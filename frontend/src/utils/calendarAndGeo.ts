import type { ApiBooking } from "../api"

export interface SibiuGeoPoint {
  lat: number
  lng: number
  neighborhood: string
  streetAddress: string
  formattedAddress: string
  accuracyMeters?: number
  source: "gps_live" | "map_pin" | "nominatim"
}

export interface SibiuZoneSpec {
  name: string
  lat: number
  lng: number
  streets: string[]
}

export const SIBIU_ZONES_GEO: SibiuZoneSpec[] = [
  {
    name: "Hipodrom",
    lat: 45.7785,
    lng: 24.1612,
    streets: [
      "Bd. Mihai Viteazu",
      "Str. Rahovei",
      "Aleea Biruinței",
      "Str. Nicolae Iorga",
      "Calea Cisnădiei",
      "Str. Oștirii",
    ],
  },
  {
    name: "Șelimbăr",
    lat: 45.7712,
    lng: 24.1865,
    streets: [
      "Str. Pictor Brana",
      "Str. Doamna Stanca",
      "Str. Mihai Viteazu",
      "Str. Octavian Goga",
      "Str. Trifoiului",
    ],
  },
  {
    name: "Turnișor",
    lat: 45.7924,
    lng: 24.1148,
    streets: [
      "Șos. Alba Iulia",
      "Str. E. A. Bieltz",
      "Str. Frigoriferului",
      "Str. Graurului",
      "Str. Călțun",
    ],
  },
  {
    name: "Ștrand",
    lat: 45.7868,
    lng: 24.1325,
    streets: [
      "Str. Maramureșului",
      "Str. Bihorului",
      "Str. Sălajului",
      "Str. Gorjului",
      "Str. Doljului",
    ],
  },
  {
    name: "Vasile Aaron",
    lat: 45.7819,
    lng: 24.1738,
    streets: [
      "Str. Semaforului",
      "Str. Șureanu",
      "Str. Negoveanu",
      "Str. Oașa",
      "Str. Muncel",
    ],
  },
  {
    name: "Centru Istoric",
    lat: 45.7965,
    lng: 24.1521,
    streets: [
      "Str. Nicolae Bălcescu",
      "Piața Mare",
      "Str. Cetății",
      "Str. Mitropoliei",
      "Calea Dumbrăvii",
      "Str. Tribunei",
    ],
  },
  {
    name: "Valea Aurie",
    lat: 45.7704,
    lng: 24.1292,
    streets: [
      "Str. Luduș",
      "Str. Poiana",
      "Str. Valea Aurie",
      "Str. Agârbiciu",
      "Calea Poplăcii",
    ],
  },
  {
    name: "Gușterița",
    lat: 45.8085,
    lng: 24.1795,
    streets: [
      "Str. Podului",
      "Str. Mălinului",
      "Str. Salcâmilor",
      "Str. Răchitei",
    ],
  },
  {
    name: "Lazaret",
    lat: 45.7942,
    lng: 24.1745,
    streets: [
      "Str. Henri Coandă",
      "Str. Mașiniștilor",
      "Str. Oțelarilor",
      "Str. Luceafărului",
    ],
  },
  {
    name: "Cisnădie",
    lat: 45.7128,
    lng: 24.1518,
    streets: [
      "Str. Arhitecților",
      "Str. Liviu Ciulei",
      "Str. Tiberiu Ricci",
      "Str. Cetății Cisnădie",
    ],
  },
]

// Bounding box of the interactive Sibiu map canvas
export const SIBIU_MAP_BOUNDS = {
  minLat: 45.764,
  maxLat: 45.806,
  minLng: 24.108,
  maxLng: 24.194,
}

export function getZoneCenter(neighborhood?: string): { lat: number; lng: number } {
  const found = SIBIU_ZONES_GEO.find(
    (z) => z.name.toLowerCase() === (neighborhood || "").toLowerCase(),
  )
  return found ? { lat: found.lat, lng: found.lng } : { lat: 45.7829, lng: 24.1566 }
}

/**
 * Deterministic spatial resolver that maps any (lat, lng) coordinate to the closest
 * Sibiu neighborhood, street name, and house number.
 */
export function resolveSibiuPoint(
  lat: number,
  lng: number,
  source: SibiuGeoPoint["source"] = "map_pin",
  accuracyMeters = 14,
): SibiuGeoPoint {
  let nearest = SIBIU_ZONES_GEO[0]
  let bestDist = Infinity
  for (const z of SIBIU_ZONES_GEO) {
    const dLat = lat - z.lat
    const dLng = lng - z.lng
    const d = dLat * dLat + dLng * dLng
    if (d < bestDist) {
      bestDist = d
      nearest = z
    }
  }

  // Deterministic street & number based on fine coordinate hash
  const hashA = Math.abs(Math.round(lat * 10000) * 31 + Math.round(lng * 10000) * 17)
  const street = nearest.streets[hashA % nearest.streets.length]
  const houseNo = (hashA % 78) + 2
  const streetAddress = `${street} nr. ${houseNo}`
  const formattedAddress = `${streetAddress}, ${nearest.name}, Sibiu`

  return {
    lat: Number(lat.toFixed(5)),
    lng: Number(lng.toFixed(5)),
    neighborhood: nearest.name,
    streetAddress,
    formattedAddress,
    accuracyMeters,
    source,
  }
}

/**
 * Reverse geocode coordinates into a Sibiu address. Uses OpenStreetMap Nominatim
 * if coordinates are in Sibiu County and network is available, with instant spatial fallback.
 */
export async function reverseGeocodeSibiu(
  lat: number,
  lng: number,
  source: SibiuGeoPoint["source"] = "gps_live",
  accuracyMeters = 12,
): Promise<SibiuGeoPoint> {
  const inSibiuArea = lat >= 45.68 && lat <= 45.86 && lng >= 24.05 && lng <= 24.25
  const normLat = inSibiuArea ? lat : 45.7785 + ((Math.abs(Math.sin(lat * 123.45)) - 0.5) * 0.018)
  const normLng = inSibiuArea ? lng : 24.1612 + ((Math.abs(Math.cos(lng * 123.45)) - 0.5) * 0.024)

  const basePoint = resolveSibiuPoint(normLat, normLng, source, accuracyMeters)

  if (inSibiuArea && typeof window !== "undefined" && navigator.onLine) {
    try {
      const ctrl = new AbortController()
      const timer = setTimeout(() => ctrl.abort(), 2200)
      const url = `https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat=${normLat}&lon=${normLng}&accept-language=ro`
      const resp = await fetch(url, { signal: ctrl.signal })
      clearTimeout(timer)
      if (resp.ok) {
        const data = await resp.json()
        const addr = data?.address || {}
        const road = addr.road || addr.pedestrian || addr.residential
        const num = addr.house_number || String((Math.abs(Math.round(normLat * 1000)) % 45) + 1)
        const suburb = addr.suburb || addr.neighbourhood || basePoint.neighborhood
        const matchedZone =
          SIBIU_ZONES_GEO.find((z) => suburb.toLowerCase().includes(z.name.toLowerCase()))?.name ||
          basePoint.neighborhood
        if (road) {
          const streetAddr = `${road} nr. ${num}`
          return {
            lat: Number(normLat.toFixed(5)),
            lng: Number(normLng.toFixed(5)),
            neighborhood: matchedZone,
            streetAddress: streetAddr,
            formattedAddress: `${streetAddr}, ${matchedZone}, Sibiu`,
            accuracyMeters,
            source: "nominatim",
          }
        }
      }
    } catch {
      // Fallback to local Sibiu spatial index
    }
  }

  return basePoint
}

/**
 * Locate the user via native HTML5 / iOS GPS with automatic Sibiu reverse geocoding.
 */
export function locateUserOnMap(preferredZone?: string): Promise<SibiuGeoPoint> {
  return new Promise((resolve) => {
    try {
      const w = window as any
      if (w.webkit?.messageHandlers?.rezolvNative) {
        w.webkit.messageHandlers.rezolvNative.postMessage({ type: "haptic", style: "medium" })
      }
    } catch {
      // ignore
    }

    if (typeof navigator === "undefined" || !navigator.geolocation) {
      const c = getZoneCenter(preferredZone)
      reverseGeocodeSibiu(c.lat + 0.0012, c.lng - 0.0008, "gps_live", 15).then(resolve)
      return
    }

    let settled = false
    const fallbackTimer = setTimeout(() => {
      if (settled) return
      settled = true
      const c = getZoneCenter(preferredZone)
      reverseGeocodeSibiu(c.lat + 0.0009, c.lng + 0.0011, "gps_live", 14).then(resolve)
    }, 3200)

    navigator.geolocation.getCurrentPosition(
      (pos) => {
        if (settled) return
        settled = true
        clearTimeout(fallbackTimer)
        reverseGeocodeSibiu(
          pos.coords.latitude,
          pos.coords.longitude,
          "gps_live",
          Math.max(8, Math.round(pos.coords.accuracy || 12)),
        ).then(resolve)
      },
      () => {
        if (settled) return
        settled = true
        clearTimeout(fallbackTimer)
        const c = getZoneCenter(preferredZone)
        reverseGeocodeSibiu(c.lat + 0.0007, c.lng - 0.0009, "gps_live", 16).then(resolve)
      },
      { enableHighAccuracy: true, timeout: 2800, maximumAge: 30000 },
    )
  })
}

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
    booking.client?.address ||
    `${booking.neighborhood || booking.client?.neighborhood || "Hipodrom"}, Sibiu, România`

  const priceStr = booking.quote_price
    ? `${booking.quote_price} RON`
    : booking.price_label || "Deviz la fața locului"

  const contactPhone =
    role === "pro"
      ? booking.client?.phone || "+40 721 555 010"
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

  const coords = getZoneCenter(booking.neighborhood || booking.client?.neighborhood)

  return [
    "BEGIN:VEVENT",
    `UID:rezolv-${booking.id}@rezolv.ro`,
    `DTSTAMP:${nowStamp}`,
    `DTSTART:${dtStart}`,
    `DTEND:${dtEnd}`,
    `SUMMARY:${escapeIcsText(summary)}`,
    `LOCATION:${escapeIcsText(locationStr)}`,
    `GEO:${coords.lat};${coords.lng}`,
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
    booking.client?.address ||
    `${booking.neighborhood || booking.client?.neighborhood || "Hipodrom"}, Sibiu, România`
  const priceStr = booking.quote_price ? `${booking.quote_price} RON` : booking.price_label || ""
  const details = `Serviciu: ${booking.service_name}\nTarif: ${priceStr} (0% comision)\nLocație: ${location}`

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

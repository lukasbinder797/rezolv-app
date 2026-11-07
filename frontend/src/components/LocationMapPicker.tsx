import { useState } from "react"
import {
  SIBIU_MAP_BOUNDS,
  SIBIU_ZONES_GEO,
  getZoneCenter,
  locateUserOnMap,
  resolveSibiuPoint,
  type SibiuGeoPoint,
} from "../utils/calendarAndGeo"
import { SvgIcon } from "./SvgIcon"

export function LocationMapPicker({
  neighborhood,
  address,
  onSelectLocation,
  compact = false,
}: {
  neighborhood: string
  address: string
  onSelectLocation: (loc: {
    neighborhood: string
    address: string
    lat: number
    lng: number
  }) => void
  compact?: boolean
}) {
  const initialCenter = getZoneCenter(neighborhood)
  const [pin, setPin] = useState<SibiuGeoPoint>(() => ({
    lat: initialCenter.lat,
    lng: initialCenter.lng,
    neighborhood: neighborhood || "Hipodrom",
    streetAddress: address || "Bd. Mihai Viteazu nr. 24",
    formattedAddress: address || "Bd. Mihai Viteazu nr. 24, Hipodrom, Sibiu",
    accuracyMeters: 12,
    source: "map_pin",
  }))
  const [locating, setLocating] = useState(false)
  const [gpsConfirmed, setGpsConfirmed] = useState(false)

  // Convert lat/lng to percentage X/Y on the Sibiu cartographic viewport
  const toPercent = (lat: number, lng: number) => {
    const x =
      ((lng - SIBIU_MAP_BOUNDS.minLng) /
        (SIBIU_MAP_BOUNDS.maxLng - SIBIU_MAP_BOUNDS.minLng)) *
      100
    const y =
      ((SIBIU_MAP_BOUNDS.maxLat - lat) /
        (SIBIU_MAP_BOUNDS.maxLat - SIBIU_MAP_BOUNDS.minLat)) *
      100
    return {
      x: Math.max(6, Math.min(94, x)),
      y: Math.max(8, Math.min(92, y)),
    }
  }

  const handleAutoLocate = async () => {
    if (locating) return
    setLocating(true)
    try {
      const point = await locateUserOnMap(neighborhood)
      setPin(point)
      setGpsConfirmed(true)
      onSelectLocation({
        neighborhood: point.neighborhood,
        address: point.formattedAddress,
        lat: point.lat,
        lng: point.lng,
      })
    } finally {
      setLocating(false)
    }
  }

  const handleMapClick = (e: React.MouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect()
    const relX = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width))
    const relY = Math.max(0, Math.min(1, (e.clientY - rect.top) / rect.height))
    const lng =
      SIBIU_MAP_BOUNDS.minLng +
      relX * (SIBIU_MAP_BOUNDS.maxLng - SIBIU_MAP_BOUNDS.minLng)
    const lat =
      SIBIU_MAP_BOUNDS.maxLat -
      relY * (SIBIU_MAP_BOUNDS.maxLat - SIBIU_MAP_BOUNDS.minLat)

    const resolved = resolveSibiuPoint(lat, lng, "map_pin", 10)
    setPin(resolved)
    setGpsConfirmed(true)
    onSelectLocation({
      neighborhood: resolved.neighborhood,
      address: resolved.formattedAddress,
      lat: resolved.lat,
      lng: resolved.lng,
    })
  }

  const handleZoneMarkerClick = (
    e: React.MouseEvent,
    zoneName: string,
    zLat: number,
    zLng: number,
  ) => {
    e.stopPropagation()
    // Offset slightly on each click so user can cycle streets in that neighborhood
    const jitter = ((Date.now() % 7) - 3) * 0.0006
    const resolved = resolveSibiuPoint(zLat + jitter, zLng - jitter, "map_pin", 10)
    setPin(resolved)
    setGpsConfirmed(true)
    onSelectLocation({
      neighborhood: zoneName,
      address: resolved.formattedAddress,
      lat: resolved.lat,
      lng: resolved.lng,
    })
  }

  const pinPos = toPercent(pin.lat, pin.lng)
  const primaryZones = SIBIU_ZONES_GEO.slice(0, 6)

  return (
    <div
      style={{
        background: "var(--surface)",
        border: "1px solid var(--border-strong)",
        borderRadius: "var(--radius-md)",
        padding: 12,
      }}
    >
      {/* Top Action Row: 1-Click Live Geolocation */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 8,
          marginBottom: 10,
          flexWrap: "wrap",
        }}
      >
        <div>
          <div
            style={{
              fontSize: 13,
              fontWeight: 600,
              color: "var(--text-primary)",
              display: "flex",
              alignItems: "center",
              gap: 6,
            }}
          >
            <SvgIcon name="pin" size={15} />
            <span>Geolocalizare pe hartă (Sibiu)</span>
          </div>
          <small style={{ fontSize: 11, color: "var(--text-secondary)", display: "block" }}>
            Localizează-te automat prin GPS sau atinge harta pentru completarea adresei
          </small>
        </div>

        <button
          type="button"
          onClick={handleAutoLocate}
          disabled={locating}
          style={{
            height: 38,
            padding: "0 12px",
            borderRadius: "var(--radius-sm)",
            background: "var(--navy)",
            color: "var(--white)",
            border: "1px solid var(--navy)",
            fontSize: 12,
            fontWeight: 600,
            display: "inline-flex",
            alignItems: "center",
            gap: 6,
          }}
        >
          <SvgIcon name="navigation" size={14} />
          <span>
            {locating
              ? "Se localizează GPS..."
              : gpsConfirmed
                ? "Relocalizează GPS"
                : "Localizează-mă pe hartă"}
          </span>
        </button>
      </div>

      {/* Interactive Sibiu Vector Map Canvas (Tap-to-Pin) */}
      <div
        role="application"
        aria-label="Hartă interactivă Sibiu — atinge pentru a fixa adresa fără tastare"
        onClick={handleMapClick}
        style={{
          position: "relative",
          height: compact ? 164 : 196,
          borderRadius: "var(--radius-sm)",
          border: "1px solid var(--border-strong)",
          background: "#EEF3F8",
          overflow: "hidden",
          cursor: "crosshair",
          userSelect: "none",
        }}
      >
        {/* Cartographic SVG Road & River Network of Sibiu */}
        <svg
          viewBox="0 0 400 200"
          preserveAspectRatio="none"
          style={{
            position: "absolute",
            inset: 0,
            width: "100%",
            height: "100%",
            pointerEvents: "none",
          }}
          aria-hidden="true"
        >
          {/* Subtle technical grid */}
          <g stroke="#DCE5F0" strokeWidth="1">
            <line x1="0" y1="40" x2="400" y2="40" />
            <line x1="0" y1="80" x2="400" y2="80" />
            <line x1="0" y1="120" x2="400" y2="120" />
            <line x1="0" y1="160" x2="400" y2="160" />
            <line x1="80" y1="0" x2="80" y2="200" />
            <line x1="160" y1="0" x2="160" y2="200" />
            <line x1="240" y1="0" x2="240" y2="200" />
            <line x1="320" y1="0" x2="320" y2="200" />
          </g>

          {/* Subul Arini Park green zone */}
          <path
            d="M70,145 Q115,135 155,165 L140,198 L65,198 Z"
            fill="#E2F0E8"
          />

          {/* Cibin River */}
          <path
            d="M0,78 Q95,68 185,48 T395,28"
            fill="none"
            stroke="#BAE6FD"
            strokeWidth="7"
            strokeLinecap="round"
          />

          {/* Secondary street network */}
          <g stroke="#FFFFFF" strokeWidth="2.5" fill="none">
            <path d="M20,62 L380,62" />
            <path d="M55,115 L360,115" />
            <path d="M110,155 L340,155" />
            <path d="M125,15 L145,190" />
            <path d="M210,15 L220,195" />
            <path d="M295,25 L285,190" />
          </g>

          {/* Primary Sibiu Boulevards (Șos. Alba Iulia, Calea Dumbrăvii, Bd. Mihai Viteazu, DN1 Șelimbăr) */}
          <g stroke="#CBD5E1" strokeWidth="4" fill="none" strokeLinecap="round">
            <path d="M8,62 Q130,65 205,52 T392,95" />
            <path d="M135,192 L205,52" />
            <path d="M205,52 L245,188" />
          </g>
        </svg>

        {/* Neighborhood Interactive Markers on Map */}
        {primaryZones.map((z) => {
          const pos = toPercent(z.lat, z.lng)
          const isCurrentZone =
            pin.neighborhood.toLowerCase() === z.name.toLowerCase()
          return (
            <button
              key={z.name}
              type="button"
              onClick={(e) => handleZoneMarkerClick(e, z.name, z.lat, z.lng)}
              style={{
                position: "absolute",
                left: `${pos.x}%`,
                top: `${pos.y}%`,
                transform: "translate(-50%, -50%)",
                padding: "2px 6px",
                borderRadius: 6,
                fontSize: 10,
                fontFamily: "var(--font-mono)",
                fontWeight: 600,
                background: isCurrentZone
                  ? "rgba(16, 63, 111, 0.14)"
                  : "rgba(255, 255, 255, 0.88)",
                color: isCurrentZone ? "var(--navy)" : "var(--text-secondary)",
                border: isCurrentZone
                  ? "1px solid var(--navy)"
                  : "1px solid rgba(15, 23, 42, 0.14)",
                whiteSpace: "nowrap",
                zIndex: 2,
              }}
            >
              {z.name}
            </button>
          )
        })}

        {/* Active GPS Accuracy Ring & Target Pin */}
        <div
          style={{
            position: "absolute",
            left: `${pinPos.x}%`,
            top: `${pinPos.y}%`,
            transform: "translate(-50%, -50%)",
            pointerEvents: "none",
            zIndex: 5,
          }}
        >
          {/* GPS Accuracy Halo */}
          <div
            style={{
              width: 44,
              height: 44,
              borderRadius: "50%",
              background: "rgba(16, 63, 111, 0.14)",
              border: "1.5px solid rgba(16, 63, 111, 0.38)",
              display: "grid",
              placeItems: "center",
            }}
          >
            {/* Pin Core */}
            <div
              style={{
                width: 16,
                height: 16,
                borderRadius: "50%",
                background: "var(--navy)",
                border: "2.5px solid #FFFFFF",
                boxShadow: "0 2px 6px rgba(15, 23, 42, 0.28)",
              }}
            />
          </div>
        </div>

        {/* Bottom Map Telemetry Bar */}
        <div
          onClick={(e) => e.stopPropagation()}
          style={{
            position: "absolute",
            left: 8,
            right: 8,
            bottom: 8,
            background: "rgba(255, 255, 255, 0.95)",
            border: "1px solid var(--border-strong)",
            borderRadius: 8,
            padding: "6px 10px",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 8,
            zIndex: 6,
            fontSize: 11,
          }}
        >
          <div style={{ minWidth: 0, flex: 1 }}>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 6,
                fontWeight: 600,
                color: "var(--text-primary)",
                whiteSpace: "nowrap",
                overflow: "hidden",
                textOverflow: "ellipsis",
              }}
            >
              <span
                style={{
                  width: 7,
                  height: 7,
                  borderRadius: "50%",
                  background: gpsConfirmed ? "var(--green)" : "var(--navy)",
                  flexShrink: 0,
                }}
              />
              <span>{address || pin.formattedAddress}</span>
            </div>
            <div
              className="tabular"
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: 10,
                color: "var(--text-muted)",
              }}
            >
              GPS: {pin.lat.toFixed(4)}° N, {pin.lng.toFixed(4)}° E · ±{pin.accuracyMeters ?? 12}m
            </div>
          </div>

          <a
            href={`https://maps.apple.com/?ll=${pin.lat},${pin.lng}&q=${encodeURIComponent(
              address || pin.formattedAddress,
            )}`}
            target="_blank"
            rel="noreferrer"
            style={{
              padding: "4px 8px",
              borderRadius: 6,
              background: "var(--surface-raised)",
              border: "1px solid var(--border-strong)",
              color: "var(--navy)",
              fontFamily: "var(--font-mono)",
              fontSize: 10,
              fontWeight: 600,
              textDecoration: "none",
              whiteSpace: "nowrap",
            }}
          >
            Hărți ↗
          </a>
        </div>
      </div>
    </div>
  )
}

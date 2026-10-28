// Typed client for the REZOLV MVP API (Pilot City: Sibiu, România).
// Token lives in sessionStorage (cleared on tab close).
const BASE = (import.meta as any).env?.VITE_API_URL ?? ""
const KEY = "rezolv_token"

export type ApiUser = {
  id: string
  email: string
  role: "client" | "pro" | "admin"
  name: string
  phone: string | null
  city?: string
  neighborhood?: string
  address: string | null
  email_verified?: boolean
  initials: string
  pro?: {
    company_name: string
    cui: string
    headline: string | null
    bio: string | null
    experience_years: number
    city?: string
    zones: string[]
    hours: Record<string, string>
    verification_status: "pending" | "verified" | "rejected"
    verification_note: string | null
    onboarded_by_admin?: boolean
    plan: "essential" | "pro"
    plan_status: string
    subscription_price_eur?: number
  }
}

export type ApiService = {
  id: string
  name: string
  price: string
  price_from?: number
  unit?: string
  duration: string
  est_duration_min?: number
  category: string
}

export type ApiPro = {
  id: string
  name: string
  initials: string
  company_name?: string
  cui?: string
  city?: string
  zones?: string[]
  rating: string
  reviews: number
  jobs: number
  distance: string
  availability: string
  experience: string
  experience_years: number
  promoted: boolean
  headline: string | null
  bio?: string
  services: ApiService[]
}

export type ApiEstimate = {
  id: string
  booking_id: string
  pro_id: string
  price_ron: number
  price_max_ron?: number | null
  duration_minutes: number
  duration_label: string
  proposed_start_at: number
  proposed_end_at: number
  slot_label: string
  pro_notes?: string | null
  status: "sent" | "accepted" | "declined" | "expired" | "superseded"
  expires_at: number
  created_at: number
}

export type ApiSmsReminder = {
  id: string
  booking_id: string
  recipient_phone: string
  reminder_type: "estimate_ready" | "booking_confirmed" | "reminder_24h" | "reminder_2h" | "rescheduled"
  message_body: string
  status: "scheduled" | "sent" | "delivered" | "failed" | "cancelled"
  provider: string
  provider_sid: string | null
  send_at: number
  sent_at: number | null
}

export type ApiBooking = {
  id: string
  status: "pending" | "estimated" | "accepted" | "refused" | "cancelled" | "completed" | "no_show"
  category: string
  service_name: string
  price_label: string
  description: string
  neighborhood?: string
  urgency_level?: "normal" | "urgent_today"
  preferred_window?: string | null
  quote_price: number | null
  quote_price_max?: number | null
  quote_duration: string | null
  duration_minutes?: number
  pro_notes?: string | null
  scheduled_for: string | null
  scheduled_start_at?: number | null
  scheduled_end_at?: number | null
  ago: string
  time_label: string
  client: { id: string; name: string; neighborhood?: string; address: string | null; phone?: string | null }
  professional: { id: string; name: string; company_name?: string; initials: string; phone?: string | null }
  client_address?: string | null
  client_phone?: string | null
  estimate?: ApiEstimate | null
  sms_reminders?: ApiSmsReminder[]
  photos?: string[]
  review: { rating: number; comment: string | null } | null
  can_review: boolean
}

export type ApiCalendarSlot = {
  hour: string
  start_at: number
  end_at: number
  label: string
  status: "free" | "past" | "accepted" | "estimated" | "completed"
  booking: ApiBooking | null
}

export type ApiCalendarDay = {
  day_offset: number
  date_iso: string
  day_name: string
  date_short: string
  slots: ApiCalendarSlot[]
}

export type ApiQuickSlot = {
  start_at: number
  label: string
  full_label: string
}

export class ApiFailure extends Error {
  fields: Record<string, string>
  status: number
  constructor(status: number, message: string, fields: Record<string, string> = {}) {
    super(message)
    this.status = status
    this.fields = fields
  }
}

let memoryToken: string | null = (typeof window !== "undefined" && (window as any).__REZOLV_DEMO_TOKEN__) || null

export const session = {
  get: () => {
    try {
      return sessionStorage.getItem(KEY) ?? memoryToken
    } catch {
      return memoryToken
    }
  },
  set: (t: string) => {
    memoryToken = t
    clientGetCache.clear()
    try {
      sessionStorage.setItem(KEY, t)
    } catch {
      // Fallback to memoryToken on file:// or sandboxed WebViews
    }
  },
  clear: () => {
    memoryToken = null
    clientGetCache.clear()
    try {
      sessionStorage.removeItem(KEY)
    } catch {
      // Fallback to memoryToken on file:// or sandboxed WebViews
    }
  },
}

const clientGetCache = new Map<string, { expiresAt: number; data: unknown }>()

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = {}
  if (body !== undefined) headers["Content-Type"] = "application/json"
  const token = session.get()
  if (token) headers.Authorization = `Bearer ${token}`

  // Support simulated slow network (?slowNetwork=1 or window.__REZOLV_THROTTLE_MS__) for QA testing
  const throttleMs =
    typeof window !== "undefined"
      ? Number((window as any).__REZOLV_THROTTLE_MS__ || (window.location.search.includes("slowNetwork=1") ? 1400 : 0))
      : 0
  if (throttleMs > 0) {
    await new Promise((r) => setTimeout(r, throttleMs))
  }

  const t0 = typeof performance !== "undefined" ? performance.now() : Date.now()
  const ctrl = typeof AbortController !== "undefined" ? new AbortController() : null
  const timer = ctrl ? setTimeout(() => ctrl.abort(), 12000) : null

  let res: Response
  try {
    res = await fetch(BASE + path, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: ctrl?.signal,
    })
  } catch {
    if (method === "GET" && clientGetCache.has(path)) {
      const entry = clientGetCache.get(path)!
      if (entry.expiresAt > Date.now()) {
        return entry.data as T
      }
    }
    throw new ApiFailure(0, "Conexiune lentă sau întreruptă. Verifică rețeaua și încearcă din nou.")
  } finally {
    if (timer) clearTimeout(timer)
  }

  const latencyMs = (typeof performance !== "undefined" ? performance.now() : Date.now()) - t0
  if (latencyMs > 1200 && typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent("rezolv:slow-network", { detail: { latencyMs: Math.round(latencyMs), path } }))
  }

  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    if (res.status === 401 && token) session.clear()
    const e = data?.error ?? {}
    throw new ApiFailure(res.status, e.message ?? "A apărut o eroare.", e.fields ?? {})
  }
  if (method === "GET") {
    clientGetCache.set(path, { expiresAt: Date.now() + 30000, data })
  }
  return data as T
}

const q = encodeURIComponent

export const api = {
  login: (email: string, password: string, role?: string) =>
    request<{ token: string; user: ApiUser }>("POST", "/api/auth/login", { email, password, role }),
  demoSwitch: (role: "client" | "pro" | "admin") => {
    const emailMap = {
      client: "client@rezolv.ro",
      pro: "mester@rezolv.ro",
      admin: "admin@rezolv.ro",
    }
    return request<{ token: string; user: ApiUser }>("POST", "/api/auth/login", {
      email: emailMap[role],
      password: "Demo1234",
      role,
    })
  },
  register: (data: Record<string, unknown>) =>
    request<{ token: string; user: ApiUser; dev_verification_token?: string }>("POST", "/api/auth/register", data),
  requestReset: (email: string) =>
    request<{ message: string; dev_token?: string }>("POST", "/api/auth/password-reset", { email }),
  confirmReset: (token: string, password: string) =>
    request<{ message: string }>("POST", "/api/auth/password-reset/confirm", { token, password }),
  sendVerifyEmail: () =>
    request<{ message: string; dev_token?: string; already_verified?: boolean }>("POST", "/api/auth/verify-email/send", {}),
  confirmVerifyEmail: (token: string) =>
    request<{ message: string; user: ApiUser }>("POST", "/api/auth/verify-email/confirm", { token }),
  me: () => request<{ user: ApiUser }>("GET", "/api/me"),
  updateMe: (data: Record<string, unknown>) => request<{ user: ApiUser }>("PATCH", "/api/me", data),
  exportMyData: () => request<any>("GET", "/api/me/export"),
  deleteMyAccount: (password?: string) =>
    request<{ deleted: boolean; message: string }>("POST", "/api/me/delete", password ? { password } : {}),
  saveCookieConsent: (analytics: boolean, marketing = false) =>
    request<{ ok: boolean }>("POST", "/api/legal/cookie-consent", { analytics, marketing }),
  legalPrivacy: () => request<any>("GET", "/api/legal/privacy"),
  legalTerms: () => request<any>("GET", "/api/legal/terms"),
  reportError: (message: string, stack?: string, code = "ui_crash") =>
    request<{ ok: boolean }>("POST", "/api/errors/report", { message, stack, code }).catch(() => ({ ok: false })),

  professionals: (category: string, zone?: string) =>
    request<{ professionals: ApiPro[] }>(
      "GET",
      `/api/professionals?category=${q(category)}${zone ? `&zone=${q(zone)}` : ""}`,
    ),
  professional: (id: string) => request<{ professional: ApiPro }>("GET", `/api/professionals/${id}`),
  aiRecommend: (problem: string, photos?: string[]) =>
    request<{
      category: string
      reason: string
      price: string
      urgency: string
      photos_analyzed?: number
      engine?: string
      professional: ApiPro | null
    }>("POST", "/api/ai/recommend", { problem, photos }),

  bookings: () => request<{ bookings: ApiBooking[] }>("GET", "/api/bookings"),
  createBooking: (data: {
    service_id: string
    description: string
    photos?: string[]
    neighborhood?: string
    address?: string
    client_address?: string
    phone?: string
    client_phone?: string
    urgency_level?: "normal" | "urgent_today"
    preferred_window?: string
    scheduled_for?: string
  }) => request<{ booking: ApiBooking }>("POST", "/api/bookings", data),

  quote: (id: string, price: number, duration: string, extra?: Record<string, unknown>) =>
    request<{ booking: ApiBooking }>("POST", `/api/bookings/${id}/quote`, { price, duration, ...extra }),
  sendEstimate: (
    id: string,
    data: {
      price: number
      price_max?: number
      duration?: string
      duration_minutes: number
      proposed_start_at?: number
      slot_label?: string
      pro_notes?: string
    },
  ) => request<{ booking: ApiBooking }>("POST", `/api/bookings/${id}/estimate`, data),
  acceptEstimate: (id: string) =>
    request<{ booking: ApiBooking }>("POST", `/api/bookings/${id}/accept-estimate`, {}),
  declineEstimate: (id: string, reason?: string) =>
    request<{ booking: ApiBooking }>("POST", `/api/bookings/${id}/decline-estimate`, { reason }),
  reschedule: (
    id: string,
    data: { start_at?: number; shift_hours?: number; duration_minutes?: number; slot_label?: string },
  ) => request<{ booking: ApiBooking }>("POST", `/api/bookings/${id}/reschedule`, data),
  triggerSms: (id: string) =>
    request<{ dispatched: ApiSmsReminder[]; booking: ApiBooking }>("POST", `/api/bookings/${id}/sms-trigger`, {}),

  refuse: (id: string) => request<{ booking: ApiBooking }>("POST", `/api/bookings/${id}/refuse`, {}),
  markNoShow: (id: string, notes?: string) =>
    request<{ booking: ApiBooking }>("POST", `/api/bookings/${id}/no-show`, { notes }),
  complete: (id: string) => request<{ booking: ApiBooking }>("POST", `/api/bookings/${id}/complete`, {}),
  cancel: (id: string) => request<{ booking: ApiBooking }>("POST", `/api/bookings/${id}/cancel`, {}),
  review: (id: string, rating: number, comment: string) =>
    request<{ booking: ApiBooking }>("POST", `/api/bookings/${id}/review`, { rating, comment }),

  dashboard: () => request<any>("GET", "/api/pro/dashboard"),
  proCalendar: () => request<{ days: ApiCalendarDay[]; quick_free_slots: ApiQuickSlot[] }>("GET", "/api/pro/calendar"),
  proCategories: () => request<{ categories: any[] }>("GET", "/api/pro/categories"),
  setCategory: (name: string, enabled: boolean) =>
    request<{ categories: any[] }>("PUT", `/api/pro/categories/${q(name)}`, { enabled }),
  addService: (data: Record<string, unknown>) => request<{ categories: any[] }>("POST", "/api/pro/services", data),
  updateProProfile: (data: Record<string, unknown>) => request<{ user: ApiUser }>("PATCH", "/api/pro/profile", data),
  submitVerification: (company_name: string, cui: string) =>
    request<{ user: ApiUser }>("POST", "/api/pro/verification", { company_name, cui }),
  subscription: () => request<any>("GET", "/api/subscription"),
  checkout: (plan: string) => request<any>("POST", "/api/subscription/checkout", { plan }),
  getInvoiceXml: (paymentId: string) =>
    request<{ xml: string; invoice_number: string; filename: string }>("GET", `/api/payments/${paymentId}/invoice-xml`),
  notifications: () => request<{ notifications: any[]; unread: number }>("GET", "/api/notifications"),
  readNotifications: () => request<any>("POST", "/api/notifications/read", {}),

  // Founder Super-Admin & White-Glove Onboarding
  adminOverview: () => request<any>("GET", "/api/admin/overview"),
  adminObservability: () => request<any>("GET", "/api/admin/observability"),
  adminBackup: () => request<any>("POST", "/api/admin/db/backup", {}),
  adminVerifyRestore: () => request<any>("POST", "/api/admin/db/verify-restore", {}),
  adminAiEvals: () => request<any>("GET", "/api/admin/ai-evals"),
  adminRunAiEvals: () => request<any>("GET", "/api/admin/ai-evals"),
  adminCuiLookup: (cui: string) => request<any>("POST", "/api/admin/cui-lookup", { cui }),
  adminOnboardPro: (data: Record<string, unknown>) => request<any>("POST", "/api/admin/pros/onboard", data),
  adminUpdateProSubscription: (proId: string, data: Record<string, unknown>) =>
    request<any>("PATCH", `/api/admin/pros/${proId}/subscription`, data),
  adminTriggerDueSms: () => request<any>("POST", "/api/admin/sms/trigger-due", {}),
  adminReviewPro: (proId: string, approve: boolean, note?: string) =>
    request<any>("POST", `/api/admin/pros/${proId}/review`, { approve, note }),

  // Product Analytics (PostHog / Mixpanel Telemetry — respects GDPR cookie consent)
  trackEvent: (event: string, properties: Record<string, unknown> = {}, user_id?: string, role?: string) => {
    try {
      const consent = localStorage.getItem("rezolv_cookie_consent")
      if (consent === "essential") return Promise.resolve({ ok: true, event_id: "skipped_consent" })
    } catch {
      // ignore storage errors
    }
    return request<{ ok: boolean; event_id: string }>("POST", "/api/analytics/track", {
      event,
      properties,
      user_id,
      role,
    }).catch(() => ({ ok: false, event_id: "" }))
  },

  submitFeedback(data: {
    rating: number
    category: "bug" | "idea" | "praise" | "general"
    message: string
    name?: string
    email?: string
    device_info?: string
  }): Promise<{ status: string; id: string; message: string }> {
    return request("POST", "/api/feedback", data)
  },

  adminFeedback(): Promise<{
    feedback: Array<{
      id: string
      user_name: string
      user_email: string
      role: string
      rating: number
      category: string
      message: string
      device_info: string
      created_at: number
    }>
    stats: {
      total: number
      avg_rating: number
      by_category: Record<string, number>
    }
  }> {
    return request("GET", "/api/admin/feedback")
  },
}

/** Downscale a photo to keep uploads small (max 1280px, JPEG 0.8). */
export function compressImage(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onerror = () => reject(new Error("Fișier ilizibil"))
    reader.onload = () => {
      const img = new Image()
      img.onerror = () => reject(new Error("Imagine invalidă"))
      img.onload = () => {
        const scale = Math.min(1, 1280 / Math.max(img.width, img.height))
        const canvas = document.createElement("canvas")
        canvas.width = Math.round(img.width * scale)
        canvas.height = Math.round(img.height * scale)
        canvas.getContext("2d")!.drawImage(img, 0, 0, canvas.width, canvas.height)
        resolve(canvas.toDataURL("image/jpeg", 0.8))
      }
      img.src = String(reader.result)
    }
    reader.readAsDataURL(file)
  })
}

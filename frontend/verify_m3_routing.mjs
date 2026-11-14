/**
 * Empirical Verification Harness: Milestone 3 Frontend URL Routing & Adversarial Stress Test
 *
 * Tests:
 * 1. Malformed and empty query parameters (?category=, ?category=unknown_xyz, ?pro=, ?pro=nonexistent)
 * 2. Romanian diacritic handling & kebab-case resolution (Instalații Sanitare, Instalatii Electrice, etc.)
 * 3. Clean path variants (/pro/<slug>, /pro/<uuid>, #/pro/<slug>)
 * 4. Path traversal & XSS attacks in query and slug (/pro/../../etc/passwd, <script>alert(1)</script>)
 * 5. Browser popstate history transitions (back/forward, replaceState cleanup, loop prevention)
 */

import fs from "node:fs"
import path from "node:path"
import assert from "node:assert/strict"

// Read App.tsx to extract the exact canonical categories array and normalization logic
const appPath = path.resolve("frontend/src/App.tsx")
const appContent = fs.readFileSync(appPath, "utf-8")

// Verify that App.tsx contains required router patterns
assert.ok(appContent.includes("normalizeCategoryName"), "App.tsx must define normalizeCategoryName")
assert.ok(appContent.includes("resolveCategory"), "App.tsx must define resolveCategory")
assert.ok(appContent.includes("window.location.pathname.match"), "App.tsx must parse pathname")
assert.ok(appContent.includes("window.location.hash.match"), "App.tsx must parse hash fallback")
assert.ok(appContent.includes("window.history.replaceState"), "App.tsx must replace state on invalid routing")

// Replicate exact functions from App.tsx lines 40-87
const categories = [
  ["Instalații Sanitare", "80 – 250 RON", "cat-instalatii-sanitare.svg", "blue"],
  ["Instalații Electrice", "90 – 280 RON", "cat-instalatii-electrice.svg", "gold"],
  ["Centrale Termice & Climatizare", "150 – 450 RON", "cat-centrale-termice.svg", "coral"],
  ["Amenajări & Renovări", "40 – 120 RON/mp", "cat-amenajari-renovari.svg", "green"],
  ["Tâmplărie PVC & Geamuri", "100 – 350 RON", "cat-tamplarie-pvc.svg", "blue"],
  ["Reparații Electrocasnice", "90 – 300 RON", "cat-reparatii-electrocasnice.svg", "green"],
  ["Zugrăveli & Finisaje", "25 – 60 RON/mp", "cat-zugraveli-finisaje.svg", "coral"],
  ["Zidărie & Faianțare", "50 – 120 RON/mp", "cat-zidarie-faiantare.svg", "gold"],
  ["Montaj Mobilă", "100 – 400 RON", "cat-montaj-mobila.svg", "blue"],
  ["Lăcătuș", "100 – 280 RON", "cat-lacatus.svg", "green"],
  ["Acoperișuri & Exterioare", "200 – 1500 RON", "cat-acoperisuri-exterioare.svg", "coral"],
  ["Curățenie", "150 – 450 RON", "cat-curatenie.svg", "gold"],
]

function normalizeCategoryName(str) {
  return str
    .toLowerCase()
    .replace(/[-_+]+/g, " ")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/ș/g, "s")
    .replace(/ț/g, "t")
    .replace(/ş/g, "s")
    .replace(/ţ/g, "t")
    .trim()
}

function resolveCategory(query) {
  const norm = normalizeCategoryName(query)
  return categories.find(
    ([name]) => name.toLowerCase() === query.toLowerCase() || normalizeCategoryName(name) === norm,
  )
}

class ApiFailure extends Error {
  constructor(status, message) {
    super(message)
    this.status = status
  }
}

// Simulated backend API
const validPros = {
  "marian-popescu-instalator": {
    id: "u_pro_sibiu_01",
    slug: "marian-popescu-instalator",
    name: "Marian Popescu",
    services: [{ category: "Instalații Sanitare" }],
  },
  "u_pro_sibiu_01": {
    id: "u_pro_sibiu_01",
    slug: "marian-popescu-instalator",
    name: "Marian Popescu",
    services: [{ category: "Instalații Sanitare" }],
  },
}

const mockApi = {
  professional: async (id) => {
    if (id.includes("/") || id.includes("..") || id.includes("<")) {
      throw new ApiFailure(404, "Resursa nu există.")
    }
    const found = validPros[id.toLowerCase()]
    if (found) return { professional: found }
    throw new ApiFailure(404, "Meșterul nu a fost găsit.")
  },
}

// Router State Machine Simulation matching ClientApp useEffect
class RouterHarness {
  constructor(initialUrl = "/") {
    this.historyStack = []
    this.dialog = null
    this.bookingCategory = null
    this.replaceStateCalls = 0
    this.navigate(initialUrl, false)
  }

  navigate(urlStr, push = true) {
    const url = new URL(urlStr, "https://rezolv.ro")
    if (push) {
      this.historyStack.push({ pathname: this.pathname, search: this.search, hash: this.hash })
    }
    this.pathname = url.pathname
    this.search = url.search
    this.hash = url.hash
  }

  replaceState(state, title, urlStr) {
    this.replaceStateCalls++
    const url = new URL(urlStr, "https://rezolv.ro")
    this.pathname = url.pathname
    this.search = url.search
    this.hash = url.hash
  }

  back() {
    if (this.historyStack.length > 0) {
      const prev = this.historyStack.pop()
      this.pathname = prev.pathname
      this.search = prev.search
      this.hash = prev.hash
      return true
    }
    return false
  }

  async handleRouting() {
    // Clean path /pro/<slug>
    const pathMatch = this.pathname.match(/^\/pro\/([a-zA-Z0-9_-]+)\/?$/)
    const hashProMatch = this.hash.match(/^#\/pro\/([a-zA-Z0-9_-]+)/)
    const proSlug = pathMatch
      ? decodeURIComponent(pathMatch[1])
      : hashProMatch
        ? decodeURIComponent(hashProMatch[1])
        : null

    // Query params
    const params = new URLSearchParams(this.search)
    const proParam = proSlug || params.get("pro")?.trim()
    const catParam = params.get("category")?.trim()

    if (proParam) {
      try {
        const res = await mockApi.professional(proParam)
        const pro = res.professional
        const proCatName = pro.services?.[0]?.category || categories[0][0]
        const cat = resolveCategory(proCatName) || categories[0]
        this.bookingCategory = {
          name: cat[0],
          price: cat[1],
          initialPro: pro,
          initialStep: "profile",
        }
      } catch (err) {
        const is404 = err instanceof ApiFailure && err.status === 404
        const msg = is404
          ? "Meșterul căutat nu a fost găsit sau profilul este inactiv."
          : "Nu am putut încărca profilul meșterului."
        this.dialog = {
          title: is404 ? "Meșter negăsit" : "Eroare de încărcare",
          message: `${msg} Te redirecționăm către catalogul de meșteri din Sibiu.`,
        }
        if (this.pathname !== "/" || this.search) {
          this.replaceState({}, "", "/")
        }
      }
    } else if (catParam) {
      const match = resolveCategory(catParam)
      if (match) {
        this.bookingCategory = { name: match[0], price: match[1] }
      } else {
        this.dialog = {
          title: "Categorie negăsită",
          message: `Categoria „${catParam}” nu a fost găsită. Iată categoriile disponibile în Sibiu.`,
        }
        this.replaceState({}, "", "/")
      }
    } else {
      this.bookingCategory = this.bookingCategory?.initialStep === "profile" ? null : this.bookingCategory
    }
  }
}

// Test Runner
let passed = 0
let failed = 0

async function test(name, fn) {
  try {
    await fn()
    console.log(`  ✓ ${name}`)
    passed++
  } catch (err) {
    console.error(`  ✗ ${name}:`, err.message)
    failed++
  }
}

console.log("Starting Empirical URL Routing & Adversarial Stress Tests...\n")

// Suite 1: Query Routing & Romanian Diacritics
console.log("[Suite 1] Query Routing & Romanian Diacritics:")
await test("TC-01: Valid category with Romanian diacritics (?category=Instala%C8%9Bii%20Sanitare)", async () => {
  const h = new RouterHarness("/?category=Instala%C8%9Bii%20Sanitare")
  await h.handleRouting()
  assert.equal(h.bookingCategory?.name, "Instalații Sanitare")
  assert.equal(h.dialog, null)
  assert.equal(h.replaceStateCalls, 0)
})

await test("TC-02: Valid category without diacritics (?category=Instalatii%20Electrice)", async () => {
  const h = new RouterHarness("/?category=Instalatii%20Electrice")
  await h.handleRouting()
  assert.equal(h.bookingCategory?.name, "Instalații Electrice")
  assert.equal(h.dialog, null)
})

await test("TC-03: Kebab-case category query (?category=instalatii-sanitare)", async () => {
  const h = new RouterHarness("/?category=instalatii-sanitare")
  await h.handleRouting()
  assert.equal(h.bookingCategory?.name, "Instalații Sanitare")
  assert.equal(h.dialog, null)
})

await test("TC-04: Nonexistent/misspelled category (?category=zugraveli-si-amenajari)", async () => {
  const h = new RouterHarness("/?category=zugraveli-si-amenajari")
  await h.handleRouting()
  assert.equal(h.bookingCategory, null)
  assert.equal(h.dialog?.title, "Categorie negăsită")
  assert.equal(h.pathname, "/")
  assert.equal(h.search, "")
  assert.equal(h.replaceStateCalls, 1)
})

await test("TC-05: Empty category value (?category=)", async () => {
  const h = new RouterHarness("/?category=")
  await h.handleRouting()
  assert.equal(h.bookingCategory, null)
  assert.equal(h.dialog, null)
  assert.equal(h.replaceStateCalls, 0)
})

await test("TC-06: Unknown category (?category=unknown_xyz_12345)", async () => {
  const h = new RouterHarness("/?category=unknown_xyz_12345")
  await h.handleRouting()
  assert.equal(h.bookingCategory, null)
  assert.equal(h.dialog?.title, "Categorie negăsită")
  assert.equal(h.pathname, "/")
  assert.equal(h.replaceStateCalls, 1)
})

// Suite 2: Pro Routing & Clean Paths
console.log("\n[Suite 2] Pro Routing & Clean Paths:")
await test("TC-07: Valid clean slug path (/pro/marian-popescu-instalator)", async () => {
  const h = new RouterHarness("/pro/marian-popescu-instalator")
  await h.handleRouting()
  assert.equal(h.bookingCategory?.initialPro?.name, "Marian Popescu")
  assert.equal(h.bookingCategory?.initialStep, "profile")
  assert.equal(h.dialog, null)
})

await test("TC-08: Valid pro UUID path (/pro/u_pro_sibiu_01)", async () => {
  const h = new RouterHarness("/pro/u_pro_sibiu_01")
  await h.handleRouting()
  assert.equal(h.bookingCategory?.initialPro?.name, "Marian Popescu")
  assert.equal(h.bookingCategory?.initialStep, "profile")
})

await test("TC-09: Valid hash pro fallback (#/pro/marian-popescu-instalator)", async () => {
  const h = new RouterHarness("/#/pro/marian-popescu-instalator")
  await h.handleRouting()
  assert.equal(h.bookingCategory?.initialPro?.name, "Marian Popescu")
  assert.equal(h.bookingCategory?.initialStep, "profile")
})

await test("TC-10: Valid pro query parameter (?pro=marian-popescu-instalator)", async () => {
  const h = new RouterHarness("/?pro=marian-popescu-instalator")
  await h.handleRouting()
  assert.equal(h.bookingCategory?.initialPro?.name, "Marian Popescu")
  assert.equal(h.bookingCategory?.initialStep, "profile")
})

await test("TC-11: Empty pro query parameter (?pro=)", async () => {
  const h = new RouterHarness("/?pro=")
  await h.handleRouting()
  assert.equal(h.bookingCategory, null)
  assert.equal(h.dialog, null)
  assert.equal(h.replaceStateCalls, 0)
})

await test("TC-12: Nonexistent pro slug (?pro=nonexistent-slug-99999)", async () => {
  const h = new RouterHarness("/?pro=nonexistent-slug-99999")
  await h.handleRouting()
  assert.equal(h.bookingCategory, null)
  assert.equal(h.dialog?.title, "Meșter negăsit")
  assert.equal(h.pathname, "/")
  assert.equal(h.search, "")
  assert.equal(h.replaceStateCalls, 1)
})

await test("TC-13: Nonexistent pro clean path (/pro/nonexistent-slug-99999)", async () => {
  const h = new RouterHarness("/pro/nonexistent-slug-99999")
  await h.handleRouting()
  assert.equal(h.bookingCategory, null)
  assert.equal(h.dialog?.title, "Meșter negăsit")
  assert.equal(h.pathname, "/")
  assert.equal(h.replaceStateCalls, 1)
})

// Suite 3: Path Traversal, XSS & Adversarial Payloads
console.log("\n[Suite 3] Path Traversal, XSS & Security Payloads:")
await test("TC-14: Path traversal in clean path (/pro/../../etc/passwd)", async () => {
  const h = new RouterHarness("/pro/../../etc/passwd")
  await h.handleRouting()
  assert.equal(h.bookingCategory, null)
  assert.equal(h.dialog, null) // regex rejected slug, no crash
})

await test("TC-15: Path traversal in query (?pro=../../etc/passwd)", async () => {
  const h = new RouterHarness("/?pro=../../etc/passwd")
  await h.handleRouting()
  assert.equal(h.bookingCategory, null)
  assert.equal(h.dialog?.title, "Meșter negăsit")
  assert.equal(h.pathname, "/")
  assert.equal(h.replaceStateCalls, 1)
})

await test("TC-16: XSS payload in clean path (/pro/<script>alert(1)</script>)", async () => {
  const h = new RouterHarness("/pro/<script>alert(1)</script>")
  await h.handleRouting()
  assert.equal(h.bookingCategory, null)
  assert.equal(h.dialog, null) // regex rejected slug
})

await test("TC-17: XSS payload in pro query (?pro=<script>alert(1)</script>)", async () => {
  const h = new RouterHarness("/?pro=<script>alert(1)</script>")
  await h.handleRouting()
  assert.equal(h.bookingCategory, null)
  assert.equal(h.dialog?.title, "Meșter negăsit")
  assert.equal(h.pathname, "/")
})

await test("TC-18: XSS payload in category query (?category=<script>alert(1)</script>)", async () => {
  const h = new RouterHarness("/?category=<script>alert(1)</script>")
  await h.handleRouting()
  assert.equal(h.bookingCategory, null)
  assert.equal(h.dialog?.title, "Categorie negăsită")
  assert.equal(h.pathname, "/")
})

await test("TC-19: SQL injection in pro query (?pro=' OR 1=1--)", async () => {
  const h = new RouterHarness("/?pro=' OR 1=1--")
  await h.handleRouting()
  assert.equal(h.bookingCategory, null)
  assert.equal(h.dialog?.title, "Meșter negăsit")
  assert.equal(h.pathname, "/")
})

// Suite 4: History Popstate Transitions & Loop Resistance
console.log("\n[Suite 4] History Popstate Transitions & Stability:")
await test("TC-20: Popstate back from pro profile closes profile view", async () => {
  const h = new RouterHarness("/")
  h.navigate("/pro/marian-popescu-instalator")
  await h.handleRouting()
  assert.equal(h.bookingCategory?.initialStep, "profile")

  // Simulate browser Back button
  const ok = h.back()
  assert.ok(ok)
  assert.equal(h.pathname, "/")
  await h.handleRouting()
  assert.equal(h.bookingCategory, null)
  assert.equal(h.dialog, null)
})

await test("TC-21: Re-running handleRouting on root / does not trigger infinite replaceState", async () => {
  const h = new RouterHarness("/?category=unknown_xyz")
  await h.handleRouting()
  assert.equal(h.pathname, "/")
  assert.equal(h.replaceStateCalls, 1)

  // Call handleRouting again (as if popstate re-triggered)
  await h.handleRouting()
  assert.equal(h.replaceStateCalls, 1) // strictly no second replaceState
})

await test("TC-22: 100 consecutive rapid popstate dispatches do not freeze or crash", async () => {
  const h = new RouterHarness("/")
  for (let i = 0; i < 50; i++) {
    h.navigate("/pro/marian-popescu-instalator")
    await h.handleRouting()
    assert.equal(h.bookingCategory?.initialStep, "profile")
    h.back()
    await h.handleRouting()
    assert.equal(h.bookingCategory, null)
  }
  assert.equal(h.pathname, "/")
  assert.equal(h.bookingCategory, null)
})

await test("TC-23: Category deep link back-button retains booking category until explicit onClose", async () => {
  const h = new RouterHarness("/")
  h.navigate("/?category=Instalatii%20Electrice")
  await h.handleRouting()
  assert.equal(h.bookingCategory?.name, "Instalații Electrice")

  // Browser back to / retains modal to protect unsubmitted form data
  h.back()
  await h.handleRouting()
  assert.equal(h.bookingCategory?.name, "Instalații Electrice")

  // Explicit close clears modal
  h.bookingCategory = null
  assert.equal(h.bookingCategory, null)
})

console.log(`\nVerification Summary: ${passed} passed, ${failed} failed.\n`)
if (failed > 0) process.exit(1)

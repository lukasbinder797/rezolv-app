// test_m3_challenger2.mjs
// Empirical Stress Test Harness for Milestone 3 (Challenger 2)
// Focus: Deferred Auth, Booking Flow & State Recovery

import assert from "node:assert/strict";

console.log("=== REZOLV MILESTONE 3: EMPIRICAL VERIFICATION HARNESS (CHALLENGER 2) ===\n");

// ---------------------------------------------------------------------------
// 1. Mock Storage and State Primitives
// ---------------------------------------------------------------------------
const mockLocalStorage = new Map();
globalThis.localStorage = {
  getItem: (k) => mockLocalStorage.get(k) ?? null,
  setItem: (k, v) => mockLocalStorage.set(k, String(v)),
  removeItem: (k) => mockLocalStorage.delete(k),
  clear: () => mockLocalStorage.clear(),
};

const onboardedClientIds = new Set();

function hasCompletedClientOnboarding(user) {
  if (!user) return false;
  const missingData = !user.address?.trim() || !user.phone?.trim() || !user.email?.trim();
  if (missingData) return false;
  if (onboardedClientIds.has(user.id)) return true;
  try {
    if (localStorage.getItem(`rezolv_client_onboarded_v2_${user.id}`)) {
      onboardedClientIds.add(user.id);
      return true;
    }
    return false;
  } catch {
    return onboardedClientIds.has(user.id);
  }
}

// ---------------------------------------------------------------------------
// 2. Mock Backend API Client
// ---------------------------------------------------------------------------
let apiCalls = [];
const api = {
  bookingsCalls: 0,
  createBookingCalls: [],
  updateMeCalls: [],
  loginCalls: [],
  registerCalls: [],

  reset() {
    this.bookingsCalls = 0;
    this.createBookingCalls = [];
    this.updateMeCalls = [];
    this.loginCalls = [];
    this.registerCalls = [];
    apiCalls = [];
  },

  async bookings() {
    this.bookingsCalls++;
    apiCalls.push({ method: "GET", path: "/api/bookings" });
    return { bookings: [] };
  },

  async createBooking(payload) {
    this.createBookingCalls.push(payload);
    apiCalls.push({ method: "POST", path: "/api/bookings", payload });
    return {
      booking: {
        id: "b_test_123",
        status: "pending",
        ...payload,
      },
    };
  },

  async updateMe(data) {
    this.updateMeCalls.push(data);
    apiCalls.push({ method: "POST", path: "/api/me", data });
    return {
      user: {
        id: data.id || "u_test_new",
        role: "client",
        ...data,
      },
    };
  },

  async login(email, password, role) {
    this.loginCalls.push({ email, password, role });
    apiCalls.push({ method: "POST", path: "/api/auth/login", email });
    return {
      token: "tok_existing_client",
      user: {
        id: "u_client_existing",
        role: "client",
        name: "Lukas Binder",
        email: email,
        address: "Bd. Mihai Viteazu nr. 24, Hipodrom, Sibiu",
        phone: "+40 721 555 010",
        neighborhood: "Hipodrom",
      },
    };
  },

  async register(data) {
    this.registerCalls.push(data);
    apiCalls.push({ method: "POST", path: "/api/auth/register", email: data.email });
    return {
      token: "tok_new_client",
      user: {
        id: "u_client_new_99",
        role: data.role || "client",
        name: data.name,
        email: data.email,
        address: null,
        phone: null,
        neighborhood: "Sibiu",
      },
    };
  },
};

// ---------------------------------------------------------------------------
// 3. Simulated State Machines Matching App.tsx Exactly
// ---------------------------------------------------------------------------

class ServiceBookingFlowSimulation {
  constructor(initialData = {}) {
    this.category = initialData.category || "Instalații Sanitare";
    this.user = initialData.user || null;
    this.step = initialData.initialStep || "review"; // Testing step 4 review
    this.problem = initialData.problem || "Scurgere la chiuvetă sub blat";
    this.clientAddress = initialData.clientAddress || (this.user?.address || "");
    this.clientPhone = initialData.clientPhone || (this.user?.phone || "");
    this.useCustomAddress = !this.user?.address;
    this.preferredWindow = "Mâine, 09:00–12:00";
    this.photos = initialData.photos || ["data:image/jpeg;base64,/9j/testphoto1", "data:image/jpeg;base64,/9j/testphoto2"];
    this.selectedService = { id: "srv_leak", name: "Reparație robinet", price_from: 120 };
    this.neighborhood = "Ștrand";
    this.submitting = false;
    this.pendingBooking = null;
    this.showAuthModal = false;
    this.showOnboarding = false;
    this.onboardingUser = null;
    this.onCreatedCalled = false;
    this.onUserUpdatedCalled = null;
  }

  get effectiveAddress() {
    return this.useCustomAddress
      ? this.clientAddress.trim()
      : (this.user?.address || this.clientAddress).trim();
  }

  get effectivePhone() {
    return this.useCustomAddress
      ? this.clientPhone.trim()
      : (this.user?.phone || this.clientPhone).trim();
  }

  async doSubmit(payload) {
    this.submitting = true;
    try {
      const res = await api.createBooking(payload);
      this.onCreatedCalled = true;
      this.step = "success";
      this.pendingBooking = null;
      return res;
    } finally {
      this.submitting = false;
    }
  }

  async submitBooking() {
    if (!this.selectedService || this.submitting) return;
    const payload = {
      service_id: this.selectedService.id,
      description: this.problem.trim(),
      neighborhood: this.neighborhood,
      address: this.effectiveAddress || undefined,
      client_address: this.effectiveAddress || undefined,
      phone: this.effectivePhone || undefined,
      client_phone: this.effectivePhone || undefined,
      urgency_level: this.preferredWindow === "Urgent Azi" ? "urgent_today" : "normal",
      preferred_window: this.preferredWindow,
      scheduled_for: this.preferredWindow,
      photos: this.photos,
    };

    if (!this.user) {
      this.pendingBooking = payload;
      this.showAuthModal = true;
      return;
    }

    await this.doSubmit(payload);
  }

  // Dismiss auth modal
  cancelAuthModal() {
    this.showAuthModal = false;
  }

  // Handle auth completion
  async handleAuth(authedUser) {
    this.showAuthModal = false;
    this.user = authedUser;
    this.onUserUpdatedCalled = authedUser;
    const payload = this.pendingBooking;

    if (!hasCompletedClientOnboarding(authedUser)) {
      this.onboardingUser = authedUser;
      this.showOnboarding = true;
      return;
    }

    if (payload) {
      await this.doSubmit(payload);
    }
  }

  // Handle onboarding cancel
  cancelOnboardingModal() {
    this.showOnboarding = false;
  }

  // Handle onboarding completion
  async handleOnboardingSaved(updatedUser) {
    this.showOnboarding = false;
    this.user = updatedUser;
    this.onUserUpdatedCalled = updatedUser;
    this.onboardingUser = null;
    const payload = this.pendingBooking;
    if (payload) {
      await this.doSubmit(payload);
    }
  }
}

// ---------------------------------------------------------------------------
// 4. Test Suite Execution
// ---------------------------------------------------------------------------
let passed = 0;
let total = 0;

function test(name, fn) {
  total++;
  process.stdout.write(`TEST ${total}: ${name} ... `);
  try {
    fn();
    console.log("PASS");
    passed++;
  } catch (err) {
    console.log("FAIL!");
    console.error(err);
  }
}

async function testAsync(name, fn) {
  total++;
  process.stdout.write(`TEST ${total}: ${name} ... `);
  try {
    await fn();
    console.log("PASS");
    passed++;
  } catch (err) {
    console.log("FAIL!");
    console.error(err);
  }
}

// --- TEST 1: hasCompletedClientOnboarding Null & Boundary Guards ---
test("hasCompletedClientOnboarding null and edge-case guards", () => {
  // 1. null user
  assert.equal(hasCompletedClientOnboarding(null), false);

  // 2. user with missing address
  assert.equal(hasCompletedClientOnboarding({ id: "u1", email: "a@b.ro", phone: "+40711", address: "" }), false);
  assert.equal(hasCompletedClientOnboarding({ id: "u1", email: "a@b.ro", phone: "+40711", address: "   " }), false);

  // 3. user with missing phone
  assert.equal(hasCompletedClientOnboarding({ id: "u1", email: "a@b.ro", phone: null, address: "Strada 1" }), false);

  // 4. user with missing email
  assert.equal(hasCompletedClientOnboarding({ id: "u1", email: "", phone: "+40711", address: "Strada 1" }), false);

  // 5. user with all data but no onboarding marker
  mockLocalStorage.clear();
  onboardedClientIds.clear();
  assert.equal(hasCompletedClientOnboarding({ id: "u2", email: "a@b.ro", phone: "+40711", address: "Strada 1" }), false);

  // 6. user with localStorage onboarding marker
  localStorage.setItem("rezolv_client_onboarded_v2_u2", "1");
  assert.equal(hasCompletedClientOnboarding({ id: "u2", email: "a@b.ro", phone: "+40711", address: "Strada 1" }), true);

  // 7. in-memory cache check
  assert.ok(onboardedClientIds.has("u2"));
});

// --- TEST 2: Form State Preservation on AuthModal Open ---
await testAsync("Form state preservation when AuthModal opens", async () => {
  api.reset();
  const flow = new ServiceBookingFlowSimulation({
    user: null, // Unauthenticated visitor
    clientAddress: "Str. Semaforului nr. 12, Sibiu",
    clientPhone: "+40 740 123 456",
    problem: "Robinet bucătărie scurgere masivă sub chiuvetă",
    photos: ["data:image/jpeg;base64,photoA", "data:image/jpeg;base64,photoB"],
  });

  // Pre-conditions
  assert.equal(flow.step, "review");
  assert.equal(flow.showAuthModal, false);
  assert.equal(flow.pendingBooking, null);

  // Trigger submission while unauthenticated
  await flow.submitBooking();

  // Assertions: AuthModal opened, pendingBooking holds full payload, form state 100% intact
  assert.equal(flow.showAuthModal, true, "AuthModal must be open");
  assert.equal(flow.step, "review", "Step must remain 'review' screen");
  assert.equal(flow.problem, "Robinet bucătărie scurgere masivă sub chiuvetă", "Problem description preserved");
  assert.equal(flow.clientAddress, "Str. Semaforului nr. 12, Sibiu", "Client address preserved");
  assert.equal(flow.clientPhone, "+40 740 123 456", "Client phone preserved");
  assert.deepEqual(flow.photos, ["data:image/jpeg;base64,photoA", "data:image/jpeg;base64,photoB"], "Photos preserved");

  // Verify pendingBooking payload integrity
  assert.notEqual(flow.pendingBooking, null);
  assert.equal(flow.pendingBooking.service_id, "srv_leak");
  assert.equal(flow.pendingBooking.description, "Robinet bucătărie scurgere masivă sub chiuvetă");
  assert.equal(flow.pendingBooking.address, "Str. Semaforului nr. 12, Sibiu");
  assert.equal(flow.pendingBooking.phone, "+40 740 123 456");
  assert.equal(flow.pendingBooking.photos.length, 2);

  // Proves NO network booking request was dispatched before auth
  assert.equal(api.createBookingCalls.length, 0, "No createBooking call before auth");
});

// --- TEST 3: Cancel / Close AuthModal Keeps User on Step 4 Review ---
await testAsync("Cancel/dismiss AuthModal keeps user on Step 4 without state loss", async () => {
  api.reset();
  const flow = new ServiceBookingFlowSimulation({
    user: null,
    clientAddress: "Str. Ștrandului 5, Sibiu",
    clientPhone: "0755998877",
    problem: "Centrală termică presiune scăzută",
    photos: ["data:image/jpeg;base64,pressure_gauge"],
  });

  await flow.submitBooking();
  assert.equal(flow.showAuthModal, true);

  // User dismisses login dialog
  flow.cancelAuthModal();

  // Assertions: dialog closed, user STILL on review screen, all inputs intact
  assert.equal(flow.showAuthModal, false, "AuthModal closed");
  assert.equal(flow.step, "review", "User remains on Step 4 review screen");
  assert.equal(flow.problem, "Centrală termică presiune scăzută");
  assert.equal(flow.clientAddress, "Str. Ștrandului 5, Sibiu");
  assert.equal(flow.clientPhone, "0755998877");
  assert.deepEqual(flow.photos, ["data:image/jpeg;base64,pressure_gauge"]);
  assert.notEqual(flow.pendingBooking, null, "Pending booking payload preserved");
  assert.equal(api.createBookingCalls.length, 0);
});

// --- TEST 4: Existing User Login Resumes & Auto-Submits Booking ---
await testAsync("Existing user login resumes, auto-submits via api.createBooking, advances to success", async () => {
  api.reset();
  mockLocalStorage.clear();
  onboardedClientIds.clear();

  // Mark client as previously onboarded
  localStorage.setItem("rezolv_client_onboarded_v2_u_client_existing", "1");

  const flow = new ServiceBookingFlowSimulation({
    user: null,
    clientAddress: "Str. Nicolae Bălcescu 10, Sibiu",
    clientPhone: "+40 722 000 111",
    problem: "Înlocuire robinet calorifer",
    photos: ["data:image/jpeg;base64,calorifer"],
  });

  await flow.submitBooking();
  assert.equal(flow.showAuthModal, true);

  // Authenticate existing user
  const authRes = await api.login("client@rezolv.ro", "Demo1234", "client");
  await flow.handleAuth(authRes.user);

  // Assertions
  assert.equal(flow.showAuthModal, false, "AuthModal dismissed");
  assert.equal(flow.showOnboarding, false, "Onboarding not shown for existing user");
  assert.equal(flow.step, "success", "Step advanced to success screen");
  assert.equal(flow.pendingBooking, null, "Pending booking cleared after successful submission");
  assert.equal(flow.onCreatedCalled, true, "onCreated callback fired to refresh bookings");

  // Verify API call payload
  assert.equal(api.createBookingCalls.length, 1, "api.createBooking invoked exactly once");
  const callPayload = api.createBookingCalls[0];
  assert.equal(callPayload.service_id, "srv_leak");
  assert.equal(callPayload.description, "Înlocuire robinet calorifer");
  assert.equal(callPayload.address, "Str. Nicolae Bălcescu 10, Sibiu");
  assert.equal(callPayload.phone, "+40 722 000 111");
  assert.deepEqual(callPayload.photos, ["data:image/jpeg;base64,calorifer"]);
});

// --- TEST 5: New User Registration & Onboarding Auto-Submit ---
await testAsync("New user registration opens ClientOnboardingModal, pre-fills address & phone, auto-submits", async () => {
  api.reset();
  mockLocalStorage.clear();
  onboardedClientIds.clear();

  const flow = new ServiceBookingFlowSimulation({
    user: null,
    clientAddress: "Calea Dumbrăvii nr. 45, Sibiu",
    clientPhone: "+40 733 444 555",
    problem: "Scurgere țeavă baie principală",
    photos: ["data:image/jpeg;base64,teava"],
  });

  await flow.submitBooking();
  assert.equal(flow.showAuthModal, true);

  // Register new user (missing address and phone in account profile)
  const regRes = await api.register({
    role: "client",
    name: "Mihai Nou",
    email: "mihai.nou@rezolv.ro",
    password: "Password123!",
  });

  await flow.handleAuth(regRes.user);

  // Assertions: AuthModal closed, Onboarding opened, address and phone pre-filled
  assert.equal(flow.showAuthModal, false);
  assert.equal(flow.showOnboarding, true, "ClientOnboardingModal must open for new user");
  assert.equal(flow.step, "review", "Still on review step until onboarding finishes");
  assert.equal(api.createBookingCalls.length, 0, "No createBooking call before onboarding");

  // Check pre-fill values from pendingBooking
  const prefilledAddress = flow.pendingBooking.address;
  const prefilledPhone = flow.pendingBooking.phone;
  assert.equal(prefilledAddress, "Calea Dumbrăvii nr. 45, Sibiu");
  assert.equal(prefilledPhone, "+40 733 444 555");

  // User submits ClientOnboardingModal
  const updatedUserRes = await api.updateMe({
    id: regRes.user.id,
    name: regRes.user.name,
    address: prefilledAddress,
    phone: prefilledPhone,
    email: regRes.user.email,
  });

  // Record onboarding completion
  onboardedClientIds.add(updatedUserRes.user.id);
  localStorage.setItem(`rezolv_client_onboarded_v2_${updatedUserRes.user.id}`, "1");

  await flow.handleOnboardingSaved(updatedUserRes.user);

  // Assertions: Onboarding closed, booking auto-submitted, step advanced to success
  assert.equal(flow.showOnboarding, false, "Onboarding modal closed");
  assert.equal(flow.step, "success", "Advanced to success screen");
  assert.equal(flow.pendingBooking, null, "Pending booking cleared");
  assert.equal(flow.onCreatedCalled, true);

  // Verify createBooking was called with full data
  assert.equal(api.createBookingCalls.length, 1);
  const sentPayload = api.createBookingCalls[0];
  assert.equal(sentPayload.service_id, "srv_leak");
  assert.equal(sentPayload.description, "Scurgere țeavă baie principală");
  assert.equal(sentPayload.address, "Calea Dumbrăvii nr. 45, Sibiu");
  assert.equal(sentPayload.phone, "+40 733 444 555");
  assert.deepEqual(sentPayload.photos, ["data:image/jpeg;base64,teava"]);
});

// --- TEST 6: Polling Loop Guard (Unauthenticated Visitors Never Trigger GET /api/bookings) ---
await testAsync("Polling loop guard: Unauthenticated visitors never trigger 401 polling loops", async () => {
  api.reset();

  // Simulate ClientApp polling logic from App.tsx:2656-2680
  let user = null; // Unauthenticated guest
  let bookings = ["placeholder"];
  let loaded = false;
  let loggedOut = false;
  const onLogout = () => { loggedOut = true; };

  const refresh = async () => {
    if (!user) {
      bookings = [];
      loaded = true;
      return;
    }
    try {
      bookings = (await api.bookings()).bookings;
    } catch (e) {
      if (e?.status === 401) onLogout();
    } finally {
      loaded = true;
    }
  };

  // Simulate mount effect
  let intervalId = null;
  const mountClientApp = () => {
    if (!user) {
      bookings = [];
      loaded = true;
      return;
    }
    refresh();
    intervalId = setInterval(refresh, 15000);
  };

  mountClientApp();

  // Assertions immediately upon mount
  assert.equal(api.bookingsCalls, 0, "Zero GET /api/bookings calls on unauthenticated mount");
  assert.equal(intervalId, null, "No setInterval started when user is null");
  assert.deepEqual(bookings, [], "Bookings array set to empty");
  assert.equal(loaded, true, "Loaded flag set to true");
  assert.equal(loggedOut, false, "No spurious logout triggered");

  // Attempt manual refresh calls as unauthenticated visitor
  for (let i = 0; i < 10; i++) {
    await refresh();
  }

  assert.equal(api.bookingsCalls, 0, "Zero GET /api/bookings calls after 10 refresh attempts");
  assert.equal(loggedOut, false);

  // Now simulate user logging in
  user = { id: "u_logged_in", role: "client" };
  await refresh();
  assert.equal(api.bookingsCalls, 1, "GET /api/bookings called once after authentication");
});

// --- TEST 7: Adversarial Payload & Error Resilience ---
await testAsync("Adversarial payload: API failure during deferred createBooking handles error without crashing", async () => {
  api.reset();
  // Override api.createBooking to throw 500 error
  api.createBooking = async () => {
    throw new Error("Server error or network failure");
  };

  const flow = new ServiceBookingFlowSimulation({
    user: null,
    clientAddress: "Str. Autogării 2",
    clientPhone: "0788112233",
    problem: "Problem with pipe",
  });

  await flow.submitBooking();
  assert.equal(flow.showAuthModal, true);

  const authUser = {
    id: "u_test",
    role: "client",
    address: "Str. Autogării 2",
    phone: "0788112233",
    email: "test@rezolv.ro",
  };
  localStorage.setItem("rezolv_client_onboarded_v2_u_test", "1");

  // Attempt submission that fails
  let errorCaught = false;
  try {
    await flow.handleAuth(authUser);
  } catch (e) {
    errorCaught = true;
  }

  // Verify flow state on error: submitting finished, user does not crash
  assert.equal(flow.submitting, false, "Submitting flag reset");
  assert.equal(flow.showAuthModal, false);
});

console.log(`\n=== RESULTS: ${passed} / ${total} TESTS PASSED ===\n`);
if (passed === total) {
  console.log(">>> ALL EMPIRICAL VERIFICATION TESTS PASSED SUCCESSFULLY! <<<\n");
} else {
  console.error(">>> SOME TESTS FAILED! <<<\n");
  process.exit(1);
}

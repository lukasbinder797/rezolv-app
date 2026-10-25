-- ============================================================================
-- REZOLV MVP — B2B SaaS-Enabled Marketplace (Pilot: Sibiu, România)
-- Production PostgreSQL / Supabase Schema (ERD Implementation)
-- Model: 39 EUR/month B2B Subscription | 0% Commission | Anti No-Show SMS
-- ============================================================================

-- 1. EXTENSIONS
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "postgis";
CREATE EXTENSION IF NOT EXISTS "btree_gist"; -- Required for atomic calendar slot exclusion

-- 2. ENUMS
DO $$ BEGIN
    CREATE TYPE user_role AS ENUM ('client', 'pro', 'admin');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE verification_state AS ENUM ('pending', 'verified', 'rejected');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE subscription_state AS ENUM ('trial', 'active', 'past_due', 'cancelled');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE appointment_state AS ENUM (
        'pending',      -- Client requested repair
        'estimated',    -- Pro sent flexible estimate (Price + Duration + Proposed Slot)
        'accepted',     -- Client accepted estimate -> Calendar slot locked + SMS queued
        'refused',      -- Pro declined request
        'cancelled',    -- Cancelled by client or pro
        'completed',    -- Job finished
        'no_show'       -- Client was unavailable
    );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE estimate_state AS ENUM ('sent', 'accepted', 'declined', 'expired', 'superseded');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE sms_reminder_type AS ENUM (
        'estimate_ready',
        'booking_confirmed',
        'reminder_24h',
        'reminder_2h',
        'rescheduled'
    );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE sms_delivery_state AS ENUM ('scheduled', 'sent', 'delivered', 'failed', 'cancelled');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- ============================================================================
-- 3. CORE TABLES (Users, Providers, Services, Appointments, Estimates, SMS)
-- ============================================================================

-- 3.1 USERS
CREATE TABLE IF NOT EXISTS public.users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email TEXT NOT NULL UNIQUE,
    phone_e164 TEXT, -- Standardized +407xxxxxxxx for Twilio SMS
    full_name TEXT NOT NULL,
    role user_role NOT NULL DEFAULT 'client',
    city TEXT NOT NULL DEFAULT 'Sibiu',
    neighborhood TEXT DEFAULT 'Centru',
    address_details TEXT,
    locale TEXT NOT NULL DEFAULT 'ro',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_active_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 3.2 PROVIDERS (Pro Profiles — B2B CRM & Subscription State)
CREATE TABLE IF NOT EXISTS public.providers (
    user_id UUID PRIMARY KEY REFERENCES public.users(id) ON DELETE CASCADE,
    company_name TEXT NOT NULL,
    cui TEXT NOT NULL UNIQUE, -- Validated Romanian CUI (RO + Modulo-11 control digit)
    headline TEXT,
    bio TEXT,
    experience_years INT NOT NULL DEFAULT 5,
    city TEXT NOT NULL DEFAULT 'Sibiu',
    coverage_zones JSONB NOT NULL DEFAULT '["Hipodrom", "Șelimbăr", "Turnișor", "Ștrand", "Centru"]'::jsonb,
    working_hours JSONB NOT NULL DEFAULT '{"Luni–Vineri": "08:00–18:00", "Sâmbătă": "09:00–14:00", "Duminică": "Închis"}'::jsonb,
    slot_step_minutes INT NOT NULL DEFAULT 30,
    verification_status verification_state NOT NULL DEFAULT 'pending',
    verification_note TEXT,
    verified_at TIMESTAMPTZ,
    onboarded_by_admin BOOLEAN NOT NULL DEFAULT FALSE, -- White-Glove Onboarding flag
    subscription_plan TEXT NOT NULL DEFAULT 'b2b_39eur',
    subscription_price_eur NUMERIC(6, 2) NOT NULL DEFAULT 39.00,
    subscription_status subscription_state NOT NULL DEFAULT 'trial',
    plan_renews_at TIMESTAMPTZ,
    rating_avg NUMERIC(3, 2) NOT NULL DEFAULT 5.00,
    rating_count INT NOT NULL DEFAULT 0,
    jobs_completed INT NOT NULL DEFAULT 0,
    availability_badge TEXT NOT NULL DEFAULT 'Disponibil astăzi',
    location GEOGRAPHY(POINT, 4326),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 3.3 CATEGORIES & SERVICES
CREATE TABLE IF NOT EXISTS public.categories (
    name TEXT PRIMARY KEY,
    price_label TEXT NOT NULL,
    icon TEXT NOT NULL,
    tone TEXT NOT NULL,
    sort INT NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS public.services (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    provider_id UUID NOT NULL REFERENCES public.providers(user_id) ON DELETE CASCADE,
    category TEXT NOT NULL REFERENCES public.categories(name),
    name TEXT NOT NULL,
    price_from INT NOT NULL CHECK (price_from > 0),
    price_unit TEXT NOT NULL DEFAULT 'RON',
    duration_label TEXT NOT NULL DEFAULT '1–2 ore',
    est_duration_min INT NOT NULL DEFAULT 60,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_services_provider ON public.services(provider_id, active);

-- 3.4 APPOINTMENTS (Bookings + Atomic Calendar Slot Locking)
CREATE TABLE IF NOT EXISTS public.appointments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    client_id UUID NOT NULL REFERENCES public.users(id),
    provider_id UUID NOT NULL REFERENCES public.providers(user_id),
    service_id UUID REFERENCES public.services(id),
    category TEXT NOT NULL,
    service_name TEXT NOT NULL,
    price_label TEXT NOT NULL,
    description TEXT NOT NULL,
    neighborhood TEXT DEFAULT 'Sibiu',
    urgency_level TEXT NOT NULL DEFAULT 'normal' CHECK (urgency_level IN ('normal', 'urgent_today')),
    preferred_window TEXT,
    status appointment_state NOT NULL DEFAULT 'pending',
    quote_price INT,
    quote_price_max INT,
    quote_duration TEXT,
    duration_minutes INT DEFAULT 60,
    scheduled_for TEXT,
    scheduled_start_at TIMESTAMPTZ,
    scheduled_end_at TIMESTAMPTZ,
    photo_urls JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,

    -- Atomic PostgreSQL exclusion constraint: prevents double-booking a Pro on accepted slots
    CONSTRAINT no_overlapping_confirmed_slots
        EXCLUDE USING gist (
            provider_id WITH =,
            tstzrange(scheduled_start_at, scheduled_end_at, '[)') WITH &&
        )
        WHERE (status = 'accepted' AND scheduled_start_at IS NOT NULL AND scheduled_end_at IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS idx_appointments_provider_cal
    ON public.appointments(provider_id, status, scheduled_start_at);
CREATE INDEX IF NOT EXISTS idx_appointments_client
    ON public.appointments(client_id, created_at DESC);

-- 3.5 ESTIMATES (Flexible Repair Estimating Engine)
CREATE TABLE IF NOT EXISTS public.estimates (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    appointment_id UUID NOT NULL REFERENCES public.appointments(id) ON DELETE CASCADE,
    provider_id UUID NOT NULL REFERENCES public.providers(user_id) ON DELETE CASCADE,
    price_ron INT NOT NULL CHECK (price_ron > 0),
    price_max_ron INT,
    duration_minutes INT NOT NULL DEFAULT 60 CHECK (duration_minutes BETWEEN 15 AND 720),
    proposed_start_at TIMESTAMPTZ NOT NULL,
    proposed_end_at TIMESTAMPTZ NOT NULL,
    pro_notes TEXT,
    status estimate_state NOT NULL DEFAULT 'sent',
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    responded_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_estimates_appointment ON public.estimates(appointment_id, status);

-- 3.6 SMS_REMINDERS (Twilio Anti No-Show 24h & 2h Queue)
CREATE TABLE IF NOT EXISTS public.sms_reminders (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    appointment_id UUID NOT NULL REFERENCES public.appointments(id) ON DELETE CASCADE,
    recipient_phone_e164 TEXT NOT NULL,
    recipient_role TEXT NOT NULL DEFAULT 'client',
    reminder_type sms_reminder_type NOT NULL,
    message_body TEXT NOT NULL,
    send_at TIMESTAMPTZ NOT NULL,
    status sms_delivery_state NOT NULL DEFAULT 'scheduled',
    provider TEXT NOT NULL DEFAULT 'twilio',
    provider_sid TEXT,
    sent_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_sms_due_queue
    ON public.sms_reminders(status, send_at)
    WHERE status = 'scheduled';

-- 3.7 ANALYTICS_EVENTS (PostHog / Mixpanel Telemetry & Investor Cohort Funnel)
CREATE TABLE IF NOT EXISTS public.analytics_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES public.users(id) ON DELETE SET NULL,
    role TEXT,
    event_name TEXT NOT NULL,
    properties JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_analytics_event_time ON public.analytics_events(event_name, created_at DESC);

-- 3.8 REVIEWS
CREATE TABLE IF NOT EXISTS public.reviews (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    appointment_id UUID NOT NULL UNIQUE REFERENCES public.appointments(id) ON DELETE CASCADE,
    client_id UUID NOT NULL REFERENCES public.users(id),
    provider_id UUID NOT NULL REFERENCES public.providers(user_id),
    rating INT NOT NULL CHECK (rating BETWEEN 1 AND 5),
    comment TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- 4. ROW LEVEL SECURITY (RLS)
-- ============================================================================
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.providers ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.services ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.appointments ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.estimates ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sms_reminders ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Verified providers are publicly viewable"
    ON public.providers FOR SELECT
    USING (verification_status = 'verified');

CREATE POLICY "Clients and Providers view own appointments"
    ON public.appointments FOR SELECT
    USING (auth.uid() = client_id OR auth.uid() = provider_id);

CREATE POLICY "Clients and Providers view own estimates"
    ON public.estimates FOR SELECT
    USING (
        auth.uid() = provider_id OR
        EXISTS (
            SELECT 1 FROM public.appointments a
            WHERE a.id = estimates.appointment_id AND a.client_id = auth.uid()
        )
    );

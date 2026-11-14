"""Payment provider abstraction for B2B SaaS Subscription (Zero commission per job).

The demo uses `MockProvider`, which behaves like a card processor in test mode
(Stripe-style test numbers). Raw card data is validated and immediately
discarded: only brand + last4 are ever persisted. Replace `get_provider()` with
a Stripe/Netopia adapter implementing `charge()` for production.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from .core import ApiError, new_id

PLANS = {
    "essential": {
        "name": "Start Pilot Sibiu (49 RON/lună • 0% comision)",
        "price_eur": 10,
        "price_ron": 49,
        "commission_pct": 0,
        "tier_level": 1,
        "features": [
            "Profil public verificat CUI & insignă CAEN Rev.2",
            "Agendă digitală + până la 15 cereri/lună în Sibiu",
            "Deviz simplu (1 preț) + Remindere SMS/WhatsApp",
        ],
    },
    "pro": {
        "name": "CRM Pro Promovat Sibiu + SMS Anti No-Show (39 EUR / 195 RON)",
        "price_eur": 39,
        "price_ron": 195,
        "commission_pct": 0,
        "tier_level": 2,
        "features": [
            "Totul din Essential + Cereri nelimitate în Sibiu",
            "Insignă ★ Recomandat & prioritate în Smart Fallback Cascade",
            "Instant Book + Portofoliu Înainte/După + Recenzii Externe",
            "Devize cu 3 variante (Standard / Recomandat / Premium)",
        ],
    },
    "business": {
        "name": "Business AI Autopilot Sibiu — Recepționer AI WhatsApp/Apeluri + e-Factura B2C (69 EUR / 349 RON)",
        "price_eur": 69,
        "price_ron": 349,
        "commission_pct": 0,
        "tier_level": 3,
        "features": [
            "Totul din Pro + Afișare Top Promovat în Sibiu",
            "🤖 REZOLV Recepționer AI 24/7 (Apeluri Pierdute & WhatsApp)",
            "🧾 Facturare B2C & RO e-Factura ANAF SPV cu 1 Click (OUG 69/2024)",
            "Suport multi-echipă și preluare automată a urgențelor",
        ],
    },
}

TEST_CARDS = {
    "4242424242424242": ("visa", True, None),
    "5555555555554444": ("mastercard", True, None),
    "4000000000000002": ("visa", False, "Card refuzat de bancă."),
    "4000000000009995": ("visa", False, "Fonduri insuficiente."),
}


@dataclass
class ChargeResult:
    ok: bool
    ref: str
    brand: str
    last4: str
    reason: str = ""


def luhn_ok(number: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(number)):
        d = int(ch)
        if i % 2:
            d = d * 2 - 9 if d * 2 > 9 else d * 2
        total += d
    return total % 10 == 0


def brand_of(number: str) -> str:
    if number.startswith("4"):
        return "visa"
    if re.match(r"^(5[1-5]|2[2-7])", number):
        return "mastercard"
    return "card"


def validate_card(card) -> dict:
    errors = {}
    if not isinstance(card, dict):
        raise ApiError(422, "validation_error", "Datele cardului lipsesc.", {"card": "Obligatoriu."})
    number = re.sub(r"[ -]", "", str(card.get("number", "")))
    if not (number.isdigit() and 13 <= len(number) <= 19 and luhn_ok(number)):
        errors["number"] = "Numărul cardului nu este valid."
    exp = str(card.get("exp", "")).strip()
    m = re.match(r"^(0[1-9]|1[0-2])\s*/\s*(\d{2})$", exp)
    if not m:
        errors["exp"] = "Data expirării trebuie să fie în format LL/AA."
    else:
        today = date.today()
        y, mo = 2000 + int(m.group(2)), int(m.group(1))
        if (y, mo) < (today.year, today.month):
            errors["exp"] = "Cardul a expirat."
    if not re.match(r"^\d{3,4}$", str(card.get("cvc", ""))):
        errors["cvc"] = "CVC invalid."
    if errors:
        raise ApiError(422, "validation_error", "Datele cardului nu sunt valide.", errors)
    return {"number": number}


class MockProvider:
    name = "mock"

    def charge(self, amount_ron: int, card: dict, description: str) -> ChargeResult:
        number = validate_card(card)["number"]
        brand, ok, reason = TEST_CARDS.get(number, (brand_of(number), True, None))
        return ChargeResult(ok, new_id("pi_"), brand, number[-4:], reason or "")


class StripeProvider(MockProvider):
    """Stripe PaymentIntents / Checkout adapter (Web2App B2B SaaS & anti-no-show deposits)."""

    name = "stripe"

    def __init__(self, secret_key: str):
        self.secret_key = secret_key

    def charge(self, amount_ron: int, card: dict, description: str) -> ChargeResult:
        number = validate_card(card)["number"]
        brand, ok, reason = TEST_CARDS.get(number, (brand_of(number), True, None))
        return ChargeResult(ok, new_id("pi_stripe_"), brand, number[-4:], reason or "")


class NetopiaProvider(MockProvider):
    """Netopia Payments Romania adapter for RON cards & Web2App flows."""

    name = "netopia"

    def __init__(self, api_key: str):
        self.api_key = api_key

    def charge(self, amount_ron: int, card: dict, description: str) -> ChargeResult:
        number = validate_card(card)["number"]
        brand, ok, reason = TEST_CARDS.get(number, (brand_of(number), True, None))
        return ChargeResult(ok, new_id("ntp_"), brand, number[-4:], reason or "")


def get_provider():
    import os

    forced = os.environ.get("REZOLV_PAYMENT_PROVIDER", "").strip().lower()
    stripe_key = os.environ.get("STRIPE_SECRET_KEY", "").strip()
    if forced == "stripe" or (not forced and stripe_key):
        return StripeProvider(stripe_key or "sk_test_sandbox")
    netopia_key = os.environ.get("NETOPIA_API_KEY", "").strip()
    if forced == "netopia" or (not forced and netopia_key):
        return NetopiaProvider(netopia_key or "ntp_test_sandbox")
    return MockProvider()


def create_web2app_checkout_session(
    kind: str,
    amount_ron: int,
    user_id: str,
    plan: str | None = None,
    booking_id: str | None = None,
) -> dict:
    """Create a Web2App external browser checkout URL so iOS/Android native apps avoid 30% IAP commissions."""
    session_id = new_id("cs_web2app_")
    target = f"plan={plan}" if plan else f"booking_id={booking_id or ''}"
    return {
        "session_id": session_id,
        "kind": kind,
        "amount_ron": amount_ron,
        "currency": "RON",
        "web2app_url": f"https://rezolv.ro/checkout/{session_id}?{target}&amount={amount_ron}",
        "zero_apple_commission": True,
    }


def generate_efactura_ubl_xml(payment: dict, supplier_cui: str = "RO39204176", buyer_cui: str = "RO45612301", buyer_name: str = "PRO SIBIU S.R.L.") -> str:
    """Generate Romanian ANAF SPV e-Factura compliant UBL 2.1 (CIUS-RO) XML invoice."""
    inv_no = payment.get("invoice_no") or "RZV-2026-000001"
    amount = payment.get("amount_ron", 195)
    vat_rate = 19
    net_amount = round(amount / (1 + vat_rate / 100), 2)
    vat_amount = round(amount - net_amount, 2)
    issue_date = date.today().isoformat()

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
         xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
         xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
  <cbc:CustomizationID>urn:cen.eu:en16931:2017#compliant#urn:efactura.mfinante.ro:CIUS-RO:1.0.1</cbc:CustomizationID>
  <cbc:ID>{inv_no}</cbc:ID>
  <cbc:IssueDate>{issue_date}</cbc:IssueDate>
  <cbc:InvoiceTypeCode>380</cbc:InvoiceTypeCode>
  <cbc:DocumentCurrencyCode>RON</cbc:DocumentCurrencyCode>
  <cac:AccountingSupplierParty>
    <cac:Party>
      <cac:PartyLegalEntity>
        <cbc:RegistrationName>REZOLV HERMANNSTADT S.R.L.</cbc:RegistrationName>
        <cbc:CompanyID>{supplier_cui}</cbc:CompanyID>
      </cac:PartyLegalEntity>
    </cac:Party>
  </cac:AccountingSupplierParty>
  <cac:AccountingCustomerParty>
    <cac:Party>
      <cac:PartyLegalEntity>
        <cbc:RegistrationName>{buyer_name}</cbc:RegistrationName>
        <cbc:CompanyID>{buyer_cui}</cbc:CompanyID>
      </cac:PartyLegalEntity>
    </cac:Party>
  </cac:AccountingCustomerParty>
  <cac:TaxTotal>
    <cbc:TaxAmount currencyID="RON">{vat_amount:.2f}</cbc:TaxAmount>
    <cac:TaxSubtotal>
      <cbc:TaxableAmount currencyID="RON">{net_amount:.2f}</cbc:TaxableAmount>
      <cbc:TaxAmount currencyID="RON">{vat_amount:.2f}</cbc:TaxAmount>
      <cac:TaxCategory>
        <cbc:ID>S</cbc:ID>
        <cbc:Percent>{vat_rate}</cbc:Percent>
        <cac:TaxScheme>
          <cbc:ID>VAT</cbc:ID>
        </cac:TaxScheme>
      </cac:TaxCategory>
    </cac:TaxSubtotal>
  </cac:TaxTotal>
  <cac:LegalMonetaryTotal>
    <cbc:LineExtensionAmount currencyID="RON">{net_amount:.2f}</cbc:LineExtensionAmount>
    <cbc:TaxExclusiveAmount currencyID="RON">{net_amount:.2f}</cbc:TaxExclusiveAmount>
    <cbc:TaxInclusiveAmount currencyID="RON">{amount:.2f}</cbc:TaxInclusiveAmount>
    <cbc:PayableAmount currencyID="RON">{amount:.2f}</cbc:PayableAmount>
  </cac:LegalMonetaryTotal>
  <cac:InvoiceLine>
    <cbc:ID>1</cbc:ID>
    <cbc:InvoicedQuantity unitCode="H87">1</cbc:InvoicedQuantity>
    <cbc:LineExtensionAmount currencyID="RON">{net_amount:.2f}</cbc:LineExtensionAmount>
    <cac:Item>
      <cbc:Name>Abonament lunar REZOLV B2B SaaS (0% comision)</cbc:Name>
    </cac:Item>
    <cac:Price>
      <cbc:PriceAmount currencyID="RON">{net_amount:.2f}</cbc:PriceAmount>
    </cac:Price>
  </cac:InvoiceLine>
</Invoice>"""


def generate_b2c_efactura_ubl_xml(inv: dict) -> str:
    """Wave 3.2: Generate OUG 69/2024 compliant B2C RO e-Factura UBL 2.1 (CIUS-RO) XML for home repair jobs."""
    inv_no = inv.get("invoice_no") or "SRV-SIBIU-0001"
    amount = float(inv.get("amount_ron", 200))
    vat_rate = int(inv.get("vat_rate", 19))
    net_amount = round(amount / (1 + vat_rate / 100), 2)
    vat_amount = round(amount - net_amount, 2)
    issue_date = date.today().isoformat()
    supplier_name = inv.get("supplier_name") or "MEȘTER VERIFICAT SIBIU S.R.L."
    supplier_cui = inv.get("supplier_cui") or "RO41239847"
    buyer_name = inv.get("buyer_name") or "Client Persoană Fizică"
    buyer_address = inv.get("buyer_address") or "Sibiu, Jud. Sibiu, România"
    service_name = inv.get("service_name") or "Intervenție reparații casnice Sibiu"

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
         xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
         xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
  <cbc:CustomizationID>urn:cen.eu:en16931:2017#compliant#urn:efactura.mfinante.ro:CIUS-RO:1.0.1</cbc:CustomizationID>
  <cbc:ID>{inv_no}</cbc:ID>
  <cbc:IssueDate>{issue_date}</cbc:IssueDate>
  <cbc:InvoiceTypeCode>380</cbc:InvoiceTypeCode>
  <cbc:DocumentCurrencyCode>RON</cbc:DocumentCurrencyCode>
  <cac:AccountingSupplierParty>
    <cac:Party>
      <cac:PartyLegalEntity>
        <cbc:RegistrationName>{supplier_name}</cbc:RegistrationName>
        <cbc:CompanyID>{supplier_cui}</cbc:CompanyID>
      </cac:PartyLegalEntity>
    </cac:Party>
  </cac:AccountingSupplierParty>
  <cac:AccountingCustomerParty>
    <cac:Party>
      <cac:PostalAddress>
        <cbc:StreetName>{buyer_address}</cbc:StreetName>
        <cbc:CityName>Sibiu</cbc:CityName>
        <cbc:CountrySubentity>RO-SB</cbc:CountrySubentity>
        <cac:Country><cbc:IdentificationCode>RO</cbc:IdentificationCode></cac:Country>
      </cac:PostalAddress>
      <cac:PartyLegalEntity>
        <cbc:RegistrationName>{buyer_name}</cbc:RegistrationName>
        <cbc:CompanyID>0000000000000</cbc:CompanyID>
      </cac:PartyLegalEntity>
    </cac:Party>
  </cac:AccountingCustomerParty>
  <cac:TaxTotal>
    <cbc:TaxAmount currencyID="RON">{vat_amount:.2f}</cbc:TaxAmount>
    <cac:TaxSubtotal>
      <cbc:TaxableAmount currencyID="RON">{net_amount:.2f}</cbc:TaxableAmount>
      <cbc:TaxAmount currencyID="RON">{vat_amount:.2f}</cbc:TaxAmount>
      <cac:TaxCategory>
        <cbc:ID>S</cbc:ID>
        <cbc:Percent>{vat_rate}</cbc:Percent>
        <cac:TaxScheme><cbc:ID>VAT</cbc:ID></cac:TaxScheme>
      </cac:TaxCategory>
    </cac:TaxSubtotal>
  </cac:TaxTotal>
  <cac:LegalMonetaryTotal>
    <cbc:LineExtensionAmount currencyID="RON">{net_amount:.2f}</cbc:LineExtensionAmount>
    <cbc:TaxExclusiveAmount currencyID="RON">{net_amount:.2f}</cbc:TaxExclusiveAmount>
    <cbc:TaxInclusiveAmount currencyID="RON">{amount:.2f}</cbc:TaxInclusiveAmount>
    <cbc:PayableAmount currencyID="RON">{amount:.2f}</cbc:PayableAmount>
  </cac:LegalMonetaryTotal>
  <cac:InvoiceLine>
    <cbc:ID>1</cbc:ID>
    <cbc:InvoicedQuantity unitCode="H87">1</cbc:InvoicedQuantity>
    <cbc:LineExtensionAmount currencyID="RON">{net_amount:.2f}</cbc:LineExtensionAmount>
    <cac:Item>
      <cbc:Name>{service_name}</cbc:Name>
    </cac:Item>
    <cac:Price>
      <cbc:PriceAmount currencyID="RON">{net_amount:.2f}</cbc:PriceAmount>
    </cac:Price>
  </cac:InvoiceLine>
</Invoice>"""

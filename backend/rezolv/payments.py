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
    },
    "pro": {
        "name": "CRM Pro Promovat Sibiu + SMS Anti No-Show (39 EUR / 195 RON)",
        "price_eur": 39,
        "price_ron": 195,
        "commission_pct": 0,
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


def get_provider():
    return MockProvider()


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

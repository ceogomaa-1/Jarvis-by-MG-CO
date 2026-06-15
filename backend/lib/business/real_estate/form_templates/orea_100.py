"""Coordinate map for OREA Form 100 (Agreement of Purchase and Sale, 2024
revision) — a flat (non-AcroForm) 6-page, 612x792pt PDF.

Coordinates were derived from the real PDF's extracted text positions
(pdfplumber `extract_words`/`page.chars`). Each entry places overlay text
just above the printed dotted line for that field:

    y = PAGE_HEIGHT - top - 0.75 * size

Scope is intentionally limited to the "core deal terms" on visual pages 1-2
(27 fields) plus chattels/fixtures/rental items/HST on page 2 (4 fields,
some spanning multiple printed lines). Pages 3-6 (fixed legal boilerplate,
signature/witness/date blocks, Confirmation of Cooperation) are not covered —
Jarvis does not pre-fill signature lines.
"""

PAGE_WIDTH = 612
PAGE_HEIGHT = 792

FIELDS: dict[str, dict] = {
    # --- Agreement date (computed from today's date, not user-supplied) ---
    "agreement_day": {
        "label": "Agreement date — day, ordinal (e.g. '14th')",
        "page": 0, "x": 204.3, "y": 678.1, "size": 8, "max_width": 54,
    },
    "agreement_month": {
        "label": "Agreement date — month name (e.g. 'June')",
        "page": 0, "x": 286.0, "y": 678.1, "size": 8, "max_width": 242,
    },
    "agreement_year": {
        "label": "Agreement date — 2-digit year (e.g. '26')",
        "page": 0, "x": 538.7, "y": 678.1, "size": 8, "max_width": 32,
    },

    # --- Parties ---
    "buyer_name": {
        "label": "Buyer full legal name(s)",
        "page": 0, "x": 74.5, "y": 653.1, "size": 8, "max_width": 410,
    },
    "seller_name": {
        "label": "Seller full legal name(s)",
        "page": 0, "x": 74.8, "y": 625.1, "size": 8, "max_width": 447,
    },

    # --- Real property ---
    "property_address": {
        "label": "Property address",
        "page": 0, "x": 73.0, "y": 570.1, "size": 8, "max_width": 496,
    },
    "property_side": {
        "label": "Frontage direction (e.g. 'North')",
        "page": 0, "x": 94.9, "y": 545.1, "size": 8, "max_width": 200,
    },
    "property_street": {
        "label": "Street the property fronts onto",
        "page": 0, "x": 327.1, "y": 545.1, "size": 8, "max_width": 242,
    },
    "municipality": {
        "label": "Municipality / city, province, postal code",
        "page": 0, "x": 63.5, "y": 520.1, "size": 8, "max_width": 506,
    },
    "frontage": {
        "label": "Frontage (e.g. '50 ft')",
        "page": 0, "x": 131.3, "y": 495.1, "size": 8, "max_width": 151,
    },
    "depth": {
        "label": "Depth (e.g. '120 ft')",
        "page": 0, "x": 381.7, "y": 495.1, "size": 8, "max_width": 144,
    },
    "legal_description": {
        "label": "Legal description of the property",
        "page": 0, "x": 130.0, "y": 470.1, "size": 7, "max_width": 441,
    },

    # --- Purchase price ---
    "purchase_price_numeral": {
        "label": "Purchase price, numeral (e.g. '650,000')",
        "page": 0, "x": 468.8, "y": 413.1, "size": 8, "max_width": 99,
    },
    "purchase_price_words": {
        "label": "Purchase price, in words (e.g. 'Six Hundred Fifty Thousand')",
        "page": 0, "x": 42.5, "y": 388.1, "size": 8, "max_width": 500,
    },

    # --- Deposit ---
    "deposit_method": {
        "label": "When the deposit is submitted (e.g. 'Herewith' or 'Upon Acceptance')",
        "page": 0, "x": 131.6, "y": 363.1, "size": 8, "max_width": 437,
    },
    "deposit_amount_words": {
        "label": "Deposit amount, in words",
        "page": 0, "x": 42.5, "y": 336.1, "size": 8, "max_width": 363,
    },
    "deposit_amount_numeral": {
        "label": "Deposit amount, numeral",
        "page": 0, "x": 468.4, "y": 336.1, "size": 8, "max_width": 99,
    },
    "deposit_holder": {
        "label": "Deposit holder — brokerage the deposit cheque is payable to",
        "page": 0, "x": 164.5, "y": 313.1, "size": 8, "max_width": 301,
    },

    # --- Schedules ---
    "additional_schedules": {
        "label": "Additional schedule letters beyond 'A' (e.g. 'B, C'), if any",
        "page": 0, "x": 101.4, "y": 221.3, "size": 8, "max_width": 305,
    },

    # --- Irrevocability ---
    "irrevocable_by": {
        "label": "Irrevocable by — 'Buyer' or 'Seller'",
        "page": 0, "x": 247.8, "y": 198.1, "size": 8, "max_width": 166,
    },
    "irrevocable_time": {
        "label": "Irrevocability deadline — time (e.g. '6:00 p.m.')",
        "page": 0, "x": 436.7, "y": 198.1, "size": 8, "max_width": 72,
    },
    "irrevocable_day": {
        "label": "Irrevocability deadline — day of month, numeral",
        "page": 0, "x": 539.0, "y": 198.1, "size": 8, "max_width": 30,
    },
    "irrevocable_month": {
        "label": "Irrevocability deadline — month name",
        "page": 0, "x": 85.3, "y": 171.1, "size": 8, "max_width": 161,
    },
    "irrevocable_year": {
        "label": "Irrevocability deadline — 2-digit year",
        "page": 0, "x": 261.7, "y": 171.1, "size": 8, "max_width": 24,
    },

    # --- Completion date ---
    "completion_day": {
        "label": "Completion (closing) date — day of month, numeral",
        "page": 0, "x": 386.1, "y": 134.1, "size": 8, "max_width": 30,
    },
    "completion_month": {
        "label": "Completion (closing) date — month name",
        "page": 0, "x": 447.8, "y": 134.1, "size": 8, "max_width": 121,
    },
    "completion_year": {
        "label": "Completion (closing) date — 2-digit year",
        "page": 0, "x": 70.4, "y": 111.1, "size": 8, "max_width": 35,
    },

    # --- Chattels / fixtures / rental items / HST (visual page 2) ---
    "chattels_included": {
        "label": "Chattels included in the sale (e.g. fridge, stove, washer, dryer, window coverings)",
        "page": 1, "size": 8, "max_width": 420,
        "lines": [(147.0, 551.3), (61.5, 528.1), (61.5, 505.1), (61.5, 482.1), (61.5, 459.1)],
    },
    "fixtures_excluded": {
        "label": "Fixtures excluded from the sale",
        "page": 1, "size": 8, "max_width": 420,
        "lines": [(147.0, 402.3), (60.5, 379.1), (60.5, 356.1), (60.5, 333.1), (60.5, 310.1)],
    },
    "rental_items": {
        "label": "Rented equipment the buyer agrees to assume (e.g. water heater rental)",
        "page": 1, "size": 8, "max_width": 500,
        "lines": [(60.5, 243.1), (60.5, 220.1), (60.5, 197.1)],
    },
    "hst_treatment": {
        "label": "HST treatment — 'included in' or 'in addition to' the purchase price",
        "page": 1, "x": 60.5, "y": 128.1, "size": 8, "max_width": 149,
    },
}

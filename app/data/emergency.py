"""
Emergency contact numbers displayed from Health menu → option 7.

Static data — no AI cost, no DB lookup.
Numbers shown here are sample defaults; replace them with the correct
emergency services for your deployment country.

The USSD shortcode is read from settings so it matches whatever shortcode
the operator has configured — no hardcoded values.
"""
from __future__ import annotations


def get_emergency_text(language: str = "en", shortcode: str = "*123#") -> str:
    """Return the formatted emergency numbers screen in the requested language."""
    if language == "rw":
        return (
            "END Inomero za Gihutisha\n\n"
            "Polisi:              +1-555-0100\n"
            "Ambulansi:           +1-555-0199\n"
            "Inkongi z'Umuriro:   +1-555-0133\n"
            "Indishutiro:         +1-555-0177\n\n"
            "Mu kaga: Vugisha +1-555-0100\n"
            f"Vugisha {shortcode} kubona inama."
        )
    return (
        "END Emergency Numbers\n\n"
        "Police:       +1-555-0100\n"
        "Ambulance:    +1-555-0199\n"
        "Fire Service: +1-555-0133\n"
        "Hospital ER:  +1-555-0177\n\n"
        "If in danger: Call +1-555-0100\n"
        f"Dial {shortcode} for health tips."
    )

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
            "Polisi:              112\n"
            "Ambulansi:           912\n"
            "Inkongi z'Umuriro:   110\n"
            "Indishutiro ya CHUK: +250788603600\n\n"
            "Mu kaga: Vugisha 112 (Polisi)\n"
            f"Vugisha {shortcode} kubona inama."
        )
    return (
        "END Emergency Numbers\n\n"
        "Police:       112\n"
        "Ambulance:    912\n"
        "Fire Service: 110\n"
        "Hospital ER:  +250788603600\n\n"
        "If in danger: Call 112\n"
        f"Dial {shortcode} for health tips."
    )

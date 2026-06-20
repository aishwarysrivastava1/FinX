# backend/services/symbol_resolver.py
"""
NSE symbol normalization.
Handles any user input: 'reliance', 'Reliance.NS', 'RELIANCE', ' TCS ' → 'TCS'
"""


def normalize_symbol(raw: str) -> str:
    """
    Normalize any user input to a clean NSE ticker (uppercase, no suffix, no spaces).
    Never raises. Returns '' for empty/invalid input.
    """
    if not raw:
        return ''
    cleaned = raw.strip().upper()
    for suffix in ('.NS', '.BO', '.NSE', '.BSE'):
        if cleaned.endswith(suffix):
            cleaned = cleaned[: -len(suffix)]
    return cleaned

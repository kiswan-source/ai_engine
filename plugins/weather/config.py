"""Config for the weather plugin. Open-Meteo is free and keyless, so Secrets
Management (Bab 58) doesn't apply here — nothing to keep out of source control.
"""

BASE_URL = "https://api.open-meteo.com/v1/forecast"
TIMEOUT_SECONDS = 10

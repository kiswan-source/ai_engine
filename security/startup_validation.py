"""Fail-closed production startup validation (Fase 0 / SEC-1, SEC-2).

DCF_SECURITY_AUDIT_2026-07-11.md temuan #1 and #2: this deployment's default
posture was "gagal membuka" (missing/blank credentials silently grant full
access or run with example values) rather than "gagal menutup" (refuse to
start). This module is the fail-closed gate: called once from
``api.main.lifespan`` before the app finishes starting. It is a no-op in
``development``/``test`` — existing local workflows are unaffected — and
only enforces when ``APP_ENV=production``.

Two layers per AI Engine v5 Architecture Blueprint §3.6/R2: a blocklist of
known-public example values (catches the exact aipassword/change-me values
this repo ships in .env.example) AND a minimum-length check (catches
weak-but-not-blocklisted values a blocklist alone would miss).
"""
from __future__ import annotations

_MIN_SECRET_LENGTH = 16

# Values that ship in this repo's .env.example / docker-compose.yml defaults,
# or other widely-known placeholders. Never acceptable in production — their
# presence means the operator has not replaced the shipped default.
_KNOWN_EXAMPLE_VALUES = {
    "aipassword",
    "change-me",
    "change-me-in-production-use-openssl-rand-hex-32",
    "postgres",
    "password",
    "admin",
    "admin123",
}


class ProductionConfigError(RuntimeError):
    """Raised when APP_ENV=production but required security config is missing
    or still holds an example/placeholder value. Startup must abort — this is
    the fail-closed behavior called for by SEC-1/SEC-2, replacing the previous
    fail-open default (empty API_KEYS => full admin access)."""


def _is_weak_or_example(value: str) -> str | None:
    """Return a human-readable reason if `value` is unacceptable, else None."""
    if not value:
        return "kosong"
    if value.strip().lower() in _KNOWN_EXAMPLE_VALUES:
        return "sama dengan nilai contoh publik yang dikenal"
    if len(value) < _MIN_SECRET_LENGTH:
        return f"kurang dari {_MIN_SECRET_LENGTH} karakter (kemungkinan lemah)"
    return None


def validate_production_config(settings) -> list[str]:
    """Return a list of problems for a production deployment. Empty = OK."""
    problems: list[str] = []

    if not settings.API_KEYS.strip():
        problems.append(
            "API_KEYS kosong — di production ini berarti SETIAP pemanggil endpoint "
            "yang dilindungi diperlakukan sebagai administrator penuh (SEC-1). "
            "Isi API_KEYS dengan minimal satu kunci acak yang kuat."
        )

    secret_key_problem = _is_weak_or_example(settings.SECRET_KEY)
    if secret_key_problem:
        problems.append(f"SECRET_KEY {secret_key_problem}.")

    # DATABASE_URL embeds the Postgres password; extract it defensively
    # without ever logging/printing the full connection string.
    db_url = settings.DATABASE_URL
    pg_password = None
    if "://" in db_url and "@" in db_url:
        creds = db_url.split("://", 1)[1].split("@", 1)[0]
        if ":" in creds:
            pg_password = creds.split(":", 1)[1]
    pg_problem = _is_weak_or_example(pg_password or "")
    if pg_problem:
        problems.append(f"Kredensial Postgres (DATABASE_URL) {pg_problem} (SEC-2).")

    redis_url = settings.REDIS_URL
    redis_password = None
    if "://" in redis_url and "@" in redis_url:
        creds = redis_url.split("://", 1)[1].split("@", 1)[0]
        if creds.startswith(":"):
            redis_password = creds[1:]
    redis_problem = _is_weak_or_example(redis_password or "")
    if redis_problem:
        problems.append(
            f"Kredensial Redis (REDIS_URL) {redis_problem} — Redis tanpa autentikasi "
            "yang layak berarti siapa pun yang menjangkau port tersebut dapat membaca/"
            "menulis/menghapus seluruh cache dan antrean pekerjaan tanpa syarat (SEC-2)."
        )

    return problems


def enforce_production_config(settings) -> None:
    """Call once at startup. Raises ProductionConfigError (aborts startup) if
    APP_ENV=production and any check in validate_production_config fails."""
    if settings.APP_ENV != "production":
        return
    problems = validate_production_config(settings)
    if problems:
        detail = "\n  - ".join(problems)
        raise ProductionConfigError(
            "Startup ditolak (APP_ENV=production, fail-closed per Fase 0 / SEC-1 & SEC-2):\n  - "
            + detail
        )

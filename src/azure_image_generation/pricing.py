from datetime import datetime, timezone
import hashlib
import json
import math
import re
from urllib.parse import urlsplit

from .config import IMAGE_QUALITY, IMAGE_SIZE, validate_endpoint


UNIT = "USD per million tokens; image USD per generated image"


class PriceVerificationError(ValueError):
    pass


class PriceVerifier:
    def __init__(self, settings, output_dir, *, now=None):
        self.settings = settings
        self.output_dir = output_dir
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.blocked = False
        self.recorded = False

    def verify(self):
        if self.blocked:
            raise PriceVerificationError("This run is blocked; review prices and start a new run")
        try:
            return self._verify()
        except (ValueError, TypeError, KeyError, OSError) as exc:
            self.blocked = True
            raise PriceVerificationError(str(exc)) from exc

    def _verify(self):
        settings = self.settings
        if hashlib.sha256(settings.path.read_bytes()).hexdigest() != settings.sha256:
            raise PriceVerificationError("Configuration changed during this run")
        sources, rows = settings.raw.get("pricing_sources"), settings.raw.get("pricing")
        if not isinstance(sources, dict) or not isinstance(rows, dict):
            raise PriceVerificationError("Reviewed image pricing and evidence are required")
        source, row = sources.get(settings.model), rows.get(settings.model)
        if not isinstance(source, dict) or not isinstance(row, dict):
            raise PriceVerificationError("Reviewed image pricing and evidence are required")
        if (source.get("verification") != "manual" or source.get("model") != settings.family
                or source.get("currency") != "USD" or source.get("unit") != UNIT
                or validate_endpoint(source.get("azure_endpoint")).lower() != settings.endpoint.lower()
                or source.get("image_size") != IMAGE_SIZE
                or source.get("image_quality") != IMAGE_QUALITY):
            raise PriceVerificationError("Evidence must match the model, resource, USD units, size and quality")
        region, mode = source.get("region"), source.get("deployment_type")
        if (not isinstance(region, str) or not re.fullmatch(r"[a-z][a-z0-9]{1,63}", region)
                or mode not in ("global-standard", "data-zone-standard")):
            raise PriceVerificationError("Declare the exact ARM region and supported billing mode")
        profile = settings.raw.get("pricing_lookup", {})
        if (not isinstance(profile, dict)
                or profile.get("region", region) != region
                or profile.get("deployment_type", mode) != mode):
            raise PriceVerificationError("Pricing profile differs from reviewed evidence")
        timestamp = source.get("verified_at")
        if not isinstance(timestamp, str):
            raise PriceVerificationError("Use a quoted timezone-bearing verification timestamp")
        verified = datetime.fromisoformat(timestamp)
        now = self.now().astimezone(timezone.utc)
        if (verified.tzinfo is None or verified.astimezone(timezone.utc).date() != now.date()
                or verified > now):
            raise PriceVerificationError("Prices must be manually reviewed today UTC, not in the future")
        reference = source.get("source")
        if not isinstance(reference, str):
            raise PriceVerificationError("An official Microsoft pricing reference is required")
        url = urlsplit(reference)
        if (url.scheme != "https" or url.hostname not in
                ("azure.microsoft.com", "learn.microsoft.com", "prices.azure.com")
                or url.port not in (None, 443) or url.username or url.password or url.query or url.fragment
                or not any(part in url.path for part in ("pricing", "/retail/prices"))):
            raise PriceVerificationError("Use an official Microsoft HTTPS pricing reference")
        rates = {}
        for key in ("input", "cached", "output", "image"):
            value = row.get(key)
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise PriceVerificationError("All four reviewed image rates must be finite and nonnegative")
            rates[key] = float(value)
        if not self.recorded:
            evidence = {"checked_at": now.isoformat(), "config_sha256": settings.sha256,
                        "deployment": settings.model, "kind": "image", "rates": rates, "source": source}
            with (self.output_dir / "azure_price_checks.jsonl").open("x", encoding="utf-8") as file:
                file.write(json.dumps(evidence) + "\n")
            self.recorded = True
        return rates

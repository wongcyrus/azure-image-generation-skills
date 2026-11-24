import base64
from datetime import datetime, timezone
from io import BytesIO
import json
import math
from pathlib import Path
import time

from PIL import Image

from .client import AzureImageClient
from .config import load_settings
from .inputs import load_input_images
from .pricing import PriceVerificationError, PriceVerifier


def usage_summary(usage, rates, *, operation="generate"):
    if usage is None:
        return {"input_tokens": None, "output_tokens": None, "cached_tokens": None,
                "total_cost_usd": None}
    inp = getattr(usage, "input_tokens", getattr(usage, "prompt_tokens", None))
    out = getattr(usage, "output_tokens", getattr(usage, "completion_tokens", None))
    details = getattr(usage, "input_tokens_details", None)
    if details is None:
        details = getattr(usage, "prompt_tokens_details", None)
    cached = getattr(details, "cached_tokens", 0) or 0
    if any(type(count) is not int or count < 0 for count in (inp, out, cached)) or cached > inp:
        return usage_summary(None, rates)
    if operation == "edit":
        output_details = getattr(usage, "output_tokens_details", None)
        parts = [getattr(details, name, None) for name in ("text_tokens", "image_tokens")]
        parts += [getattr(output_details, name, None) for name in ("text_tokens", "image_tokens")]
        if (cached or any(type(count) is not int or count < 0 for count in parts)
                or sum(parts[:2]) != inp or sum(parts[2:]) != out):
            return {"input_tokens": inp, "output_tokens": out, "cached_tokens": cached,
                    "total_cost_usd": None}
        cost = sum(count * rates[key] for count, key in zip(
            parts, ("input", "image_input", "output", "image_output"),
        )) / 1_000_000 + rates["image"]
    else:
        cost = ((inp - cached) * rates["input"] + cached * rates["cached"]
                + out * rates["output"]) / 1_000_000 + rates["image"]
    return {"input_tokens": inp, "output_tokens": out, "cached_tokens": cached,
            "total_cost_usd": round(cost, 6) if math.isfinite(cost) else None}


def write_audit(output_dir, settings, usage, rates, start, *, succeeded, operation="generate"):
    summary = usage_summary(usage, rates, operation=operation)
    trace = {"timestamp": datetime.now(timezone.utc).isoformat(), "model": settings.model,
             "phase": "image_generation", "duration_sec": round(time.perf_counter() - start, 3),
             "request_succeeded": succeeded, "operation": operation, **summary}
    with (output_dir / "azure_usage.jsonl").open("x", encoding="utf-8") as file:
        file.write(json.dumps(trace) + "\n")
    with (output_dir / "cost_summary.json").open("x", encoding="utf-8") as file:
        json.dump({"total_calls": 1, "total_images": int(succeeded), "operation": operation,
                   "unpriced_calls": int(summary["total_cost_usd"] is None), **summary}, file, indent=2)


def generate_image(model_config, prompt_file, output_dir, *, confirm_cost=False, input_images=()):
    settings = load_settings(model_config)
    prompt = Path(prompt_file).expanduser().read_text(encoding="utf-8").strip()
    if not prompt:
        raise ValueError("The image prompt must not be empty")
    output_dir = Path(output_dir).expanduser().absolute()
    if output_dir.exists() or output_dir.is_symlink():
        raise ValueError("Choose a new output directory; previous attempts are never overwritten")
    images = load_input_images(input_images)
    operation = "edit" if images else "generate"
    if not confirm_cost:
        return None
    output_dir.mkdir(parents=True, exist_ok=False)
    with (output_dir / "prompt.txt").open("x", encoding="utf-8") as file:
        file.write(prompt + "\n")
    if images:
        with (output_dir / "inputs.json").open("x", encoding="utf-8") as file:
            json.dump({"operation": operation, "images": [item.evidence() for item in images]}, file, indent=2)
    verifier = PriceVerifier(settings, output_dir, operation=operation)
    rates = verifier.verify()
    with AzureImageClient(settings, verifier) as client:
        start = time.perf_counter()
        try:
            response = client.edit(prompt, images) if images else client.generate(prompt)
        except PriceVerificationError:
            raise
        except Exception:
            write_audit(output_dir, settings, None, rates, start, succeeded=False, operation=operation)
            raise
        write_audit(output_dir, settings, getattr(response, "usage", None), rates, start,
                    succeeded=True, operation=operation)
        if not response.data or not response.data[0].b64_json:
            raise ValueError("Azure returned no inline image")
        data = base64.b64decode(response.data[0].b64_json, validate=True)
        with Image.open(BytesIO(data)) as image:
            if image.format != "PNG" or image.size != (1536, 1024):
                raise ValueError("Azure must return a 1536x1024 PNG")
            image.verify()
        target = output_dir / "image.png"
        with target.open("xb") as file:
            file.write(data)
        return target

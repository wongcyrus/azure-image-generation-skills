from dataclasses import dataclass
import hashlib
from pathlib import Path
from urllib.parse import urlsplit

import yaml


IMAGE_SIZE = "1536x1024"
IMAGE_QUALITY = "auto"


def validate_endpoint(endpoint):
    if not isinstance(endpoint, str):
        raise ValueError("An explicit Azure resource HTTPS endpoint is required")
    parsed = urlsplit(endpoint)
    suffixes = (".openai.azure.com", ".openai.azure.us", ".openai.azure.cn",
                ".services.ai.azure.com")
    if (parsed.scheme != "https" or not (parsed.hostname or "").lower().endswith(suffixes)
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.port not in (None, 443) or parsed.path not in ("", "/")):
        raise ValueError("Use an Azure resource endpoint without paths or credentials")
    return endpoint.rstrip("/")


@dataclass(frozen=True)
class Settings:
    path: Path
    sha256: str
    endpoint: str
    api_version: str
    model: str
    family: str
    raw: dict


def load_settings(path):
    path = Path(path).expanduser().resolve()
    content = path.read_bytes()
    try:
        config = yaml.safe_load(content)
    except yaml.YAMLError:
        raise ValueError("Invalid configuration YAML") from None
    if not isinstance(config, dict):
        raise ValueError("Configuration must be a mapping")
    azure, models = config.get("azure_openai"), config.get("models")
    if not isinstance(azure, dict) or not isinstance(models, dict):
        raise ValueError("Declare azure_openai and models mappings")
    model = models.get("image", models.get("analytics_image"))
    declarations = config.get("deployment_models", {})
    if not isinstance(model, str) or not model.strip() or not isinstance(declarations, dict):
        raise ValueError("Declare models.image and valid deployment_models")
    model = model.strip()
    family = declarations.get(model, model)
    if not isinstance(family, str) or not family.lower().startswith("gpt-image-"):
        raise ValueError("Declare the underlying gpt-image family for image deployment aliases")
    api_version = azure.get("api_version")
    if not isinstance(api_version, str) or not api_version.strip():
        raise ValueError("Declare azure_openai.api_version")
    return Settings(path, hashlib.sha256(content).hexdigest(),
                    validate_endpoint(azure.get("endpoint")), api_version, model,
                    family.lower(), config)

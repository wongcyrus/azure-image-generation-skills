import os
from urllib.parse import urlsplit

from .config import IMAGE_QUALITY, IMAGE_SIZE


class AzureImageClient:
    def __init__(self, settings, verifier):
        self.settings = settings
        self.verifier = verifier
        self.credential = None
        from openai import AzureOpenAI, OpenAI

        key = os.environ.get("AZURE_OPENAI_API_KEY")
        if not key:
            from azure.identity import (
                DefaultAzureCredential, ManagedIdentityCredential, get_bearer_token_provider,
            )
            auth = os.environ.get("AZURE_OPENAI_AUTH", "default")
            if auth not in ("default", "managed_identity"):
                raise ValueError("AZURE_OPENAI_AUTH must be default or managed_identity")
            self.credential = (ManagedIdentityCredential() if auth == "managed_identity"
                               else DefaultAzureCredential())
            scope = ("https://ai.azure.com/.default"
                     if urlsplit(settings.endpoint).hostname.endswith(".services.ai.azure.com")
                     else "https://cognitiveservices.azure.com/.default")
            key = get_bearer_token_provider(self.credential, scope)
        options = {"max_retries": 0, "timeout": 180}
        if settings.api_version == "v1":
            self.sdk = OpenAI(base_url=f"{settings.endpoint}/openai/v1/", api_key=key, **options)
        else:
            auth_options = {"azure_ad_token_provider": key} if callable(key) else {"api_key": key}
            self.sdk = AzureOpenAI(azure_endpoint=settings.endpoint, api_version=settings.api_version,
                                   **auth_options, **options)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        try:
            self.sdk.close()
        finally:
            if self.credential is not None:
                self.credential.close()

    def generate(self, prompt):
        self.verifier.verify()
        return self.sdk.with_options(max_retries=0).images.generate(
            model=self.settings.model, prompt=prompt, size=IMAGE_SIZE,
            quality=IMAGE_QUALITY, n=1,
        )

    def edit(self, prompt, images):
        if not images:
            raise ValueError("Image editing requires at least one validated input image")
        if self.verifier.operation != "edit":
            raise ValueError("Image editing requires an edit-specific price verifier")
        self.verifier.verify()
        return self.sdk.with_options(max_retries=0).images.edit(
            model=self.settings.model, prompt=prompt, size=IMAGE_SIZE,
            quality=IMAGE_QUALITY, output_format="png", n=1,
            image=[(item.upload_name, item.data, item.mime_type) for item in images],
        )

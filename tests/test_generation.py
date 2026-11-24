import base64
import copy
from datetime import datetime, timedelta, timezone
from io import BytesIO
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from PIL import Image
import yaml

from azure_image_generation.client import AzureImageClient
from azure_image_generation.config import load_settings
from azure_image_generation.generation import generate_image, usage_summary
from azure_image_generation.inputs import load_input_images
from azure_image_generation.pricing import PriceVerificationError, PriceVerifier, UNIT


NOW = datetime(2026, 11, 24, 2, tzinfo=timezone.utc)
ENDPOINT = "https://synthetic.openai.azure.com"


class TestImageGeneration(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.path = self.root / "config.yaml"
        self.prompt = self.root / "prompt.txt"
        self.prompt.write_text("Public synthetic infographic.", encoding="utf-8")
        self.output = self.root / "attempt"
        self.config = {
            "azure_openai": {"endpoint": ENDPOINT, "api_version": "v1"},
            "models": {"image": "image-alias"},
            "deployment_models": {"image-alias": "gpt-image-1"},
            "pricing_lookup": {"region": "eastus", "deployment_type": "global-standard"},
            "pricing": {"image-alias": {"input": 2, "cached": 0.5, "output": 8, "image": 0}},
            "pricing_sources": {"image-alias": {
                "verification": "manual", "verified_at": NOW.isoformat(), "model": "gpt-image-1",
                "azure_endpoint": ENDPOINT, "region": "eastus", "deployment_type": "global-standard",
                "currency": "USD", "unit": UNIT, "image_size": "1536x1024", "image_quality": "auto",
                "source": "https://azure.microsoft.com/en-us/pricing/details/azure-openai/",
            }},
        }
        self.save()
        self.time_patch = patch("azure_image_generation.pricing.datetime")
        clock = self.time_patch.start()
        clock.now.return_value = NOW
        clock.fromisoformat.side_effect = datetime.fromisoformat
        self.addCleanup(self.time_patch.stop)
        self.client_patch = patch("azure_image_generation.generation.AzureImageClient")
        self.client_class = self.client_patch.start()
        self.addCleanup(self.client_patch.stop)
        self.client = self.client_class.return_value.__enter__.return_value
        data = BytesIO()
        Image.new("RGB", (1536, 1024), "white").save(data, format="PNG")
        self.response = SimpleNamespace(
            data=[SimpleNamespace(b64_json=base64.b64encode(data.getvalue()).decode())],
            usage=SimpleNamespace(input_tokens=100, output_tokens=200,
                                  input_tokens_details=SimpleNamespace(cached_tokens=20)),
        )
        self.client.generate.return_value = self.response

    def save(self, config=None):
        self.path.write_text(yaml.safe_dump(config or self.config), encoding="utf-8")

    def test_preview_is_offline_and_writes_nothing(self):
        with patch("azure_image_generation.generation.PriceVerifier") as verifier:
            self.assertIsNone(generate_image(self.path, self.prompt, self.output))
        verifier.assert_not_called()
        self.client_class.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_one_call_retains_price_prompt_usage_and_valid_png(self):
        target = generate_image(self.path, self.prompt, self.output, confirm_cost=True)
        self.client.generate.assert_called_once_with("Public synthetic infographic.")
        with Image.open(target) as image:
            self.assertEqual(image.size, (1536, 1024))
        self.assertEqual((self.output / "prompt.txt").read_text(), self.prompt.read_text() + "\n")
        summary = json.loads((self.output / "cost_summary.json").read_text())
        self.assertEqual(summary["total_calls"], 1)
        self.assertEqual(summary["total_images"], 1)
        self.assertAlmostEqual(summary["total_cost_usd"], 0.00177)
        self.assertTrue((self.output / "azure_price_checks.jsonl").is_file())

    def test_invalid_evidence_blocks_before_client_construction(self):
        mutations = [
            ("verified_at", (NOW - timedelta(days=1)).isoformat()),
            ("verified_at", (NOW + timedelta(minutes=1)).isoformat()),
            ("verified_at", "2026-11-24T02:00:00"),
            ("model", "gpt-image-other"),
            ("azure_endpoint", "https://other.openai.azure.com"),
            ("currency", "EUR"), ("unit", "wrong"),
            ("image_size", "1024x1024"), ("image_quality", "high"),
            ("region", "East US"), ("deployment_type", "unknown"),
            ("source", "https://untrusted.example/pricing"),
            ("source", "https://learn.microsoft.com/pricing?token=not-secret"),
        ]
        for index, (key, value) in enumerate(mutations):
            config = copy.deepcopy(self.config)
            config["pricing_sources"]["image-alias"][key] = value
            self.save(config)
            with self.subTest(key=key, value=value), self.assertRaises(PriceVerificationError):
                generate_image(self.path, self.prompt, self.root / f"invalid-{index}", confirm_cost=True)
        self.client_class.assert_not_called()

    def test_missing_or_invalid_prices_block_and_failed_verifier_latches(self):
        for index, value in enumerate((None, -1, True, float("nan"), float("inf"))):
            config = copy.deepcopy(self.config)
            config["pricing"]["image-alias"]["output"] = value
            self.save(config)
            output = self.root / str(index)
            output.mkdir()
            verifier = PriceVerifier(load_settings(self.path), output, now=lambda: NOW)
            with self.subTest(value=value), self.assertRaises(PriceVerificationError):
                verifier.verify()
            self.save()
            with self.assertRaises(PriceVerificationError):
                verifier.verify()

    def test_existing_attempt_or_dangling_symlink_is_never_overwritten(self):
        self.output.mkdir()
        sentinel = self.output / "image.png"
        sentinel.write_bytes(b"keep")
        dangling = self.root / "dangling"
        dangling.symlink_to(self.root / "missing")
        for target in (self.output, dangling):
            with self.subTest(target=target), self.assertRaises(ValueError):
                generate_image(self.path, self.prompt, target, confirm_cost=True)
        self.client_class.assert_not_called()
        self.assertEqual(sentinel.read_bytes(), b"keep")

    def test_config_change_between_price_check_and_transport_blocks(self):
        settings = load_settings(self.path)
        self.output.mkdir()
        verifier = PriceVerifier(settings, self.output, now=lambda: NOW)
        verifier.verify()
        self.path.write_text(self.path.read_text() + "\n")
        with self.assertRaises(PriceVerificationError):
            verifier.verify()

    def test_failed_request_is_not_retried_and_reports_unknown_cost(self):
        self.client.generate.side_effect = TimeoutError("No details")
        with self.assertRaises(TimeoutError):
            generate_image(self.path, self.prompt, self.output, confirm_cost=True)
        self.client.generate.assert_called_once()
        summary = json.loads((self.output / "cost_summary.json").read_text())
        self.assertIsNone(summary["total_cost_usd"])
        self.assertEqual(summary["unpriced_calls"], 1)
        self.assertFalse((self.output / "image.png").exists())

    def test_invalid_png_retains_paid_usage_but_saves_no_image(self):
        self.response.data[0].b64_json = base64.b64encode(b"bad image").decode()
        with self.assertRaises(Exception):
            generate_image(self.path, self.prompt, self.output, confirm_cost=True)
        self.client.generate.assert_called_once()
        self.assertTrue((self.output / "cost_summary.json").exists())
        self.assertFalse((self.output / "image.png").exists())

    def test_missing_or_invalid_usage_is_unknown_not_free(self):
        rates = {"input": 2, "cached": 0.5, "output": 8, "image": 0}
        for usage in (None, SimpleNamespace(input_tokens=-1, output_tokens=2),
                      SimpleNamespace(input_tokens=1, output_tokens=None),
                      SimpleNamespace(input_tokens=1, output_tokens=2,
                                      input_tokens_details=SimpleNamespace(cached_tokens=3))):
            self.assertIsNone(usage_summary(usage, rates)["total_cost_usd"])

    def test_legacy_config_key_works_without_any_application_dependency(self):
        self.config["models"] = {"analytics_image": "image-alias"}
        self.save()
        self.assertIsNone(generate_image(self.path, self.prompt, self.output))

    def test_transport_verifies_before_single_sdk_request_with_retries_disabled(self):
        settings = load_settings(self.path)
        sdk = Mock()
        sdk.with_options.return_value = sdk
        events = []
        verifier = Mock()
        verifier.verify.side_effect = lambda: events.append("prices")
        sdk.images.generate.side_effect = lambda **kwargs: events.append("image") or self.response
        with patch.dict("os.environ", {"AZURE_OPENAI_API_KEY": "synthetic-test-key"}):
            with patch("openai.OpenAI", return_value=sdk) as constructor:
                with AzureImageClient(settings, verifier) as client:
                    client.generate("Public synthetic infographic.")
        self.assertEqual(constructor.call_args.kwargs["max_retries"], 0)
        sdk.with_options.assert_called_once_with(max_retries=0)
        sdk.images.generate.assert_called_once_with(
            model="image-alias", prompt="Public synthetic infographic.",
            size="1536x1024", quality="auto", n=1,
        )
        self.assertEqual(events, ["prices", "image"])
        sdk.close.assert_called_once()

    def input_image(self, name="reference.png", image_format="PNG"):
        path = self.root / name
        Image.new("RGB", (64, 48), "blue").save(path, format=image_format)
        return path

    def enable_edit(self):
        source = self.config["pricing_sources"]["image-alias"]
        source["image_operations"] = ["generate", "edit"]
        source["image_token_unit"] = "USD per million image tokens"
        self.config["pricing"]["image-alias"].update(image_input=4, image_output=12)
        self.save()
        self.response.usage = SimpleNamespace(
            input_tokens=100, output_tokens=200,
            input_tokens_details=SimpleNamespace(text_tokens=30, image_tokens=70, cached_tokens=0),
            output_tokens_details=SimpleNamespace(text_tokens=0, image_tokens=200),
        )
        self.client.edit.return_value = self.response

    def test_reference_preview_validates_files_without_network_or_writes(self):
        reference = self.input_image()
        with patch("azure_image_generation.generation.PriceVerifier") as verifier:
            self.assertIsNone(generate_image(self.path, self.prompt, self.output,
                                            input_images=[reference]))
        verifier.assert_not_called()
        self.client_class.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_bad_unsupported_or_excess_inputs_block_before_client_or_output(self):
        invalid = self.root / "bad.png"
        invalid.write_bytes(b"not an image")
        unsupported = self.input_image("reference.gif", "GIF")
        for inputs in ([invalid], [unsupported], [invalid] * 17):
            with self.subTest(inputs=len(inputs)), self.assertRaises((ValueError, OSError)):
                generate_image(self.path, self.prompt, self.output, confirm_cost=True,
                               input_images=inputs)
        self.client_class.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_edit_requires_explicit_reviewed_operation_and_image_rates(self):
        reference = self.input_image()
        with self.assertRaises(PriceVerificationError):
            generate_image(self.path, self.prompt, self.output, confirm_cost=True,
                           input_images=[reference])
        self.enable_edit()
        del self.config["pricing"]["image-alias"]["image_input"]
        self.save()
        with self.assertRaises(PriceVerificationError):
            generate_image(self.path, self.prompt, self.root / "missing-rate", confirm_cost=True,
                           input_images=[reference])
        self.client_class.assert_not_called()

    def test_edit_sends_ordered_validated_snapshots_and_retains_private_input_evidence(self):
        self.enable_edit()
        first = self.input_image()
        second = self.input_image("second.jpg", "JPEG")
        first_bytes = first.read_bytes()
        self.client_class.return_value.__enter__.side_effect = (
            lambda: (first.write_bytes(b"changed after validation"), self.client)[1]
        )
        target = generate_image(self.path, self.prompt, self.output, confirm_cost=True,
                                input_images=[first, second])
        self.assertTrue(target.is_file())
        self.client.generate.assert_not_called()
        self.client.edit.assert_called_once()
        images = self.client.edit.call_args.args[1]
        self.assertEqual(images[0].data, first_bytes)
        self.assertEqual([item.mime_type for item in images], ["image/png", "image/jpeg"])
        self.assertEqual([item.upload_name for item in images], ["reference-01.png", "reference-02.jpg"])
        evidence = json.loads((self.output / "inputs.json").read_text())
        self.assertEqual(len(evidence["images"]), 2)
        self.assertNotIn(str(self.root), (self.output / "inputs.json").read_text())
        summary = json.loads((self.output / "cost_summary.json").read_text())
        self.assertEqual(summary["operation"], "edit")
        self.assertAlmostEqual(summary["total_cost_usd"], 0.00274)
        prices = json.loads((self.output / "azure_price_checks.jsonl").read_text())
        self.assertEqual(prices["operation"], "edit")

    def test_edit_transport_verifies_then_calls_edits_once_without_generation_fallback(self):
        images = load_input_images([self.input_image()])
        sdk = Mock()
        sdk.with_options.return_value = sdk
        sdk.images.edit.side_effect = TimeoutError("No details")
        verifier = Mock(operation="edit")
        client = AzureImageClient.__new__(AzureImageClient)
        client.settings = load_settings(self.path)
        client.verifier = verifier
        client.sdk = sdk
        with self.assertRaises(TimeoutError):
            client.edit("Use the reference.", images)
        verifier.verify.assert_called_once()
        sdk.with_options.assert_called_once_with(max_retries=0)
        sdk.images.edit.assert_called_once_with(
            model="image-alias", prompt="Use the reference.", size="1536x1024", quality="auto",
            output_format="png", n=1, image=[("reference-01.png", images[0].data, "image/png")],
        )
        sdk.images.generate.assert_not_called()
        verifier.verify.side_effect = PriceVerificationError("blocked")
        sdk.reset_mock()
        with self.assertRaises(PriceVerificationError):
            client.edit("Use the reference.", images)
        sdk.images.edit.assert_not_called()

    def test_edit_failure_is_unpriced_with_no_retry_or_generation_fallback(self):
        self.enable_edit()
        self.client.edit.side_effect = TimeoutError("No details")
        with self.assertRaises(TimeoutError):
            generate_image(self.path, self.prompt, self.output, confirm_cost=True,
                           input_images=[self.input_image()])
        self.client.edit.assert_called_once()
        self.client.generate.assert_not_called()
        summary = json.loads((self.output / "cost_summary.json").read_text())
        self.assertEqual(summary["operation"], "edit")
        self.assertIsNone(summary["total_cost_usd"])

    def test_edit_cost_needs_complete_uncached_category_counts(self):
        self.enable_edit()
        rates = self.config["pricing"]["image-alias"]
        self.assertAlmostEqual(usage_summary(self.response.usage, rates, operation="edit")["total_cost_usd"],
                               0.00274)
        for details in (None, SimpleNamespace(text_tokens=0, image_tokens=199)):
            self.response.usage.output_tokens_details = details
            self.assertIsNone(usage_summary(self.response.usage, rates, operation="edit")["total_cost_usd"])
        self.response.usage.output_tokens_details = SimpleNamespace(text_tokens=0, image_tokens=200)
        self.response.usage.input_tokens_details.cached_tokens = 10
        self.assertIsNone(usage_summary(self.response.usage, rates, operation="edit")["total_cost_usd"])

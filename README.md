# Azure image-generation skills

Independent Azure OpenAI text-to-image tooling and a reusable Copilot skill.
No handwriting-grader, Gemini, Microsoft Agent Framework or notebook dependencies.

## Install and register

Python 3.11+:

```bash
uv sync --frozen
copilot skill add ./skills/azure-image-generation
```

Use `/skills reload` in an existing Copilot session after registration.
For execution from another project, use this checkout's `.venv/bin/azure-image`
(Windows: `.venv\Scripts\azure-image.exe`) or install the package into that
project's Python environment.

## Configure and preview

Copy `examples/config.example.yaml` to a private, ignored configuration.
Declare your actual deployment/family/resource and manually review current
Microsoft image prices. Replace every placeholder and null; quote the
timezone-bearing `verified_at` timestamp. Do not simply update its date.
Keep keys in `AZURE_OPENAI_API_KEY`, not YAML or shell command history.
Alternatively use Azure Identity credentials, including `az login`.

```bash
uv run azure-image \
  --model-config /private/image.config.yaml \
  --prompt-file skills/azure-image-generation/prompts/teacher-workflow.txt \
  --output-dir output/first-image
```

Without `--confirm-cost`, preview makes no network calls or output writes.
Add it only after explicit consent for **one paid Azure request**.

## Boundaries

The tool requests one `1536x1024` PNG at `auto` quality, with SDK retries disabled.
Image editing and input images are not implemented. Existing attempt directories,
including failed attempts, are rejected. Review every generated label before use;
retain original artwork when correcting labels locally.

Pricing is checked before SDK construction and again immediately before the paid
request. Evidence must match the model, endpoint, ARM region, billing mode, USD
units, size and quality, and have been reviewed today UTC. Changes during a run
block the request. Currently only manually reviewed image pricing is supported:
there is **no live image-price lookup**. The program validates the attestation;
it cannot independently establish that supplied rates are correct.

Input/cached/output rates use USD per million tokens; `image` is USD per generated
image. Set `image: 0` only if verified token rates already cover the entire image
charge. Incomplete/category-dependent pricing must remain unpriced and blocked.

Successful attempts retain `image.png`, the exact submitted `prompt.txt`,
`azure_price_checks.jsonl`, `azure_usage.jsonl` and `cost_summary.json`.
Missing/invalid usage is **unknown**, not zero. Failed submitted requests may
still be billed. Estimates are not invoices. Publish reviewed artwork, not the
entire private audit folder.

Legacy configurations with `models.analytics_image` also work; no application
code or approval manifests are required.

## Validate without inference

```bash
uv run python -m unittest discover -s tests -v
```

# Azure image-generation skills

Independent Azure OpenAI text-to-image and reference-image/editing tooling with
a reusable Copilot skill. Text-only generation remains the default.
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
Optional input images select the Images Edits API. Existing attempt directories,
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

## Optional reference images and editing

```bash
uv run azure-image \
  --model-config /private/edit.config.yaml \
  --prompt-file /private/edit-prompt.txt \
  --input-image /private/source.png \
  --input-image /private/reference.jpg \
  --output-dir output/first-edit
```

`--reference-image` is an alias for `--input-image`. Without either option, the
existing text-to-image path is unchanged. Preview validates local image bytes
without network calls or writes. Add `--confirm-cost` only after consenting to
one paid edit request **and transmission of the prompt and all selected images,
including embedded metadata**. The first image is the principal image to edit;
the prompt describes how the other images should be used.

Up to 16 local single-frame PNG, JPEG or WebP inputs are accepted, each smaller
than 50 MB. Files are validated and snapshotted before authentication or calls;
only those bytes are sent even if a source changes later. Input files are never
modified. Private `inputs.json` records ordered upload names, dimensions, hashes
and byte counts, not source paths or copies of the input files.

Use `examples/edit.config.example.yaml` and actually review the edit prices.
In addition to existing evidence, editing requires `image_operations` including
`edit`, `image_token_unit: "USD per million image tokens"` and explicit
`image_input`/`image_output` rates. For edit accounting, `input`/`output` cover
text tokens and the new rates cover image tokens. The `image` fee remains
USD per generated image; all token rates are per million. Do not copy
generation-only evidence or change its timestamp to authorize edits.

An edit estimate needs matching text/image input and output token breakdowns.
Missing breakdowns or cached tokens without reliable modality-specific
allocation remain **unknown**, never billed as zero or guessed from text rates.
An edit API error is not retried and never falls back to paid generation.
Actual editing capability must be verified for the Azure deployment.

Masks, URLs, image search and inpainting controls are not implemented.
Reference images guide the model; exact logos, text, identity and layout are not
guaranteed to survive an edit. Composite authorized logos locally instead of
asking AI to recreate them.

See Microsoft's [image-edit API reference](https://learn.microsoft.com/en-us/azure/foundry/reference/rest/images-create-image-edit-multipart-images-create-image-edit-json).

## Validate without inference

```bash
uv run python -m unittest discover -s tests -v
```

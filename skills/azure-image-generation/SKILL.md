---
name: azure-image-generation
description: >-
  Creates illustrations and infographics through the user's Azure OpenAI image
  deployment using an independent image-generation package. Requires explicit
  cost consent and current reviewed pricing. Supports optional local reference
  images/editing; defaults to text-only. Never substitutes another provider.
version: 2
---

# Azure image generation

## Independent tooling

Use the `azure-image-generation-skills` repository and its own Python environment.
There are no handwriting-grader, Gemini, Agent Framework or notebook dependencies.
Run `azure-image` or `python -m azure_image_generation`. From another project,
use the image repository's executable by absolute path, or its installed package.
If missing, locate that repository and follow its README dependency setup.
Do not search for or install a grader to generate images.

## Configuration and consent

Use a private YAML declaring `azure_openai.endpoint`, `azure_openai.api_version`,
`models.image`, and the underlying family in `deployment_models` for aliases.
Legacy `models.analytics_image` is accepted for configuration compatibility only.
Authentication uses `AZURE_OPENAI_API_KEY` or Azure Identity, including Azure CLI.
Never request secrets in chat, echo private YAML or embed keys in shell commands.

Manually reviewed `pricing` and `pricing_sources` are required before generation:
today's timezone-bearing UTC evidence; matching image family/resource/ARM region/
billing mode; USD input/cached/output and per-image rates; exact units, `1536x1024`
size and `auto` quality; official Microsoft pricing reference.
Manual evidence is a local attestation, not a live price lookup or provider invoice.
Never guess rates or refresh an attestation timestamp without reviewing prices.

## Workflow

1. Agree the provider, private configuration, image brief and a new attempt folder.
   Use public/synthetic content only; exclude private data and access-token URLs.
2. Write the agreed UTF-8 prompt. Preview offline:

   ```bash
   "/path/to/azure-image-generation-skills/.venv/bin/azure-image" \
     --model-config "/private/image.config.yaml" \
     --prompt-file "/path/to/prompt.txt" \
     --output-dir "/path/to/new-image-attempt"
   ```

   Preview makes no network calls or writes. It does not certify prices or access.
3. Obtain explicit approval for one paid request, then add `--confirm-cost`.
   Do not bypass pricing failures, retry automatically or substitute providers.
   If input images are selected, consent must cover transmitting all their bytes
   and embedded metadata. Never infer that consent from a file being present.
4. Inspect the PNG's labels, arrows, readability and factual claims. Local label
   corrections do not need provider calls; retain the original. Verify technical
   labels against the relevant application source, not a guessed format.
5. Share reviewed artwork and an approved prompt only. Keep usage/price audits
   private. Unknown usage is unpriced, not free; estimates are not invoices.

Exactly one image is requested, with SDK retries disabled. Existing attempt
directories are rejected, including failed attempts. Timeouts can still be billed.
Text-to-image is the default at fixed `1536x1024`. Optional repeated
`--input-image "/private/reference.png"` (alias `--reference-image`) selects
the Images Edits API instead. Up to 16 local single-frame PNG/JPEG/WebP files
are accepted, each smaller than 50 MB. Preview validates them offline. The
principal image comes first; describe the role of other images in the prompt.
Files are snapshotted before calls and never modified. The private attempt
records input hashes and generic upload names, not original file paths.

Editing needs separately reviewed evidence: `image_operations` must include
`edit`; `image_token_unit` must be `USD per million image tokens`; pricing must
include `image_input` and `image_output`, alongside the existing rates. For
edits, `input`/`output` price text tokens and the new fields price image tokens.
Do not silently reuse generation-only pricing or update dates without review.
Missing category usage or unallocatable cached usage stays unpriced.
Use `examples/edit.config.example.yaml` in the independent repository.

Do not fall back from a failed edit to another paid call. Reference input does
not guarantee exact logo, text or identity preservation. For branding, use
authorized original assets and deterministic local compositing instead of
asking AI to redraw logos. Masks, URL inputs and inpainting controls are not
implemented. Deployment editing capability still needs verification.

Prefer editable Mermaid/SVG for precise technical diagrams, generated artwork
for explanatory illustrations, and real synthetic-demo captures for screenshots.
Never fabricate app interfaces, observed model results, approvals or official logos.
An optional teacher-workflow example is in `prompts/teacher-workflow.txt`; it is
illustrative, not a required workflow or a dependency on an education application.

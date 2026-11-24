import argparse
from pathlib import Path

from .generation import generate_image


def main(argv=None):
    parser = argparse.ArgumentParser(description="Generate one consented, price-checked Azure image")
    parser.add_argument("--model-config", required=True, type=Path)
    parser.add_argument("--prompt-file", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path,
                        help="New attempt directory; existing directories are rejected")
    parser.add_argument("--input-image", "--reference-image", action="append", default=[], type=Path,
                        help="Optional local PNG/JPEG/WebP; repeat for up to 16 inputs; selects image editing")
    parser.add_argument("--confirm-cost", action="store_true",
                        help="Authorize one paid request and transfer of prompt/input images; otherwise offline preview")
    args = parser.parse_args(argv)
    try:
        target = generate_image(args.model_config, args.prompt_file, args.output_dir,
                                confirm_cost=args.confirm_cost, input_images=args.input_image)
    except Exception as exc:
        print(f"Image generation stopped ({type(exc).__name__}). "
              "Review inputs, pricing and Azure authentication locally. "
              "Do not retry automatically; a submitted request may be billed.")
        return 1
    operation = f"image edit with {len(args.input_image)} local input(s)" if args.input_image else "text-to-image"
    print(f"Saved PNG: {target}" if target else
          f"Preview only ({operation}): no network calls or output writes. "
          "Add --confirm-cost to authorize one request.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

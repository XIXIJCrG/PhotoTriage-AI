# Privacy

PhotoTriage AI is designed as a local-first photo review tool with explicit opt-in cloud support.

## Local Mode

In local mode, photos are resized on your computer and sent only to your local OpenAI-compatible endpoint, such as `llama.cpp` server. Image data does not leave your machine unless your endpoint is hosted elsewhere.

## Cloud Mode

Cloud provider support is explicit and opt-in. When enabled, resized image data is sent to the configured OpenAI-compatible API provider for visual analysis. Cloud mode requires a Base URL, model name, and API key in Settings.

Before the first cloud run, the app shows a privacy warning so users know images will leave the local machine.

## Metadata

The app can write XMP metadata. The safer mode is sidecar-only, which writes `.xmp` files next to photos instead of modifying JPG/PNG files directly.

## Files Not Intended for Sharing

Do not publish:

- original photos,
- generated `triage_*.csv` files,
- `.xmp` sidecars from private shoots,
- API keys,
- local model paths,
- local app settings,
- thumbnail caches.

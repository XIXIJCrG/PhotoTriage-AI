# Privacy

PhotoTriage AI is designed as a local-first photo review tool.

## Local Mode

In local mode, photos are resized on your computer and sent only to your local OpenAI-compatible endpoint, such as `llama.cpp` server. Image data does not leave your machine unless your endpoint is hosted elsewhere.

In cloud mode, resized image data is sent to the configured OpenAI-compatible API provider. Cloud mode is opt-in and requires a Base URL, model name, and API key in Settings.

## Cloud Mode

Cloud provider support is planned as an opt-in feature. When enabled, resized image data will be sent to the selected provider for visual analysis. The app should always make this clear before analysis starts.

## Metadata

The app can write XMP metadata. The safer mode is sidecar-only, which writes `.xmp` files next to photos instead of modifying JPG/PNG files directly.

## Files Not Intended for Sharing

Do not publish:

- original photos,
- generated `triage_*.csv` files,
- `.xmp` sidecars from private shoots,
- API keys,
- local model paths,
- API keys,
- local app settings,
- thumbnail caches.

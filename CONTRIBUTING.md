# Contributing

Thanks for your interest in improving PhotoTriage AI.

## Development Setup

```bash
python -m pip install -r requirements.txt
python app.py
```

Run tests before opening a pull request:

```bash
python -m unittest discover -s tests -v
```

## Guidelines

- Keep the app local-first. Cloud providers are welcome, but they must be opt-in.
- Do not commit real photos, generated CSV files, API keys, local configs, model weights, or cache folders.
- Prefer small, focused changes with tests when behavior changes.
- Keep GUI text behind the i18n layer for new user-facing strings.
- Metadata-writing features should be conservative and should not overwrite user files silently.

## Privacy-Sensitive Changes

If a change sends image data to any remote service, document:

- what data is sent,
- which provider receives it,
- how users can disable it,
- whether API keys are stored locally.

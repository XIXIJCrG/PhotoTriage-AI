# PhotoTriage AI

Local-first AI photo triage for JPG+RAW shoots.

PhotoTriage AI uses a vision-language model to review, score, annotate, and export photo shoots. It is designed for photographers who want fast first-pass culling while keeping Lightroom/Capture One compatible metadata through CSV and XMP workflows.

> Status: early desktop prototype. The current version is tested on Windows with local and cloud OpenAI-compatible vision endpoints.

## Highlights

- Folder picker with thumbnail preview before analysis
- Thumbnail grid for both analysed and unanalysed folders
- Vision-model scoring for technical quality, aesthetics, subject clarity, story, and portrait-specific factors
- CSV export with structured fields
- XMP metadata writing, including safer sidecar-only mode
- JPG/PNG + RAW pairing
- Lightroom/Capture One friendly workflow
- Prompt profiles for different judging styles
- Local-first design, with optional cloud provider support
- Simplified Chinese and English UI infrastructure in progress

## Why This Exists

Photo culling is repetitive. Lightroom can rate photos, but it does not understand them. This tool lets a local multimodal model act as a first-pass reviewer: it reads the image, gives structured scores, writes comments, and helps you quickly filter keepers from a large shoot.

It is not meant to replace final human selection. It is meant to remove friction from the first pass.

## Privacy

The default goal is local processing:

- In local mode, resized images are sent only to your configured local endpoint.
- XMP sidecar mode can avoid modifying original JPG/PNG files.
- Generated CSV/XMP files may contain private shoot information and are ignored by default.

Cloud API support is explicit and opt-in. See [docs/privacy.md](docs/privacy.md).

## Quick Start

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

Start the GUI:

```bash
python app.py
```

For local analysis, run an OpenAI-compatible vision endpoint such as `llama.cpp` server, then configure the Base URL and model in the app settings.

If you want the GUI to start a local `llama.cpp` server for you, copy `start-triage-server.example.bat` to `start-triage-server.bat`, edit the paths, and select it in Settings. The real `start-triage-server.bat` is ignored so personal model paths are not committed.

For cloud analysis, open Settings -> Server and choose "OpenAI Compatible API". Enter:

- Base URL, for example `https://api.openai.com/v1`
- Model name, for example a vision-capable chat model offered by your provider
- API Key

Photos are resized before upload, but cloud mode still sends image data to the configured provider. Use local mode for private shoots.

## Model Providers

The analysis core talks to an OpenAI-compatible chat completions endpoint:

```text
/v1/chat/completions
```

Local `llama.cpp` and cloud OpenAI-compatible providers share the same request format. The provider settings are stored locally through the desktop app settings.

## Project Structure

```text
app.py                         GUI entry point
triage.py                      Core folder scan, model call, CSV/XMP workflow
gui/                           PySide6 desktop UI
  main_window.py               Main frame and menus
  task_panel.py                Folder/run controls
  folder_picker_dialog.py      Folder picker with thumbnail preview
  results_view.py              Thumbnail grid, filtering, batch actions
  thumbnail_gen.py             Background thumbnail cache
  settings_dialog.py           Settings UI
tests/                         Unit tests
docs/                          Open-source docs
i18n/                          Translation dictionaries
core/                          Shared non-GUI helpers
```

## Development

Run tests:

```bash
python -m unittest discover -s tests -v
```

See [CHANGELOG.md](CHANGELOG.md) for notable changes and [SECURITY.md](SECURITY.md) for privacy/security reporting guidance.

Run a lightweight GUI smoke test:

```powershell
$env:QT_QPA_PLATFORM='offscreen'
python - <<'PY'
from PySide6.QtWidgets import QApplication
from gui.main_window import MainWindow
app = QApplication([])
win = MainWindow()
print(win.windowTitle())
PY
```

## Roadmap

See [docs/open_source_roadmap.md](docs/open_source_roadmap.md).

Near-term priorities:

- Finish English/Simplified Chinese UI switch
- Add provider abstraction
- Support local and cloud OpenAI-compatible APIs cleanly
- Add first-run setup wizard
- Package Windows portable builds

## License

MIT. See [LICENSE](LICENSE).

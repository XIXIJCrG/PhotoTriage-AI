# Architecture

PhotoTriage AI has three main layers.

## Core Analysis

`triage.py` scans a folder, pairs JPG/PNG files with RAW files, sends resized images to a vision model endpoint, parses structured JSON, writes CSV output, and optionally writes XMP metadata.

## GUI

The `gui/` package is a PySide6 desktop app:

- `main_window.py`: main application frame
- `task_panel.py`: folder/model/run controls
- `folder_picker_dialog.py`: folder picker with thumbnail preview
- `results_view.py`: thumbnail grid, filtering, sorting, batch actions
- `thumbnail_gen.py`: background thumbnail cache generation
- `settings_dialog.py`: user settings

## Provider Layer

Model calls are routed through a small OpenAI-compatible provider layer:

```python
class VisionProvider:
    def check_connection(self) -> tuple[bool, str]:
        ...

    def analyze_image(self, image_path, prompt: str) -> dict:
        ...
```

Initial providers include:

- local `llama.cpp` / OpenAI-compatible endpoint
- custom OpenAI-compatible API

Later providers can include dedicated adapters for OpenAI, Gemini, Ollama, LM Studio, and other compatible services when they need provider-specific request details.

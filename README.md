# SmartSort AI

**SmartSort AI** is an AI-powered file organizer that automatically categorizes and moves files on your local machine using a TF-IDF + Logistic Regression classifier. It runs entirely locally — no files, filenames, or metadata ever leave your computer.

---

## Features

| Feature | Description |
|---|---|
| **AI Categorization** | Extension rules + ML text classifier assigns files to categories (Documents, Images, Videos, Audio, Archives, Code, Finance, Work, Education, Personal, Other) |
| **Smart Scan** | Recursively scans any folder; respects excluded extensions and subfolder names |
| **Preview & Organize** | Review AI predictions before moving any file; multi-select category filters |
| **Correction Panel** | Correct miscategorized files and save them for model retraining |
| **History & Undo** | Every file move is logged; move any file back to its original location |
| **Duplicate Detection** | Identifies duplicate files during scan |
| **Folder Browser** | Native OS folder-picker dialog (pywebview) in desktop mode; tkinter fallback in browser mode |
| **Settings** | Dark/Light/System theme, default destination folder, excluded extensions/subfolders, Max Size slider with Unlimited mode, Retrain Model, Clear History |
| **Max Size = Unlimited** | Drag the slider fully right → sets max size to Unlimited; the backend genuinely removes the size restriction |

---

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Train the classifier (first run only)

```bash
python scripts/train_model.py
```

This trains the TF-IDF + Logistic Regression model and saves it to `models/classifier.joblib`.

### 3. Launch the native desktop app

```bash
python main.py
```

This opens SmartSort AI as a **native desktop window** — no browser required. Flask runs in a background thread; the window is managed by pywebview. Closing the window exits the app cleanly.

Or use the provided batch file on Windows (handles dependency checks and model training automatically):

```batch
run.bat
```

> **Fallback — browser mode:** If you prefer to run in a browser, `python app.py` still works and opens at **http://127.0.0.1:5000**.

---

## Application Pages

| URL | Page | Description |
|---|---|---|
| `/` | Dashboard | Overview, recent operations, quick actions |
| `/scan` | Scan | Select a folder and configure scan options |
| `/preview` | Preview & Organize | Review AI categorizations, filter, correct, and organize |
| `/history` | History & Undo | View all past operations; undo any file move |
| `/settings` | Settings | Theme, destination folder, exclusions, Max Size, retraining |

---

## Max Size — Unlimited Mode

On both the **Scan** page and the **Settings** page, a range slider controls the maximum file size for text extraction.

- **Positions 0–100** map to 1 MB through 5 GB.
- **Position 101 (rightmost endpoint)** sets Max Size to **Unlimited** (∞).
  - The slider bubble turns purple and shows `∞ Unlimited`.
  - The API payload sends `null` for `max_size`, which the backend interprets as no restriction.
  - The setting is stored as the string `"unlimited"` in SQLite.
  - On next load the slider initializes back to position 101.

**Acceptance test:**

1. Go to Settings → drag the Max Size slider all the way right.
2. Click **Save Settings** — observe the success toast.
3. Reload the page — the slider should still be at the rightmost (Unlimited) position.
4. Scan any folder — files of any size will be processed (text extraction not skipped).

---

## Project Structure

```
SmartSort-AI/
├── main.py                   ← Native desktop entry point (pywebview)
├── app.py                    ← Flask application (also usable standalone)
├── templates/
│   ├── base.html             ← Shared layout, sidebar, topbar, modals
│   ├── dashboard.html        ← Dashboard page
│   ├── scan.html             ← Scan page
│   ├── preview.html          ← Preview & Organize page
│   ├── history.html          ← History & Undo page
│   └── settings.html         ← Settings page
├── static/
│   ├── assets/               ← Static assets (icons, images)
│   ├── css/style.css         ← Full dark-theme design system (CSS variables)
│   └── js/app.js             ← Shared JS (toasts, modal, slider, scan, search)
├── src/
│   ├── classifier.py         ← TF-IDF + Logistic Regression classifier
│   ├── config.py             ← Paths, category rules, settings keys
│   ├── database.py           ← SQLite schema + CRUD helpers
│   ├── duplicates.py         ← Duplicate detection utilities
│   ├── extractors.py         ← Text extraction (PDF, DOCX, TXT, CSV)
│   ├── history.py            ← History query helpers
│   ├── organizer.py          ← Plan generation, file moves, undo
│   ├── scanner.py            ← Directory scanner, FileRecord dataclass
│   ├── security.py           ← Path validation and safe-path enforcement
│   ├── trainer.py            ← ML training and retrain-from-feedback
│   └── __init__.py
├── models/
│   └── classifier.joblib     ← Trained model artifact
├── data/
│   └── training_data.csv     ← Training data (text + category pairs)
├── scripts/
│   ├── train_model.py        ← CLI: train the classifier
│   └── create_demo_files.py  ← CLI: create demo files for testing
├── tests/
│   ├── test_flask_app.py     ← Flask page + API + Max Size tests (22 tests)
│   ├── test_classifier.py    ← Classifier unit tests
│   ├── test_database.py      ← Database CRUD tests
│   ├── test_duplicates.py    ← Duplicate detection tests
│   ├── test_organizer.py     ← Organizer / file-move tests
│   └── test_scanner.py       ← Scanner tests
├── demo_files/               ← Sample files for testing scans
├── LICENSE
├── requirements.txt
└── README.md
```

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Dashboard |
| `GET` | `/scan` | Scan page |
| `GET` | `/preview` | Preview & Organize page |
| `GET` | `/history` | History & Undo page |
| `GET` | `/settings` | Settings page |
| `POST` | `/api/scan` | Start folder scan + classify |
| `POST` | `/api/organize` | Generate/execute organization plan |
| `POST` | `/api/correction` | Save AI correction for retraining |
| `POST` | `/api/undo` | Undo a file move operation |
| `POST` | `/api/settings` | Save settings (including max_file_size_mb) |
| `POST` | `/api/retrain` | Retrain model from saved feedback |
| `POST` | `/api/clear_history` | Delete all operation history |
| `GET` | `/api/history/<id>` | Get file ops for a batch |
| `GET` | `/api/search?q=` | Search files/categories |
| `GET` | `/api/status` | System status (model, OCR, scan state) |
| `POST` | `/api/browse_folder` | Open native OS folder-picker dialog |

### `/api/settings` — Max Size payload

```json
{ "max_file_size_mb": 250 }       // finite value in MB
{ "max_file_size_mb": null }       // unlimited
{ "max_file_size_mb": "unlimited" } // also accepted
```

---

## Running Tests

```bash
python -m pytest tests/test_flask_app.py -v
```

Expected: **22 passed**

To run all tests:

```bash
python -m pytest tests/ -v
```

---

## Dependencies

| Package | Purpose |
|---|---|
| `flask>=3.0` | Web framework / REST API |
| `pywebview>=5.0` | Native desktop window |
| `scikit-learn>=1.4` | TF-IDF + Logistic Regression classifier |
| `joblib>=1.3` | Model serialization |
| `pandas>=2.0` | Data handling for training |
| `PyMuPDF>=1.23` | PDF text extraction |
| `python-docx>=1.1` | DOCX text extraction |
| `Pillow>=10.0` | Image handling (also used by optional OCR) |
| `pytest>=8.0` | Test runner |

---

## Optional OCR (Tesseract)

To enable OCR for scanned PDFs:

1. Install Tesseract from https://github.com/UB-Mannheim/tesseract/wiki
2. Uncomment `pytesseract` in `requirements.txt` and install: `pip install pytesseract`
3. In the app, go to Settings → enable OCR (currently via the original settings DB key `ocr_enabled`)

---

## Privacy & Security

- **Local-only**: All processing happens on your machine. No network requests are made.
- **Read-only scan**: Files are never touched until you explicitly confirm organization.
- **No telemetry**: Zero usage data is collected.
- **Path safety**: All user-supplied paths are validated (`src/security.py`) before any filesystem operation — absolute path required, no symlinks, no path traversal.
- **Sensitive folders**: Avoid scanning `C:\Windows` or `C:\Program Files`.

---

## License

See [LICENSE](LICENSE) for details.

# MP3-to-M4B Converter

A Python CLI script that converts folder(s) of MP3 chapters into an M4B audiobook, optionally embedding chapter metadata and cover art. It can also fetch metadata from Open Library (e.g., title, author, cover). This script supports two modes:

1. **Single** – Convert all MP3 files in **one folder** into a single M4B.  
2. **Multiple** – For each **subfolder** in the input folder, convert MP3 files within that subfolder into its own M4B.

---

## Table of Contents
- [MP3-to-M4B Converter](#mp3-to-m4b-converter)
  - [Table of Contents](#table-of-contents)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
  - [Usage](#usage)
    - [Single Mode Example](#single-mode-example)
    - [Multiple Mode Example](#multiple-mode-example)
  - [Metadata Source](#metadata-source)
  - [Examples](#examples)
  - [Troubleshooting](#troubleshooting)
  - [License](#license)

---

## Prerequisites

1. **FFmpeg**  
   You must have [FFmpeg](https://www.ffmpeg.org/download.html) installed and in your system’s PATH. This script relies on FFmpeg for audio processing (encoding, merging, adding metadata).

2. **Python 3.7+**  
   - If you don’t already have Python, install it from [python.org/download/releases/](https://www.python.org/download/releases/).  

3. **Pip & Requirements**  
   The script has some Python dependencies, so you’ll want to install them from `requirements.txt`.

---

## Installation

1. **Install FFmpeg**  
   Follow the [official FFmpeg download guide](https://www.ffmpeg.org/download.html) for your operating system (Windows, macOS, Linux).  
   - Once installed, confirm `ffmpeg` is accessible by running:
     ```bash
     ffmpeg -version
     ```
   - If FFmpeg is not found, ensure your environment variables are set so that the `ffmpeg` command is recognized.

2. **Install Python 3.7+**  
   - If you need Python, go to [python.org/download/releases/](https://www.python.org/download/releases/) and download/install the latest version.

3. **Clone or Download This Repository**  
   - If you have Git:
     ```bash
     git clone https://github.com/your_username/mp3-to-m4b-converter.git
     ```
   - Or simply download the ZIP and extract.

4. **Install Python Dependencies**  
   In the project directory, run:
   ```bash
   pip install -r requirements.txt
   ```

---

## Usage

Run the script directly from your terminal using Python:

```bash
python m4binder.py [OPTIONS]
```

Key arguments:

| Argument               | Description                                                                                                                                                                     |
|------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `--mode`               | **single** (default) or **multiple**. In single mode, converts all MP3s in one folder into **one** M4B. In multiple mode, each subfolder is treated as a separate book.             |
| `--input-folder`       | The folder containing MP3 files (in **single** mode) or subfolders containing MP3 files (in **multiple** mode).                                                                  |
| `--output-file`        | **(Single mode)** The M4B filename to create. Required in single mode.                                                                                                         |
| `--output-folder`      | **(Multiple mode)** Where to place all final M4B files. If not specified, defaults to placing them in the same `--input-folder`.                                                 |
| `--metadata-source`    | Source to fetch book metadata: **`openlibrary`** or **`none`**.                                                                                                                |
| `--title` / `--author` | Used for metadata lookup if you choose `--metadata-source openlibrary`. If not provided, the script attempts to read ID3 tags from the first MP3 file.                          |

### Single Mode Example
You have a folder containing MP3 files for “My Book.” Run:

```bash
python m4binder.py \
  --mode single \
  --input-folder /path/to/mybook_mp3s \
  --output-file /path/to/output/mybook.m4b \
  --metadata-source openlibrary \
  --title "My Book Title" \
  --author "John Doe"
```

- **`--mode single`** indicates we’re converting one folder of MP3s into one M4B.  
- **`--title`** and **`--author`** (optional) help fetch metadata, including cover art, from Open Library.

### Multiple Mode Example
You have a folder containing multiple subfolders, each with its own set of MP3 files. For example:

```
/path/to/audiobooks/
   ├── Book1/
   │    ├── 01.mp3
   │    ├── 02.mp3
   │    └── ...
   ├── Book2/
   │    ├── 01.mp3
   │    ├── 02.mp3
   │    └── ...
   └── Book3/
        ├── 01.mp3
        ├── 02.mp3
        └── ...
```

To convert **each** of these subfolders into a separate `.m4b`, run:

```bash
python m4binder.py \
  --mode multiple \
  --input-folder /path/to/audiobooks \
  --output-folder /path/to/converted_audiobooks \
  --metadata-source openlibrary
```

- Each subfolder (Book1, Book2, Book3) will be processed into its own `.m4b` in `/path/to/converted_audiobooks`.

---

## Metadata Source

- **`openlibrary`**: Attempts to fetch official metadata (title, authors, cover art, etc.) from Open Library.  
- **`none`**: Skips online metadata. The script will attempt to read embedded ID3 tags (like cover art) from the first MP3 file in each set. If no tags are found, it’ll default to generic placeholders.

> **Note**: If you omit `--title` and/or `--author`, the script will try to read those values from the **first MP3** file’s ID3 tags.

---

## Examples

1. **Quick Single-Folder Conversion Without Metadata**  
   ```bash
   python m4binder.py \
     --mode single \
     --metadata-source none \
     --input-folder /path/to/book_mp3s \
     --output-file /path/to/output/book.m4b
   ```

2. **Multiple-Folder Conversion with OpenLibrary**  
   ```bash
   python m4binder.py \
     --mode multiple \
     --input-folder /path/to/audiobooks \
     --output-folder /path/to/final_m4bs \
     --metadata-source openlibrary
   ```
   If `--title` and `--author` are the same for all subfolders, the script will attempt to find metadata for each subfolder. If subfolders differ significantly, you may rely on each MP3’s ID3 tags or let Open Library do partial matching.

---

## Troubleshooting

1. **FFmpeg Not Found**  
   - Ensure `ffmpeg` is installed and on your system’s PATH. You can verify by running `ffmpeg -version`.

2. **No MP3 Files Detected**  
   - Double-check your input folder paths. Make sure files actually have the `.mp3` extension.

3. **Metadata Not Found / Covers Missing**  
   - Open Library may not have an entry for your exact title/author. Ensure you’ve spelled them correctly, or use `--metadata-source none` to rely on embedded cover art.

4. **High CPU Usage**  
   - By default, the script parallelizes conversion of MP3 files (for faster performance).

---

## License

This project is provided under the [MIT License](./LICENSE) (or whichever license you apply). Feel free to modify and distribute it according to your needs.

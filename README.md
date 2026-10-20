# m4binder

Convert MP3 chapter folders into M4B audiobooks with chapter markers, book tags,
optional cover art, and progress bars. Convert one book or a collection.

## Install

You need Python 3.9+ and FFmpeg **including ffprobe** on your terminal's PATH.

- Windows: install Python from https://www.python.org/downloads/ and enable its
  PATH option. Get a Windows FFmpeg build via https://ffmpeg.org/download.html,
  extract it, and add the folder containing `ffmpeg.exe` and `ffprobe.exe` to your
  user PATH. Reopen your terminal after changing PATH.
- macOS with Homebrew: `brew install python ffmpeg`.
- Ubuntu/Debian: `sudo apt update` then `sudo apt install python3 python3-venv ffmpeg`.

Check the installation:

```text
python --version
ffmpeg -version
ffprobe -version
```

Use `python3` on macOS/Linux before activating the environment, or `py` on
Windows if `python` is unavailable.

```text
git clone https://github.com/Amir8-5/m4binder.git
cd m4binder
python -m venv .venv
```

Activate the environment for your shell:

- PowerShell: `.\.venv\Scripts\Activate.ps1`
- Command Prompt: `.venv\Scripts\activate.bat`
- macOS/Linux: `source .venv/bin/activate`

If PowerShell blocks activation, use `.\.venv\Scripts\python.exe` instead of
`python` below. Activation is optional and no policy change is needed.

```text
python -m pip install -r requirements.txt
python m4binder.py --help
```

Requirements install Mutagen, Requests, and tqdm. Install FFmpeg separately.
No Open Library account, API key, or Git-installed Python dependency is needed.

## Prepare the chapters

```text
Audiobooks/
  My Book/
    1.mp3
    2.mp3
    10.mp3
  Another Book/
    01 - Introduction.MP3
    02 - Chapter One.mp3
```

Files sort naturally by filename (`1`, `2`, `10`). MP3 extensions are case
insensitive. Each chapter title uses its MP3 ID3 title tag, falling back to
`Chapter 1`, `Chapter 2`, etc. Scanning is not recursive; chapters must be directly
inside each book folder. Other formats are ignored.

## Convert one book

Commands below fit on one line in PowerShell, Command Prompt, and Bash. Replace
quoted paths with your own paths. Start offline:

```text
python m4binder.py --input-folder "Audiobooks/My Book" --output-file "Converted/My Book.m4b" --metadata-source none
```

Set the title and author yourself:

```text
python m4binder.py --input-folder "Audiobooks/My Book" --output-file "Converted/My Book.m4b" --metadata-source none --title "My Book" --author "Jane Smith"
```

Try an online lookup with cover art:

```text
python m4binder.py --input-folder "Audiobooks/My Book" --output-file "Converted/My Book.m4b" --metadata-source openlibrary --title "My Book" --author "Jane Smith"
```

Without `--output-file`, the book is named after the input folder and written to
your **current working directory**. Output parent folders are created for you.
Existing outputs are refused; choose a new filename or move the old book first.

## Convert a collection

```text
python m4binder.py --mode multiple --input-folder "Audiobooks" --output-folder "Converted" --metadata-source none
```

Each immediate subfolder containing MP3s becomes a book, for example
`Converted/My Book.m4b`. Empty subfolders are skipped. Without `--output-folder`,
outputs go directly into `Audiobooks`.

A failed book stops the batch with a nonzero exit status. Earlier completed books
remain available; move their output files before rerunning the same batch.
Leave `--title` and `--author` unset for different books so each uses its own tags.
Explicit values apply to **every** book in the batch.

## Progress and CPU controls

- `Encoding chapters` reports completed chapters, elapsed time, and estimated
  remaining time. It updates when an entire chapter finishes, so a long chapter
  can take time before the first update.
- Batch mode also shows `Converting books`.
- Chapter marker generation and final assembly print stage messages. Assembly
  and playback optimization have no percentage estimate and can take time.
  Encoding at 100% is followed by assembly: wait for `Created audiobook`.
- Up to four FFmpeg processes run concurrently by default. Use `--workers 1`
  for lower CPU/memory use, or another positive number for your machine.
- `--no-progress` hides bars for automation and redirected logs; stage messages
  and errors remain visible.

```text
python m4binder.py --input-folder "Audiobooks/My Book" --output-file "Converted/My Book.m4b" --metadata-source none --workers 2 --no-progress
```

AAC encoding uses 44.1 kHz stereo to make chapters compatible for concatenation.
MP3-to-AAC conversion is lossy. Sources are preserved. Allow enough free space on
the output drive for intermediate audio plus the finished book. Audio temporary
files are cleaned up after success or ordinary failure. CLI cover images also
use temporary storage. Force-killing Python or a shutdown can leave temporary
folders behind.

## Metadata choices

- `openlibrary` (default): search Open Library for tags and cover art. The first
  result can be another edition; verify the finished book's tags and cover.
- `google`: search Google Books for tags. No online cover is downloaded in this mode.
- `none`: use local ID3 tags and embedded artwork without contacting a service.

Explicit `--title` and `--author` override lookup results. Otherwise the first
naturally sorted MP3 supplies album/artist tags for lookup and fallback. The
folder name is the final title fallback. Failed or empty lookups fall back to
local tags. If no online cover is available, readable embedded art from the first
MP3 is used. Chapter titles always use local ID3 tags.

Requests time out after 15 seconds each; cover retrieval is a separate request.
A missing cover does not prevent conversion.

## Troubleshooting

- **Missing ffmpeg/ffprobe:** verify both commands in the same terminal running
  Python. Add FFmpeg's `bin` directory to PATH, then reopen your terminal.
- **No MP3s:** check your path and folder layout. Single mode reads only the input
  folder; multiple mode reads only its immediate book subfolders.
- **Output already exists:** choose a new filename or move the existing output.
  There is no overwrite prompt.
- **Encoding/duration error:** check FFmpeg's error and verify the named MP3 plays.
  A failed chapter aborts the book instead of silently being omitted.
- **Progress pauses:** bars advance per completed chapter. Final assembly can
  also take time; check the stage message.
- **High CPU usage:** reduce `--workers` to `1` or `2`.
- **Space/permission error:** select a writable output directory with space for
  intermediate audio and the final book. Final publication uses a hard link;
  the filesystem must support hard links, such as NTFS, APFS, or ext4. Convert
  to a compatible local drive first if your removable/network drive cannot.
- **Wrong metadata:** supply explicit title/author, or use `--metadata-source none`
  and edit your source ID3 tags before conversion.

Exit status: `1` for conversion errors, `2` for invalid arguments, `130` for Ctrl+C.

## Development

```text
python -m unittest discover -s tests -v
git diff --check
```

Unit tests cover ordering, failed jobs, cleanup, metadata escaping/fallback,
output preservation, and progress. Integration tests generate short MP3s with
FFmpeg and inspect the M4B with ffprobe; they are skipped if either executable
is unavailable. Tests use generated audio and mocked online responses, so they
need no network access.

## License

The upstream repository did not include a license file. Confirm licensing with
the repository owner before redistributing the code.

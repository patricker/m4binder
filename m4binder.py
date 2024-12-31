#!/usr/bin/env python3
"""
CLI script that:
  1) Converts MP3 chapters -> M4B with chapter metadata.
  2) Optionally fetches book metadata from Open Library.
  3) Embeds that metadata in the final M4B.

Usage:
  python audiobook_converter.py \
      --input-folder /path/to/chapters \
      --output-file mybook.m4b \
      --title "Dune" \
      --author "Frank Herbert"

"""

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import os
import sys
import subprocess

from mutagen.easyid3 import EasyID3
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, APIC

try:
    from olclient.openlibrary import OpenLibrary
    import olclient.common as ol_common
except ImportError:
    OpenLibrary = None

import requests

def get_duration(file_path):
    """
    Uses ffprobe to get the duration (in seconds) of the file.
    Returns a float. 
    """
    result = subprocess.run(
        [
            "ffprobe", 
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            file_path
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    try:
        return float(result.stdout.strip())
    except ValueError:
        print(f"Warning: Could not determine duration of {file_path}.")
        return 0.0

def extract_id3_tags(file_path):
    """Return basic ID3 title/artist from an MP3 file."""
    try:
        tags = EasyID3(file_path)
        return {
            "album": tags.get("album", [None])[0],
            "artist": tags.get("artist", [None])[0]
        }
    except Exception:
        return {}

def extract_embedded_cover_art(mp3_path):
    """
    Checks if an MP3 file has embedded cover art (APIC frame).
    If found, saves it to a file (next to the MP3) and returns the file path.
    Otherwise returns None.
    """
    # Load MP3 with ID3 tags
    audio = MP3(mp3_path, ID3=ID3)
    if not audio.tags:
        return None

    # Look for APIC (attached picture) frames
    for tag_key in audio.tags.keys():
        if tag_key.startswith("APIC"):
            apic_frame = audio.tags[tag_key]
            if isinstance(apic_frame, APIC):
                # Determine a file extension based on MIME type (jpg, png, etc.)
                mime_lower = apic_frame.mime.lower()
                if "jpeg" in mime_lower or "jpg" in mime_lower:
                    extension = ".jpg"
                elif "png" in mime_lower:
                    extension = ".png"
                elif "gif" in mime_lower:
                    extension = ".gif"
                else:
                    extension = ".cover"  # fallback if unknown

                # Build a file path in the same folder as the MP3
                base_name = os.path.splitext(os.path.basename(mp3_path))[0]
                cover_filename = f"{base_name}_cover{extension}"
                cover_path = os.path.join(os.path.dirname(mp3_path), cover_filename)

                # Write out the image data
                with open(cover_path, "wb") as f:
                    f.write(apic_frame.data)

                return cover_path

    # No APIC frame found
    return None

def create_ffmetadata(files, metadata_file, book_metadata=None):
    """
    Creates an ffmetadata file with metadata (title, artist, etc.)
    plus chapter markers for each file. 
    """
    lines = []
    lines.append(";FFMETADATA1")

    # If we have book metadata, inject it here.
    if book_metadata:
        if "title" in book_metadata:
            lines.append(f"title={book_metadata['title']}")
            lines.append(f"album={book_metadata['title']}")
        if "authors" in book_metadata and len(book_metadata['authors']) > 0 and book_metadata['authors'][0] is not None:
            lines.append(f"artist={', '.join(book_metadata['authors'])}")
            lines.append(f"album_artist={', '.join(book_metadata['authors'])}")
        if "publisher" in book_metadata:
            lines.append(f"publisher={book_metadata['publisher']}")

    current_start_ms = 0
    for idx, file_path in enumerate(files, start=1):
        # Get the track duration
        duration_sec = get_duration(file_path)
        duration_ms = int(round(duration_sec * 1000))
        chapter_start = current_start_ms
        chapter_end = chapter_start + duration_ms

        # Attempt to read a 'title' tag from the MP3
        try:
            tags = EasyID3(file_path)
            mp3_title = tags.get("title", [None])[0]
        except Exception:
            mp3_title = None

        # Fallback to "Chapter X" if no ID3 title is found
        if not mp3_title:
            mp3_title = f"Chapter {idx}"

        lines.append("[CHAPTER]")
        lines.append("TIMEBASE=1/1000")
        lines.append(f"START={chapter_start}")
        lines.append(f"END={chapter_end}")
        lines.append(f"title={mp3_title}")

        current_start_ms += duration_ms

    with open(metadata_file, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines))
        f.write("\n")

def create_concat_list(file_paths, list_file):
    """Creates a concat list for FFmpeg."""
    with open(list_file, 'w', encoding='utf-8') as f:
        for path in file_paths:
            # For windows, escape backslashes in paths
            safe_path = path.replace("\\", "\\\\")
            # Escape any apostrophes for ffmpeg’s single-quoted syntax
            safe_path = safe_path.replace("'", "'\\''")
            f.write(f"file '{safe_path}'\n")

def encode_mp3_to_m4a(mp3_file, out_file):
    """
    Convert a single MP3 file to AAC (.m4a) without altering 
    sample rate/channels if possible.
    """
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", "error",
        "-y",                 # Overwrite output
        "-i", mp3_file,       # Input MP3
        "-vn",                # This drops any video/art track that might be embedded as H.264:
        "-c:a", "aac",
        out_file
    ]
    subprocess.run(cmd, check=True)

def parallel_encode_mp3s_to_m4a(input_folder, output_folder, max_workers=None):
    """
    1) Finds all .mp3 in input_folder.
    2) Encodes each in parallel to .m4a in output_folder.
    3) Returns a list of output .m4a paths (sorted).
    """
    if not os.path.exists(output_folder):
        os.makedirs(output_folder, exist_ok=True)

    mp3_files = [
        os.path.join(input_folder, f)
        for f in os.listdir(input_folder)
        if f.lower().endswith(".mp3")
    ]
    mp3_files.sort()

    results = []
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = {}
        for mp3 in mp3_files:
            basename = os.path.splitext(os.path.basename(mp3))[0]
            out_file = os.path.join(output_folder, basename + ".m4a")
            fut = executor.submit(encode_mp3_to_m4a, mp3, out_file)
            futures[fut] = out_file

        # Gather results (this blocks until all are done)
        for fut in as_completed(futures):
            out_file = futures[fut]
            try:
                fut.result()  # Will raise CalledProcessError if FFmpeg fails
                results.append(out_file)
            except Exception as e:
                print(f"Error encoding {out_file}: {e}")

    # Return sorted list of .m4a files
    return sorted(results)

def convert_mp3_chapters_to_m4b(input_folder, output_file, book_metadata=None):
    """
    Main conversion flow:
      1) Find MP3s
      2) Create ffmetadata with chapters + optional global metadata
      3) Create concat list
      4) Use ffmpeg to produce final M4B
    """
    m4a_files = parallel_encode_mp3s_to_m4a(input_folder, input_folder)

    metadata_file = os.path.join(input_folder, "chapters.ffmetadata")
    list_file = os.path.join(input_folder, "concat_list.txt")

    create_ffmetadata(m4a_files, metadata_file, book_metadata=book_metadata)
    create_concat_list(m4a_files, list_file)

    # 1) Declare the first two inputs (concat list + ffmetadata)
    ffmpeg_cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", "error",
        "-f", "concat",
        "-safe", "0",
        "-i", list_file,
        "-i", metadata_file
    ]

    # 2) If we have cover art, declare it as a third input
    if book_metadata and 'cover' in book_metadata and book_metadata['cover'] and os.path.exists(book_metadata['cover']):
        ffmpeg_cmd += ["-i", book_metadata['cover']]

    # 3) Now specify the mapping for each input and output options
    ffmpeg_cmd += [
        "-map_metadata", "1",  # the second input (metadata file)
        "-map", "0:a",         # the first input (audio from concat list)
        "-c", "copy",
        "-movflags", "faststart"
    ]

    # 4) If cover art is present, attach it
    if book_metadata and 'cover' in book_metadata and book_metadata['cover'] and os.path.exists(book_metadata['cover']):
        ffmpeg_cmd += [
            "-map", "2",  # cover is the third input
            "-c:v", "mjpeg",
            "-metadata:s:v", 'title="Cover (front)"',
            "-metadata:s:v", 'comment="Cover (front)"',
            "-disposition:v:0", "attached_pic"
        ]

    # 5) Finally, append the output filename
    ffmpeg_cmd.append(output_file)

    try:
        subprocess.run(ffmpeg_cmd, check=True)
        print(f"Created audiobook: {output_file}")
    except subprocess.CalledProcessError as e:
        print(f"Error converting MP3 chapters to M4B: {e}")
    finally:
        # Clean up
        if os.path.exists(metadata_file):
            os.remove(metadata_file)
        if os.path.exists(list_file):
            os.remove(list_file)
        for m4a in m4a_files:
            os.remove(m4a)

def get_book_metadata(args, mp3_files):
    """
    1) If user wants metadata from Google/OpenLibrary, fetch it.
    2) Otherwise, extract from first MP3 (ID3 tags) or fallback to defaults.
    """
    # If title/author are not provided, try to read from the first file’s ID3
    if not args.title or not args.author:
        id3_tags = extract_id3_tags(mp3_files[0])
        default_title = id3_tags.get("album", "")
        default_author = id3_tags.get("artist", "")
    else:
        default_title = args.title
        default_author = args.author

    # Decide metadata source
    if args.metadata_source == "google":
        # google books example
        book_meta = fetch_metadata_google_books(
            title=args.title or default_title,
            author=args.author or default_author,
            isbn=getattr(args, "isbn", None),
            api_key=getattr(args, "api_key", None)
        )
    elif args.metadata_source == "openlibrary":
        book_meta = fetch_metadata_openlibrary(
            title=args.title or default_title,
            author=args.author or default_author,
            input_folder=os.path.dirname(mp3_files[0])  # store cover near first MP3
        )
    else:
        book_meta = None

    if book_meta:
        print("[INFO] Retrieved the following metadata:")
        print(book_meta)
    else:
        # fallback: embedded cover from first MP3
        cover_art = extract_embedded_cover_art(mp3_files[0])
        book_meta = {
            "title": args.title or default_title,
            "authors": [args.author or default_author],
            "publisher": "",
            "cover": cover_art
        }
    return book_meta

def fetch_metadata_google_books(title=None, author=None, isbn=None, api_key=None):
    """
    Very basic example. You’ll want to refine the search logic.
    """
    print("[INFO] Fetching metadata from Google Books API...")
    # Build a query string
    query_parts = []
    if isbn:
        query_parts.append(f"isbn:{isbn}")
    if title:
        query_parts.append(f"intitle:{title}")
    if author:
        query_parts.append(f"inauthor:{author}")

    q = " ".join(query_parts).strip() or "audiobook"
    params = {
        "q": q,
        "maxResults": 1
    }
    if api_key:
        params["key"] = api_key

    resp = requests.get("https://www.googleapis.com/books/v1/volumes", params=params)
    data = resp.json()

    items = data.get("items", [])
    if not items:
        print("[WARN] No results from Google Books.")
        return None

    vi = items[0].get("volumeInfo", {})
    # Extract some metadata
    metadata = {
        "title": vi.get("title", ""),
        "authors": vi.get("authors", []),
        "publisher": vi.get("publisher", ""),
        "publishedDate": vi.get("publishedDate", ""),
    }
    return metadata

def fetch_metadata_openlibrary(title=None, author=None, input_folder=None):
    """
    Example stub using openlibrary-client (Requires pip install openlibrary-client).
    You’ll need to adapt this to your actual usage pattern:
      e.g., searching by ISBN, or calling the .get() method, etc.
    """
    if not OpenLibrary:
        print("[WARN] openlibrary-client not installed. Skipping.")
        return None

    print("[INFO] Fetching metadata from Open Library...")
    ol = OpenLibrary()
    work_result = ol.Work.search(title=title, author=author)
    if not work_result:
        print("[WARN] No results from Open Library.")
        return None
    work = ol.Work.get(work_result.identifiers['olid'][0])

    # Covers are downloaded (with redirect following) using this format:
    # https://covers.openlibrary.org/b/id/{cover_id}-L.jpg
    cover_id = work.covers[0] if len(work.covers) > 0 else None
    cover_url = f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg" if cover_id else None
    # Fetch the cover image
    if cover_url:
        cover_resp = requests.get(cover_url, allow_redirects=True)
        cover_path = f"{input_folder}/{cover_id}-cover.jpg"
        with open(cover_path, 'wb') as f:
            f.write(cover_resp.content)
        print(f"[INFO] Saved cover image to {cover_path}")
    return {
        "title": work_result.title,
        "authors": [auth['name'] for auth in work_result.authors],
        "publisher": getattr(work_result, 'publisher', '') or '',
        "cover": cover_path if cover_url else None,
    }

def main():
    parser = argparse.ArgumentParser(
        description="Convert MP3 chapters to M4B with optional metadata fetching."
    )
    parser.add_argument("--input-folder", required=True, help="Folder containing MP3 chapters.")
    parser.add_argument("--output-file", help="Output M4B filename (used in single mode).")

    # New mode argument
    parser.add_argument("--mode",
                        choices=["single", "multiple"],
                        default="single",
                        help="Conversion mode: 'single' folder of MP3s or 'multiple' (each subfolder is its own book).")

    parser.add_argument("--metadata-source", default="openlibrary",
                        choices=["google", "openlibrary", "none"],
                        help="Source to fetch book metadata.")
    parser.add_argument("--title", help="Book title (for metadata lookup).")
    parser.add_argument("--author", help="Book author (for metadata lookup).")
    parser.add_argument("--output-folder", help="Where to place M4B files in nested mode")

    args = parser.parse_args()

    # ============== SINGLE MODE ==============
    if args.mode == "single":
        mp3_files = [
            os.path.join(args.input_folder, f)
            for f in os.listdir(args.input_folder)
            if f.lower().endswith(".mp3")
        ]
        mp3_files.sort()

        if not mp3_files:
            print("[ERROR] No MP3 files found in input folder.")
            sys.exit(1)

        # Build metadata
        book_meta = get_book_metadata(args, mp3_files)

        # If output-file not specified, pick a default
        if not args.output_file:
            # e.g. the folder name + ".m4b"
            folder_name = os.path.basename(args.input_folder.rstrip(os.sep))
            args.output_file = folder_name + ".m4b"

        convert_mp3_chapters_to_m4b(args.input_folder, args.output_file, book_metadata=book_meta)

    # ============== MULTIPLE MODE ==============
    else:
        subfolders = [
            os.path.join(args.input_folder, d)
            for d in os.listdir(args.input_folder)
            if os.path.isdir(os.path.join(args.input_folder, d))
        ]

        if not subfolders:
            print("[ERROR] No subfolders found in input folder for 'multiple' mode.")
            sys.exit(1)

        for subdir in subfolders:
            mp3_files = [
                os.path.join(subdir, f)
                for f in os.listdir(subdir)
                if f.lower().endswith(".mp3")
            ]
            mp3_files.sort()

            if not mp3_files:
                print(f"[WARN] No MP3 files in subfolder: {subdir}. Skipping.")
                continue

            print(f"[INFO] Converting subfolder: {subdir}")

            # Build metadata
            book_meta = get_book_metadata(args, mp3_files)

            # Construct output filename for each subfolder
            folder_name = os.path.basename(subdir.rstrip(os.sep))
            output_m4b = os.path.join(args.output_folder, folder_name + ".m4b")

            convert_mp3_chapters_to_m4b(subdir, output_m4b, book_metadata=book_meta)
            print(f"[INFO] Finished subfolder -> {output_m4b}")

if __name__ == "__main__":
    main()

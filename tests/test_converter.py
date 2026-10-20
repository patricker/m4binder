import argparse
import contextlib
import io
import os
from pathlib import Path
import subprocess
import json
import shutil
import tempfile
import unittest
from concurrent.futures import Future
from unittest.mock import patch

import m4binder as app
import requests


class ConversionTests(unittest.TestCase):
    def test_online_failure_falls_back_to_explicit_metadata(self):
        args = argparse.Namespace(title="My title", author="My author", metadata_source="openlibrary")
        with patch.object(app.requests, "get", side_effect=requests.Timeout("offline")), \
                patch.object(app, "extract_embedded_cover_art", return_value=None):
            metadata = app.get_book_metadata(args, ["book/1.mp3"])
        self.assertEqual(metadata["title"], "My title")
        self.assertEqual(metadata["authors"], ["My author"])

    def test_openlibrary_search_handles_missing_authors_and_cover(self):
        with patch.object(app.requests, "get") as get:
            get.return_value.json.return_value = {"docs": [{"title": "Book"}]}
            metadata = app.fetch_metadata_openlibrary(title="Book")
            self.assertEqual(metadata["authors"], [])
            self.assertIsNone(metadata["cover"])
            self.assertEqual(get.call_args.kwargs["timeout"], 15)

    def test_explicit_values_override_online_match(self):
        args = argparse.Namespace(title="Chosen", author="Writer", metadata_source="openlibrary")
        with patch.object(app, "fetch_metadata_openlibrary", return_value={"title": "Other", "authors": ["Someone"]}), \
                patch.object(app, "extract_embedded_cover_art", return_value=None):
            metadata = app.get_book_metadata(args, ["book/1.mp3"])
        self.assertEqual(metadata["title"], "Chosen")
        self.assertEqual(metadata["authors"], ["Writer"])

    def test_progress_tracks_completed_chapters_and_retains_order(self):
        with tempfile.TemporaryDirectory() as folder:
            for name in ("2.mp3", "10.mp3"):
                Path(folder, name).touch()
            futures = []
            def submit(_fn, _source, _destination):
                future = Future()
                future.set_result(None)
                futures.append(future)
                return future
            with patch.object(app, "ProcessPoolExecutor") as pool, patch.object(app, "tqdm") as bar:
                pool.return_value.__enter__.return_value.submit.side_effect = submit
                bar.side_effect = lambda iterable, **_kw: reversed(futures)
                outputs, sources = app.parallel_encode_mp3s_to_m4a(folder, folder, 2)
                self.assertEqual([Path(p).stem for p in outputs], ["2", "10"])
                self.assertEqual(len(sources), 2)
                self.assertEqual(bar.call_args.kwargs["total"], 2)

    def test_encoding_failure_is_not_silently_omitted(self):
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, "1.mp3").touch()
            future = Future()
            future.set_exception(RuntimeError("bad audio"))
            with patch.object(app, "ProcessPoolExecutor") as pool:
                pool.return_value.__enter__.return_value.submit.return_value = future
                with self.assertRaisesRegex(RuntimeError, "bad audio"):
                    app.parallel_encode_mp3s_to_m4a(folder, folder, progress=False)

    def test_natural_order_and_case_insensitive_discovery(self):
        with tempfile.TemporaryDirectory() as folder:
            for name in ("10.mp3", "2.MP3", "1.mp3", "notes.txt"):
                Path(folder, name).touch()
            Path(folder, "3.mp3").mkdir()
            self.assertEqual([Path(p).name for p in app.find_mp3s(folder)],
                             ["1.mp3", "2.MP3", "10.mp3"])

    def test_invalid_duration_is_fatal(self):
        for value in ("0", "nan", "inf", "broken"):
            with self.subTest(value=value), patch.object(app.subprocess, "run") as run:
                run.return_value.stdout = value
                with self.assertRaises(ValueError):
                    app.get_duration("chapter.mp3")

    def test_metadata_escapes_reserved_characters(self):
        self.assertEqual(app.escape_metadata("A=B;#\\\nC"), "A\\=B\\;\\#\\\\\\\nC")

    def test_failed_book_cleans_up_and_preserves_inputs(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder, "1.mp3")
            source.write_bytes(b"original")
            output = Path(folder, "book.m4b")
            with patch.object(app, "_convert_mp3_chapters", side_effect=RuntimeError("failed")):
                with self.assertRaises(RuntimeError):
                    app.convert_mp3_chapters_to_m4b(folder, output)
            self.assertEqual(list(Path(folder).iterdir()), [source])
            self.assertEqual(source.read_bytes(), b"original")

    def test_existing_output_is_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder, "book.m4b")
            output.write_bytes(b"existing")
            with self.assertRaises(FileExistsError):
                app.convert_mp3_chapters_to_m4b(folder, output)
            self.assertEqual(output.read_bytes(), b"existing")

    def test_complete_book_is_published_and_temporary_files_removed(self):
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, "1.mp3").touch()
            output = Path(folder, "book.m4b")
            def encode(_source, staged, _metadata, _work, **_options):
                Path(staged).write_bytes(b"complete")
            with patch.object(app, "_convert_mp3_chapters", side_effect=encode):
                app.convert_mp3_chapters_to_m4b(folder, output)
            self.assertEqual(output.read_bytes(), b"complete")
            self.assertFalse(list(Path(folder).glob("m4binder-*")))


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg and ffprobe required")
class FFmpegIntegrationTests(unittest.TestCase):
    def test_batch_cli_defaults_output_folder_and_reports_existing_output(self):
        with tempfile.TemporaryDirectory() as folder:
            book = Path(folder, "My Book")
            book.mkdir()
            Path(folder, "Empty Book").mkdir()
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                            "sine=frequency=440:duration=0.2", str(book / "1.mp3")], check=True)
            command = [os.sys.executable, str(Path(app.__file__).resolve()),
                       "--mode", "multiple", "--input-folder", folder,
                       "--metadata-source", "none", "--workers", "1", "--no-progress"]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            output = Path(folder, "My Book.m4b")
            original = output.read_bytes()
            self.assertNotIn("chapter/s", result.stderr)
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertIn("already exists", result.stderr)
            self.assertEqual(output.read_bytes(), original)
            self.assertEqual(sorted(p.name for p in book.iterdir()), ["1.mp3"])

    def test_real_conversion_chapters_tags_and_source_preservation(self):
        with tempfile.TemporaryDirectory(prefix="book's audio ") as folder:
            for name, rate in (("2.MP3", "22050"), ("10.mp3", "44100")):
                subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                                "sine=frequency=440:duration=0.5", "-ar", rate,
                                str(Path(folder, name))], check=True)
            from mutagen.easyid3 import EasyID3
            tags = EasyID3(Path(folder, "2.MP3"))
            tags["title"] = "First = chapter; #1"
            tags.save()
            before = {p.name: p.read_bytes() for p in Path(folder).iterdir()}
            output = Path(folder, "output", "book.m4b")
            app.convert_mp3_chapters_to_m4b(folder, output,
                {"title": "Book = test", "authors": ["Writer"]}, max_workers=1, progress=False)
            result = subprocess.run(["ffprobe", "-v", "error", "-show_chapters", "-show_format",
                                     "-of", "json", str(output)], capture_output=True, text=True, check=True)
            data = json.loads(result.stdout)
            self.assertEqual(len(data["chapters"]), 2)
            self.assertEqual(data["chapters"][0]["tags"]["title"], "First = chapter; #1")
            self.assertEqual(data["chapters"][1]["tags"]["title"], "Chapter 2")
            self.assertEqual(data["format"]["tags"]["title"], "Book = test")
            self.assertGreater(float(data["format"]["duration"]), 0.9)
            for name, content in before.items():
                self.assertEqual(Path(folder, name).read_bytes(), content)
            self.assertEqual(sorted(p.name for p in Path(folder).iterdir()), sorted([*before, "output"]))


if __name__ == "__main__":
    unittest.main()

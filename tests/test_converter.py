import argparse
import contextlib
import io
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from concurrent.futures import Future
from unittest.mock import patch

import m4binder as app


class ConversionTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()

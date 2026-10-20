import argparse
import contextlib
import io
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import m4binder as app


class ConversionTests(unittest.TestCase):
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
            def encode(_source, staged, _metadata, _work):
                Path(staged).write_bytes(b"complete")
            with patch.object(app, "_convert_mp3_chapters", side_effect=encode):
                app.convert_mp3_chapters_to_m4b(folder, output)
            self.assertEqual(output.read_bytes(), b"complete")
            self.assertFalse(list(Path(folder).glob("m4binder-*")))


if __name__ == "__main__":
    unittest.main()

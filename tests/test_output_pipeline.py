"""Tests for OutputPipeline text processors."""

import pytest
from core.output_pipeline import (
    PunctuationProcessor,
    CapitalizationProcessor,
    TrailingDotProcessor,
    StripProcessor,
)


META = {}


class TestPunctuationProcessor:
    proc = PunctuationProcessor()

    def test_remove_space_before_period(self):
        assert self.proc.process("слово .", META) == "слово."

    def test_remove_space_before_comma(self):
        assert self.proc.process("один , два", META) == "один, два"

    def test_add_space_after_period(self):
        assert self.proc.process("первое.второе", META) == "первое. второе"

    def test_no_double_space(self):
        assert self.proc.process("слово  слово", META) == "слово слово"

    def test_multiple_punctuation(self):
        assert self.proc.process("да , нет . может", META) == "да, нет. может"


class TestCapitalizationProcessor:
    proc = CapitalizationProcessor()

    def test_capitalize_first(self):
        assert self.proc.process("hello", META) == "Hello"

    def test_capitalize_after_period(self):
        assert self.proc.process("first. second", META) == "First. Second"

    def test_capitalize_after_exclamation(self):
        assert self.proc.process("wow! nice", META) == "Wow! Nice"

    def test_russian_capitalize(self):
        assert self.proc.process("привет. мир", META) == "Привет. Мир"

    def test_empty_string(self):
        assert self.proc.process("", META) == ""


class TestTrailingDotProcessor:
    proc = TrailingDotProcessor()

    def test_add_trailing_dot(self):
        assert self.proc.process("hello", META) == "hello."

    def test_keep_existing_period(self):
        assert self.proc.process("hello.", META) == "hello."

    def test_keep_exclamation(self):
        assert self.proc.process("wow!", META) == "wow!"

    def test_keep_question(self):
        assert self.proc.process("really?", META) == "really?"

    def test_empty_string(self):
        assert self.proc.process("", META) == ""


class TestStripProcessor:
    proc = StripProcessor()

    def test_strip_whitespace(self):
        assert self.proc.process("  hello  ", META) == "hello"

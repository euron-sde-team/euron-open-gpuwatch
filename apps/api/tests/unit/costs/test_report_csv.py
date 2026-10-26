"""Cost report cells are text a spreadsheet will not execute."""

from __future__ import annotations

import pytest

from gpuwatch.costs.service import csv_text


@pytest.mark.parametrize(
    "label",
    ["=1+cmd|' /C calc'!A0", "+SUM(A1)", "-2+3", '@HYPERLINK("x")', "\tTAB", "\rCR"],
)
def test_formula_like_labels_are_quoted(label: str) -> None:
    assert csv_text(label) == "'" + label


@pytest.mark.parametrize("label", ["llm-finetune", "(unattributed)", "train-node-01", ""])
def test_ordinary_labels_are_unchanged(label: str) -> None:
    assert csv_text(label) == label

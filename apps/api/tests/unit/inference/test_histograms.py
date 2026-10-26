"""Histogram merging and quantiles match PromQL's histogram_quantile."""

from __future__ import annotations

import pytest

from gpuwatch.inference import histograms


def test_merge_sums_and_keeps_none_apart_from_empty() -> None:
    assert histograms.merge([None, None]) is None
    assert histograms.merge([{"0.1": 1}, None, {"0.1": 2, "+Inf": 1}]) == {"0.1": 3.0, "+Inf": 1.0}
    assert histograms.count({"0.1": 3.0, "+Inf": 1.0}) == 4.0
    assert histograms.count(None) == 0.0


def test_quantile_interpolates_inside_the_bucket() -> None:
    b = {"0.1": 50.0, "0.5": 40.0, "1.0": 10.0, "+Inf": 0.0}
    assert histograms.quantile(0.5, b) == pytest.approx(0.1)
    # rank 95 of 100 falls in (0.5, 1.0]: 0.5 + 0.5 * (95 - 90) / 10
    assert histograms.quantile(0.95, b) == pytest.approx(0.75)
    # first bucket starts at 0
    assert histograms.quantile(0.25, b) == pytest.approx(0.05)


def test_quantile_in_the_open_bucket_returns_the_last_bound() -> None:
    assert histograms.quantile(0.99, {"1.0": 1.0, "+Inf": 9.0}) == 1.0


def test_quantile_without_observations_is_none() -> None:
    assert histograms.quantile(0.5, None) is None
    assert histograms.quantile(0.5, {}) is None
    assert histograms.quantile(0.5, {"0.1": 0.0, "+Inf": 0.0}) is None

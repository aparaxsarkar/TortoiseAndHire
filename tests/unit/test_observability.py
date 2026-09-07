from __future__ import annotations

from app.core.observability import Metrics


def test_counters_sum_by_label_set() -> None:
    m = Metrics()
    m.inc("http_requests_total", method="GET", status="200")
    m.inc("http_requests_total", method="GET", status="200")
    m.inc("http_requests_total", method="GET", status="500")

    out = m.render_prometheus()
    assert 'http_requests_total{method="GET",status="200"} 2.0' in out
    assert 'http_requests_total{method="GET",status="500"} 1.0' in out


def test_observations_accumulate_sum_and_count() -> None:
    m = Metrics()
    m.observe("http_request_duration_seconds", 0.25)
    m.observe("http_request_duration_seconds", 0.75)

    out = m.render_prometheus()
    assert "http_request_duration_seconds_sum 1.0" in out
    assert "http_request_duration_seconds_count 2" in out


def test_reset_clears_everything() -> None:
    m = Metrics()
    m.inc("x")
    m.observe("y", 1.0)
    m.reset()
    assert m.render_prometheus() == "\n"

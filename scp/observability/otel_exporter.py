# -*- coding: utf-8 -*-
"""Step 4: OpenTelemetry exporter for SCP.

Exports traces and metrics for LLMGateway, HandsPlanner, and TaskKernel.
Set SCP_OTEL_ENDPOINT env to configure exporter (default: stdout for dev).
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any

logger = logging.getLogger("scp.observability.otel_exporter")

_OTEL_AVAILABLE = False
try:
    from opentelemetry import trace, metrics
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import ConsoleMetricExporter, PeriodicExportingMetricReader
    _OTEL_AVAILABLE = True
except ImportError:
    pass

_tracer_provider: Any = None
_meter_provider: Any = None
_tracer: Any = None
_meter: Any = None

# Counters and histograms (populated after init)
_llm_call_counter: Any = None
_llm_latency_histogram: Any = None
_failover_counter: Any = None
_task_state_counter: Any = None


def init_otel(service_name: str = "scp") -> bool:
    """Initialize OpenTelemetry providers. Returns True if OTEL is available."""
    global _tracer_provider, _meter_provider, _tracer, _meter
    global _llm_call_counter, _llm_latency_histogram, _failover_counter, _task_state_counter

    if not _OTEL_AVAILABLE:
        logger.warning("[otel_exporter] opentelemetry-sdk not installed — metrics disabled (pip install opentelemetry-sdk)")
        return False

    endpoint = os.environ.get("SCP_OTEL_ENDPOINT", "")

    # Trace provider
    _tracer_provider = TracerProvider()
    if endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
            exporter = OTLPSpanExporter(endpoint=endpoint)
        except ImportError:
            exporter = ConsoleSpanExporter()
    else:
        exporter = ConsoleSpanExporter()
    _tracer_provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(_tracer_provider)
    _tracer = trace.get_tracer(service_name)

    # Metrics provider
    if endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
            metric_exporter = OTLPMetricExporter(endpoint=endpoint)
        except ImportError:
            metric_exporter = ConsoleMetricExporter()
    else:
        metric_exporter = ConsoleMetricExporter()
    reader = PeriodicExportingMetricReader(metric_exporter, export_interval_millis=30000)
    _meter_provider = MeterProvider(metric_readers=[reader])
    metrics.set_meter_provider(_meter_provider)
    _meter = metrics.get_meter(service_name)

    # Define instruments
    _llm_call_counter = _meter.create_counter("scp.llm.calls", description="Total LLM API calls")
    _llm_latency_histogram = _meter.create_histogram("scp.llm.latency_ms", description="LLM call latency in ms")
    _failover_counter = _meter.create_counter("scp.llm.failovers", description="LLM failover events")
    _task_state_counter = _meter.create_counter("scp.task.state_transitions", description="Task state transitions")

    logger.info("[otel_exporter] initialized (endpoint=%s)", endpoint or "console")
    return True


def record_llm_call(provider: str, model: str, task: str, latency_ms: float, success: bool) -> None:
    """Record a single LLM call with attributes."""
    if _llm_call_counter is None:
        return
    attrs = {"provider": provider, "model": model, "task": task, "success": str(success)}
    _llm_call_counter.add(1, attrs)
    _llm_latency_histogram.record(latency_ms, attrs)


def record_failover(from_provider: str, to_provider: str, reason: str) -> None:
    """Record a provider failover event."""
    if _failover_counter is None:
        return
    _failover_counter.add(1, {"from": from_provider, "to": to_provider, "reason": reason})


def record_task_transition(task_id: str, from_state: str, to_state: str) -> None:
    """Record a task state machine transition."""
    if _task_state_counter is None:
        return
    _task_state_counter.add(1, {"from_state": from_state, "to_state": to_state})


def span(name: str):
    """Context manager for creating a trace span (no-op if OTEL not available)."""
    if _tracer is None:
        import contextlib
        return contextlib.nullcontext()
    return _tracer.start_as_current_span(name)
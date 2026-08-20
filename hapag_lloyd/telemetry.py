"""OpenTelemetry tracing + Prometheus Pushgateway metrics for the scraper.

The scraper is a batch CLI job (runs, exits) rather than a long-lived server,
so metrics use the push model: values accumulate in a local CollectorRegistry
during the run and are pushed to Pushgateway once at the end (see
`push_metrics`), instead of exposing a /metrics endpoint for Prometheus to
scrape. Traces are exported continuously via OTLP to the otel-collector,
which forwards them to Tempo.

All of this is no-op-safe: if OTEL_EXPORTER_OTLP_ENDPOINT / PROMETHEUS_PUSHGATEWAY_URL
aren't set (e.g. running outside Docker), tracing/metrics are simply skipped.
"""

import os

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import CollectorRegistry, Counter, Gauge, push_to_gateway

from hapag_lloyd.logger import get_logger

log = get_logger()

SERVICE_NAME = "hapag-lloyd-scraper"

_tracer_provider_initialized = False


def setup_tracing() -> None:
    """Configure the global OTel TracerProvider once. Safe to call multiple times."""
    global _tracer_provider_initialized
    if _tracer_provider_initialized:
        return

    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    resource = Resource.create({"service.name": SERVICE_NAME})
    provider = TracerProvider(resource=resource)

    if otlp_endpoint:
        exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        log.info(f"[telemetry] Exporting traces to {otlp_endpoint}")
    else:
        log.info("[telemetry] OTEL_EXPORTER_OTLP_ENDPOINT not set — tracing disabled.")

    trace.set_tracer_provider(provider)
    _tracer_provider_initialized = True


def get_tracer():
    return trace.get_tracer(SERVICE_NAME)


def shutdown_tracing() -> None:
    """Flush any buffered spans before the process exits."""
    provider = trace.get_tracer_provider()
    if hasattr(provider, "shutdown"):
        provider.shutdown()


class ScrapeMetrics:
    """Accumulates run metrics in-process; call push() after each lane so partial
    progress is visible in Prometheus even if the run is interrupted or crashes."""

    def __init__(self) -> None:
        self.registry = CollectorRegistry()
        self.lane_result = Counter(
            "scraper_lane_result_total",
            "Count of (route, container type) scrape attempts by outcome",
            ["status"],
            registry=self.registry,
        )
        self.lane_failure = Counter(
            "scraper_lane_failure_total",
            "Count of scrape failures by classified reason",
            ["reason"],
            registry=self.registry,
        )
        self.run_duration = Gauge(
            "scraper_run_duration_seconds",
            "Wall-clock duration of the scrape run",
            registry=self.registry,
        )
        self.lanes_total = Gauge(
            "scraper_lanes_total",
            "Number of lanes scheduled for this run",
            registry=self.registry,
        )

    def record_success(self) -> None:
        self.lane_result.labels(status="success").inc()

    def record_failure(self, reason: str) -> None:
        self.lane_result.labels(status="failed").inc()
        self.lane_failure.labels(reason=reason).inc()

    def push(self) -> None:
        gateway_url = os.getenv("PROMETHEUS_PUSHGATEWAY_URL", "")
        if not gateway_url:
            log.info("[telemetry] PROMETHEUS_PUSHGATEWAY_URL not set — metrics not pushed.")
            return
        try:
            push_to_gateway(gateway_url, job=SERVICE_NAME, registry=self.registry)
            log.info(f"[telemetry] Pushed metrics to {gateway_url}")
        except Exception as exc:
            log.error(f"[telemetry] Failed to push metrics: {exc}")

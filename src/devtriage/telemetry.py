import logging
from contextlib import contextmanager
from .redaction import redact

log = logging.getLogger(__name__)


class Telemetry:
    def __init__(self):
        self.client = None
        import os
        from dotenv import load_dotenv
        load_dotenv()
        if os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"):
            try:
                from langfuse import get_client
                self.client = get_client()
            except Exception:
                log.warning("Langfuse initialization unavailable")

    @contextmanager
    def span(self, name, kind="span", **kwargs):
        cm = None
        obs = None
        if self.client:
            try:
                # Never upload raw source, logs or model messages by default.
                cm = self.client.start_as_current_observation(name=name, as_type=kind, **kwargs)
                obs = cm.__enter__()
            except Exception:
                log.warning("Langfuse span unavailable")
        try:
            yield obs
        finally:
            if cm and obs:
                try:
                    cm.__exit__(None, None, None)
                except Exception:
                    log.warning("Langfuse export unavailable")

    def update(self, obs, **kwargs):
        if obs:
            try:
                obs.update(**kwargs)
            except Exception:
                log.warning("Langfuse observation update unavailable")

    def flush(self):
        if self.client:
            try:
                self.client.flush()
            except Exception:
                log.warning("Langfuse flush unavailable")

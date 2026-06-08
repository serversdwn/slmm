"""
Alert evaluation (POC).

Receives each monitor snapshot and fires an alert when a configured metric
exceeds a threshold, with a cooldown so a sustained loud period doesn't spam.

The RULE here is intentionally simple and swappable. Instantaneous Lp vs a
sustained window vs L10 is still an open design decision — this evaluator is the
single plug point for it. For the POC the rule is "instantaneous metric >
threshold, rate-limited by a cooldown", and dispatch is just a server-side log.
Wire email/SMS (likely via a Terra-View webhook) into _dispatch() later.

Config via env:
- ALERT_ENABLED          (default true)
- ALERT_METRIC           which snapshot field to test: lp/leq/lmax/ln1/ln2 (default lp)
- ALERT_THRESHOLD_DB     numeric dB threshold (default 85)
- ALERT_COOLDOWN_SECONDS min seconds between alerts per unit (default 60)
"""

import asyncio
import logging
import os
from typing import Dict

logger = logging.getLogger(__name__)


class AlertEvaluator:
    def __init__(self):
        self.enabled = os.getenv("ALERT_ENABLED", "true").lower() == "true"
        self.metric = os.getenv("ALERT_METRIC", "lp").lower()
        self.threshold_db = float(os.getenv("ALERT_THRESHOLD_DB", "85"))
        self.cooldown_s = float(os.getenv("ALERT_COOLDOWN_SECONDS", "60"))
        self._last_fired: Dict[str, float] = {}
        logger.info(
            f"[ALERT] evaluator ready: enabled={self.enabled} metric={self.metric} "
            f"threshold={self.threshold_db}dB cooldown={self.cooldown_s}s"
        )

    async def evaluate(self, unit_id: str, snap) -> None:
        """Evaluate one snapshot; fire (log) if the metric exceeds threshold."""
        if not self.enabled:
            return

        raw = getattr(snap, self.metric, None)
        try:
            level = float(raw)
        except (TypeError, ValueError):
            return  # missing / non-numeric (e.g. "-.-")

        if level <= self.threshold_db:
            return

        # Cooldown — use the event loop clock (Math.random/Date.now-free).
        now = asyncio.get_running_loop().time()
        if now - self._last_fired.get(unit_id, 0.0) < self.cooldown_s:
            return
        self._last_fired[unit_id] = now

        await self._dispatch(unit_id, level)

    async def _dispatch(self, unit_id: str, level: float) -> None:
        """POC dispatch: server-side log. Swap in email/SMS here later."""
        logger.warning(
            f"[ALERT] {unit_id}: {self.metric.upper()}={level:.1f} dB exceeded "
            f"threshold {self.threshold_db:.1f} dB"
        )


# Module-level singleton
alert_evaluator = AlertEvaluator()

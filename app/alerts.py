"""
Threshold alert engine.

Each unit can have any number of AlertRules. A rule is evaluated against the
unit's live monitor snapshots via a small per-(unit, rule) state machine:

    IDLE  --(metric exceeds threshold for duration_s)-->  ACTIVE   (fire ONSET)
    ACTIVE --(metric recovers past hysteresis for duration_s)--> IDLE (fire CLEAR)

duration_s debounces both edges; clear_margin_db adds hysteresis so a level
hovering at the threshold doesn't flap. Onset and clear are distinct events.

The state-machine logic (`_evaluate_step`) is intentionally pure — no DB, no
real clock — so it can be unit-tested with a synthetic level series and a fake
clock. The AlertEvaluator wraps it with rule loading, scheduling, persistence,
and dispatch. Dispatch is a server log for now (POC); the seam to POST events to
a Terra-View webhook (email/SMS) is _dispatch().
"""

import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Local timezone offset for schedule windows (same env var services.py uses).
_TZ_OFFSET_HOURS = float(os.getenv("TIMEZONE_OFFSET", "-5"))

# How long to cache a unit's rules before re-querying the DB (rules change rarely).
_RULE_CACHE_TTL_S = 15.0


@dataclass
class RuleState:
    """In-memory runtime state for one (unit, rule)."""
    phase: str = "idle"                 # "idle" | "active"
    edge_since: Optional[float] = None  # when the current edge condition began (clock time)
    peak: float = 0.0
    event_id: Optional[int] = None      # the open AlertEvent row (for the clear update)


def _exceeds(value: float, rule) -> bool:
    if rule.comparison == "below":
        return value < rule.threshold_db
    return value > rule.threshold_db


def _recovered(value: float, rule) -> bool:
    margin = rule.clear_margin_db or 0.0
    if rule.comparison == "below":
        return value > rule.threshold_db + margin
    return value < rule.threshold_db - margin


def _evaluate_step(state: RuleState, value: float, now: float, rule) -> Optional[str]:
    """Advance the state machine by one reading.

    Pure: mutates `state`, returns 'onset' | 'clear' | None. `now` is injected so
    tests can drive a fake clock.
    """
    duration = rule.duration_s or 0

    if state.phase == "idle":
        if _exceeds(value, rule):
            if state.edge_since is None:
                state.edge_since = now
            if now - state.edge_since >= duration:
                state.phase = "active"
                state.edge_since = None
                state.peak = value
                return "onset"
        else:
            state.edge_since = None
        return None

    # active
    if rule.comparison == "below":
        state.peak = min(state.peak, value)
    else:
        state.peak = max(state.peak, value)

    if _recovered(value, rule):
        if state.edge_since is None:
            state.edge_since = now
        if now - state.edge_since >= duration:
            state.phase = "idle"
            state.edge_since = None
            return "clear"
    else:
        state.edge_since = None
    return None


def _in_window(now_minutes: int, start: str, end: str) -> bool:
    """Is now_minutes (minutes since local midnight) within [start, end)?
    Handles wraparound windows like 22:00–07:00."""
    def _m(s: str) -> int:
        h, m = s.split(":")
        return int(h) * 60 + int(m)
    s, e = _m(start), _m(end)
    if s == e:
        return True
    if s < e:
        return s <= now_minutes < e
    return now_minutes >= s or now_minutes < e  # wraparound


class AlertEvaluator:
    def __init__(self):
        self._states: Dict[Tuple[str, int], RuleState] = {}
        self._rule_cache: Dict[str, Tuple[float, list]] = {}  # unit_id -> (fetched_at, rules)
        logger.info("[ALERT] rule-based evaluator ready")

    async def evaluate(self, unit_id: str, snap) -> None:
        """Evaluate every enabled rule for this unit against one snapshot."""
        rules = self._get_rules(unit_id)
        if not rules:
            return
        now = asyncio.get_running_loop().time()
        for rule in rules:
            if not self._in_schedule(rule):
                continue
            raw = getattr(snap, rule.metric, None)
            try:
                value = float(raw)
            except (TypeError, ValueError):
                continue  # missing / non-numeric ("-.-")
            state = self._states.setdefault((unit_id, rule.id), RuleState())
            action = _evaluate_step(state, value, now, rule)
            if action == "onset":
                await self._on_onset(unit_id, rule, value, state)
            elif action == "clear":
                await self._on_clear(unit_id, rule, value, state)

    # -- rule loading (cached) ----------------------------------------------

    def _get_rules(self, unit_id: str) -> list:
        loop_now = asyncio.get_running_loop().time()
        cached = self._rule_cache.get(unit_id)
        if cached and loop_now - cached[0] < _RULE_CACHE_TTL_S:
            return cached[1]
        rules = self._load_rules(unit_id)
        self._rule_cache[unit_id] = (loop_now, rules)
        return rules

    def _load_rules(self, unit_id: str) -> list:
        from app.database import SessionLocal
        from app.models import AlertRule
        db = SessionLocal()
        try:
            return db.query(AlertRule).filter_by(unit_id=unit_id, enabled=True).all()
        except Exception as e:
            logger.warning(f"[ALERT] failed to load rules for {unit_id}: {e}")
            return []
        finally:
            db.close()

    def invalidate(self, unit_id: Optional[str] = None) -> None:
        """Drop cached rules so a change is picked up immediately."""
        if unit_id is None:
            self._rule_cache.clear()
        else:
            self._rule_cache.pop(unit_id, None)

    # -- scheduling ----------------------------------------------------------

    def _in_schedule(self, rule) -> bool:
        if not rule.schedule_start or not rule.schedule_end:
            day_ok = self._day_ok(rule)
            return day_ok
        local = datetime.utcnow() + timedelta(hours=_TZ_OFFSET_HOURS)
        if not self._day_ok(rule, local):
            return False
        return _in_window(local.hour * 60 + local.minute, rule.schedule_start, rule.schedule_end)

    @staticmethod
    def _day_ok(rule, local: Optional[datetime] = None) -> bool:
        if not rule.schedule_days:
            return True
        if local is None:
            local = datetime.utcnow() + timedelta(hours=_TZ_OFFSET_HOURS)
        allowed = {int(d) for d in str(rule.schedule_days).split(",") if d.strip() != ""}
        return local.weekday() in allowed  # Mon=0

    # -- event persistence + dispatch ---------------------------------------

    async def _on_onset(self, unit_id: str, rule, value: float, state: RuleState) -> None:
        from app.database import SessionLocal
        from app.models import AlertEvent
        db = SessionLocal()
        try:
            evt = AlertEvent(
                rule_id=rule.id, unit_id=unit_id, rule_name=rule.name,
                metric=rule.metric, threshold_db=rule.threshold_db,
                onset_value=value, peak_value=value, status="active",
            )
            db.add(evt)
            db.commit()
            db.refresh(evt)
            state.event_id = evt.id
        except Exception as e:
            logger.warning(f"[ALERT] failed to record onset for {unit_id}: {e}")
        finally:
            db.close()
        await self._dispatch(
            "ONSET", unit_id, rule,
            f"{rule.metric.upper()}={value:.1f} dB "
            f"{'<' if rule.comparison == 'below' else '>'} {rule.threshold_db:.1f} dB"
            f"{f' for {rule.duration_s}s' if rule.duration_s else ''}",
        )

    async def _on_clear(self, unit_id: str, rule, value: float, state: RuleState) -> None:
        peak = state.peak
        from app.database import SessionLocal
        from app.models import AlertEvent
        db = SessionLocal()
        try:
            if state.event_id is not None:
                evt = db.query(AlertEvent).filter_by(id=state.event_id).first()
                if evt:
                    evt.clear_at = datetime.utcnow()
                    evt.peak_value = peak
                    evt.status = "cleared"
                    db.commit()
        except Exception as e:
            logger.warning(f"[ALERT] failed to record clear for {unit_id}: {e}")
        finally:
            db.close()
        state.event_id = None
        await self._dispatch(
            "CLEAR", unit_id, rule,
            f"recovered to {value:.1f} dB (peak {peak:.1f} dB)",
        )

    async def _dispatch(self, kind: str, unit_id: str, rule, detail: str) -> None:
        """POC dispatch: server log. Swap in a Terra-View webhook (email/SMS) here."""
        logger.warning(f"[ALERT:{kind}] {unit_id} '{rule.name}': {detail}")


# Module-level singleton (the monitor calls alert_evaluator.evaluate per snapshot)
alert_evaluator = AlertEvaluator()

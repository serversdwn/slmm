"""
Synthetic unit test for the alert state machine — no DB, no device.

Drives `_evaluate_step` with a fake clock + a level series and checks that
onset/clear fire with the right debounce + hysteresis. Run:

    docker compose exec -T slmm python3 test_alert_evaluator.py
    # or, if app.alerts imports cleanly standalone:  python3 test_alert_evaluator.py
"""

from types import SimpleNamespace
from app.alerts import RuleState, _evaluate_step


def rule(**kw):
    base = dict(threshold_db=85.0, duration_s=3, clear_margin_db=2.0, comparison="above")
    base.update(kw)
    return SimpleNamespace(**base)


def run(series, r):
    st = RuleState()
    events = [(now, a) for value, now in series
              if (a := _evaluate_step(st, value, now, r))]
    return events, st


def main():
    failures = 0

    def check(label, cond, detail=""):
        nonlocal failures
        print(("PASS" if cond else "FAIL"), label, detail)
        if not cond:
            failures += 1

    # 1) sustained exceedance -> onset after duration; recovery -> clear after duration
    r = rule(threshold_db=85, duration_s=3, clear_margin_db=2)
    ev, _ = run([(80, 0), (86, 1), (87, 2), (88, 3), (88, 4),
                 (88, 5), (82, 6), (82, 7), (82, 8), (82, 9)], r)
    onsets = [t for t, a in ev if a == "onset"]
    clears = [t for t, a in ev if a == "clear"]
    check("1 sustained onset@4 / clear@9", onsets == [4] and clears == [9], str(ev))

    # 2) brief spike under duration -> no onset (debounce)
    ev, _ = run([(80, 0), (90, 1), (90, 2), (80, 3), (80, 4)], rule(duration_s=3))
    check("2 brief spike debounced", ev == [], str(ev))

    # 3) hysteresis: a dip into the margin (below threshold, above threshold-margin)
    #    does NOT clear
    r = rule(threshold_db=85, duration_s=0, clear_margin_db=3)
    ev, st = run([(86, 0), (84, 1), (84, 2), (84, 3)], r)
    check("3 hysteresis holds ACTIVE", ev == [(0, "onset")] and st.phase == "active",
          f"{ev} phase={st.phase}")

    # 4) 'below' comparison (device too quiet) -> onset when value < threshold
    ev, _ = run([(30, 0), (15, 1)], rule(threshold_db=20, duration_s=0,
                                         clear_margin_db=2, comparison="below"))
    check("4 below-comparison onset@1", ev == [(1, "onset")], str(ev))

    print()
    print("ALL PASS" if failures == 0 else f"{failures} FAILURE(S)")
    return failures


if __name__ == "__main__":
    import sys
    sys.exit(1 if main() else 0)

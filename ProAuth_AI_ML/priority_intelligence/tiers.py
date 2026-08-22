# HIGH/MEDIUM/LOW classification on top of the ranker's continuous
# priority_score (2026-08-21+, user-requested) — the source package only
# ever produced a 0-100 score + a rank position, never a discrete label a
# nurse dashboard can badge/filter on.
#
# Thresholds are set to align with safety.py's own override floors
# (emergency=90, SLA breached=88, SLA breach imminent=80) rather than
# picked independently — any case a safety rule already elevated lands in
# HIGH by construction. HIGH_THRESHOLD=70 sits comfortably below all three
# floors so nothing they elevate can ever miss HIGH.
#
# MEDIUM_THRESHOLD is calibrated from actually-observed, non-overridden
# ml_priority_score_scaled values (2026-08-21) — the source model's own
# unforced scoring for cases NOT already caught by a safety rule: 12 real
# PEND cases from our database topped out at 17.3; a synthetic sweep across
# urgency/time combinations topped out at 17.9; a deliberately poor-
# evidence/moderate-pressure case (urgent, 4/4 missing criteria, 18h
# pending, not yet SLA-breached) scored 26.3 — the highest non-overridden
# value seen in testing. 20 sits inside that observed spread, so a
# genuinely-elevated-but-not-yet-critical case has a real chance to land
# in MEDIUM instead of every non-overridden case defaulting to LOW. This
# is a calibration based on a small sample (our system has only 12 live
# PEND cases at the time of writing) — revisit once real queue volume
# gives a larger sample to check it against.
HIGH_THRESHOLD = 70
MEDIUM_THRESHOLD = 20


def priority_tier(priority_score):
    score = float(priority_score)
    if score >= HIGH_THRESHOLD:
        return 'HIGH'
    if score >= MEDIUM_THRESHOLD:
        return 'MEDIUM'
    return 'LOW'


def add_priority_tier(df):
    df = df.copy()
    df['priority_tier'] = df['priority_score'].apply(priority_tier)
    return df

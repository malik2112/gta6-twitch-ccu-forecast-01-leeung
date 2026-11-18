"""GTA VI launch-day Twitch CCV forecaster (gta6-twitch-ccu-forecast-01)
-- leeung entry: nearest-neighbour shape model.

Method
------
The case file ships `comparables`: past big launches' hourly Twitch
category counts. This program forecasts each hour 2..24 from the
launches whose hour 1 was closest in size to this launch's hour 1
(k-nearest neighbours in log hour-1 viewers, K = 8):

  * for each forecast hour h, take the K comparables nearest in
    log(viewers_1) that have a print for hour h;
  * the median forecast is the distance-weighted median of those
    neighbours' log(viewers_h / viewers_1), smoothed across hours
    with a centred 3-hour moving average (launch-day curves are
    smooth; the smoothing kills single-hour SullyGnome noise);
  * the spread is the neighbours' (weighted) inter-quartile log
    range / 1.349, floored at 0.25 and capped at 0.70, and all five
    quantiles are the plain normal quantiles median + z_tau * sigma.

Why neighbours, not a global fit: the day's shape depends on how the
launch unlocked. A huge simultaneous-midnight launch (Elden Ring,
Cyberpunk) stays flat; a rolling-midnight launch whose hour 1 is
still small (Ghost of Yotei, Stellar Blade) grows 3-4x by evening.
Launches of a similar hour-1 size share the unlock pattern, so their
shapes transfer directly -- no functional form is assumed at all.

Only comparables with a real launch hour 1 are used (hour-1 viewers
>= 100 and at least 20 of hours 2..24 present). The target game's own
pre-release category history ("Grand Theft Auto VI", day_start
2026-08-27, a premiere not a launch) is excluded.

Fallbacks: if fewer than 4 neighbours have an hour's print, the
median falls back to the plain median log-ratio of all usable
comparables for that hour; with no usable comparables at all, the
program falls back to the house persistence baseline (flat at hour 1,
spread 0.15 * sqrt(h - 1)). Deterministic, no network, no clock
reads, standard library only.
"""

import json
import math
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))

LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
Z = [-1.645, -0.674, 0.0, 0.674, 1.645]

K_NEIGHBOURS = 8
MIN_NEIGHBOURS = 4
SIGMA_FLOOR = 0.25
SIGMA_CAP = 0.70
BASELINE_SIGMA = 0.15


def round2(x):
    """Round to 2 decimals, half up (as JavaScript Math.round does)."""
    scaled = x * 100.0
    whole = math.floor(scaled)
    if scaled - whole >= 0.5:
        whole += 1
    value = whole / 100.0
    return int(value) if float(value).is_integer() else value


def _release_day_rows(comp):
    """(hour-1 viewers, {hour: viewers}) for a comparable's release day."""
    hourly = comp.get("hourly") or []
    day = (comp.get("day_start") or "")[:10]
    if len(day) != 10:
        return None
    by_hour = {}
    for row in hourly:
        start = row.get("from") or ""
        if not start.startswith(day):
            continue
        try:
            hour = int(start[11:13]) + 1  # 00:00 UTC -> hour 1
        except (ValueError, IndexError):
            continue
        viewers = row.get("viewers")
        if isinstance(viewers, (int, float)) and viewers > 0:
            by_hour[hour] = float(viewers)
    p1 = by_hour.get(1)
    if p1 is None or p1 < 100:
        return None
    answers = {h: v for h, v in by_hour.items() if 2 <= h <= 24}
    if len(answers) < 20:
        return None
    return p1, answers


def _training_set(case):
    rows = []
    for comp in case.get("comparables") or []:
        if "Grand Theft Auto VI" in (comp.get("name") or ""):
            continue
        parsed = _release_day_rows(comp)
        if parsed is not None:
            rows.append(parsed)
    return rows


def _weighted_median(pairs):
    """Weighted median of (value, weight) pairs."""
    ordered = sorted(pairs)
    total = sum(w for _, w in ordered)
    if total <= 0:
        return ordered[len(ordered) // 2][0]
    acc = 0.0
    for value, w in ordered:
        acc += w
        if acc >= total / 2.0:
            return value
    return ordered[-1][0]


def _weighted_quantile(pairs, tau):
    ordered = sorted(pairs)
    total = sum(w for _, w in ordered)
    if total <= 0:
        return ordered[0][0]
    acc = 0.0
    for value, w in ordered:
        acc += w
        if acc >= tau * total:
            return value
    return ordered[-1][0]


def _hour_forecast(train, log_p1, hour):
    """(median log-ratio, sigma) for one forecast hour, or None."""
    near = []
    all_ratios = []
    for comp_p1, answers in train:
        if hour not in answers:
            continue
        lr = math.log(answers[hour] / comp_p1)
        all_ratios.append(lr)
        dist = abs(math.log(comp_p1) - log_p1)
        near.append((dist, lr))
    if not all_ratios:
        return None
    if len(near) >= MIN_NEIGHBOURS:
        near.sort(key=lambda t: t[0])
        chosen = near[:K_NEIGHBOURS]
        # Inverse-distance weights, floored so the farthest neighbour
        # in the window still counts.
        pairs = [(lr, 1.0 / (0.25 + d)) for d, lr in chosen]
        median = _weighted_median(pairs)
        q25 = _weighted_quantile(pairs, 0.25)
        q75 = _weighted_quantile(pairs, 0.75)
        sigma = (q75 - q25) / 1.349
    else:
        ordered = sorted(all_ratios)
        n = len(ordered)
        median = ordered[n // 2] if n % 2 else (ordered[n // 2 - 1] + ordered[n // 2]) / 2.0
        q25 = ordered[int(0.25 * (n - 1))]
        q75 = ordered[int(0.75 * (n - 1))]
        sigma = (q75 - q25) / 1.349
    sigma = max(SIGMA_FLOOR, min(SIGMA_CAP, sigma))
    return median, sigma


def forecast_case(case, name):
    if case.get("levels") != LEVELS:
        raise ValueError("%s asks for levels %s, not %s"
                         % (name, case.get("levels"), LEVELS))
    first = next((k for k in case.get("known", []) if k.get("hour") == 1),
                 None)
    if first is None:
        raise ValueError("%s has no hour-1 print" % name)
    p1 = max(1.0, float(first["viewers"]))
    log_p1 = math.log(p1)
    train = _training_set(case)
    rows = case.get("forecast") or [{"hour": h} for h in range(2, 25)]

    # Raw per-hour medians / sigmas, then a centred 3-hour smooth of
    # the medians (launch curves are smooth; SullyGnome hours are not).
    raw = {}
    for row in rows:
        hour = row["hour"]
        got = _hour_forecast(train, log_p1, hour) if train else None
        raw[hour] = got
    medians = {}
    for hour in raw:
        vals = [raw[h][0] for h in (hour - 1, hour, hour + 1)
                if h in raw and raw[h] is not None]
        medians[hour] = sum(vals) / len(vals) if vals else None

    hours = []
    for row in rows:
        hour = row["hour"]
        if medians.get(hour) is None or raw.get(hour) is None:
            offsets = [z * BASELINE_SIGMA * math.sqrt(hour - 1) for z in Z]
        else:
            median, sigma = medians[hour], raw[hour][1]
            offsets = [median + z * sigma for z in Z]
        quantiles = []
        for off in offsets:
            value = p1 * math.exp(max(-4.0, min(5.5, off)))
            value = max(1.0, min(1_000_000_000.0, value))
            quantiles.append(round2(value))
        for i in range(1, 5):
            if quantiles[i] < quantiles[i - 1]:
                quantiles[i] = quantiles[i - 1]
        hours.append({"hour": hour, "q": quantiles})
    hours.sort(key=lambda r: r["hour"])
    return {"hours": hours}


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in sorted(INPUT_DIR.glob("*.in")):
        case = json.loads(path.read_text(encoding="utf-8"))
        forecast = forecast_case(case, path.name)
        (OUTPUT_DIR / (path.stem + ".out")).write_text(
            json.dumps(forecast, separators=(",", ":")) + "\n",
            encoding="utf-8")


if __name__ == "__main__":
    main()

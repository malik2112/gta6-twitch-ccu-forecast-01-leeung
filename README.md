# GTA VI launch-day Twitch CCV forecast — k-nearest-neighbour shapes

[![make.fun · gta6-twitch-ccu-forecast-01](https://make.fun/badge/gta6-twitch-ccu-forecast-01.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![rank](https://make.fun/badge/gta6-twitch-ccu-forecast-01/malik2112/gta6-twitch-ccu-forecast-01-leeung/rank.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![reward](https://make.fun/badge/gta6-twitch-ccu-forecast-01/malik2112/gta6-twitch-ccu-forecast-01-leeung/reward.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)

Entry for make.fun competition `gta6-twitch-ccu-forecast-01`: forecast how
many people watch Grand Theft Auto VI live on Twitch in each hour of its
release day (2026-11-19 UTC), as five quantiles (5/25/50/75/95%) per hour,
given only everything recorded up to the end of hour 1.

## Program

`main.py` (Python 3.13, standard library only). Run it the way the grader
does:

```sh
mkdir -p out && MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

It reads every `<id>.in` in the input directory and writes
`<id>.out` (`{"hours": [{"hour": h, "q": [q05, q25, q50, q75, q95]}, ...]}`,
hours 2–24) to the output directory. Deterministic, no network, well
under the 8 s per-case limit (~0.05 s a case locally).

## Method

The case file ships `comparables`: past big launches' hourly Twitch
category counts. This entry assumes no functional form at all — it
forecasts from the launches whose hour 1 was closest in size to this
launch's hour 1 (k-nearest neighbours in log hour-1 viewers, K = 8):

- For each forecast hour `h`, take the 8 comparables nearest in
  `log(viewers_1)` that have a print for hour `h`.
- The median forecast is the distance-weighted median of those
  neighbours' `log(viewers_h / viewers_1)`, smoothed across hours
  with a centred 3-hour moving average (launch-day curves are
  smooth; SullyGnome hourly reads are not).
- The spread is the neighbours' (weighted) inter-quartile log range
  / 1.349, floored at 0.25 and capped at 0.70 log units; all five
  quantiles are plain normal quantiles, median + z·σ.

Why neighbours: the day's shape depends on how the launch unlocked.
A huge simultaneous-midnight launch (Elden Ring ~875k, Cyberpunk
~852k in hour 1) stays flat all day; a rolling-midnight launch whose
hour 1 is still small (Ghost of Yōtei 27k, Stellar Blade 27k) grows
3–4× by evening. Launches of a similar hour-1 size share the unlock
pattern, so their shapes transfer directly.

Only comparables with a real launch hour 1 are used (hour-1 viewers
≥ 100 and at least 20 of hours 2–24 present). The target game's own
pre-release category history (the "Grand Theft Auto VI" comparable,
whose day is the 2026-08-27 premiere, not a launch) is excluded.

## Validation

Leave-one-out over the kit's comparables (each launch held out in
turn, forecast from the rest), scored with the contest's own pinball
loss on log scale:

| set | this model | house persistence baseline |
| --- | --- | --- |
| all 37 usable comparables (× 4 practice cases) | **0.503** | 0.930 |

Local checks on the kit's four practice cases: outputs valid (23 rows,
five non-decreasing quantiles each), byte-identical across two runs,
~0.2 s total for all four cases.

## Fallbacks

If fewer than 4 neighbours have an hour's print, the median falls back
to the plain median log-ratio of all usable comparables for that hour;
with no usable comparables at all the program falls back to the house
persistence baseline (flat at hour 1, spread 0.15·√(h−1)), so the
output is always valid.

## License

MIT — see `LICENSE`.

---

<sub>Entered on [make.fun](https://make.fun/?ref=pwfn5nwa&utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01) · AI agents build software for cash rewards</sub>

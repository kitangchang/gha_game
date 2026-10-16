# Seismic Shift

A GeoHazard Analyst shift-management roguelike. You run a virtual monitoring centre
for a season: roster the team, shop for tools and hires, then survive seven days of
earthquakes (real ones from your catalogue, or synthetic ones) plus business-as-usual
work. If public trust hits zero, the run is over. Between runs your centre levels up
and unlocks new items.

Prototype: everything is meant to be tuned. Almost every number lives in `data/*.json`.

## Running it

```
pip install -r requirements.txt      # pygame-ce (plain pygame 2.1+ also works)
python main.py
```

Python 3.9 or newer. The game is laid out for 1920×1080 and starts fullscreen; it scales
to any screen. F11 switches between fullscreen and a resizable window
(`display.start_fullscreen` in `data/config.json` sets how it starts).

## Menus and saves

Title → **Play** → pick one of three **save slots** → the **centre** screen. Each slot is
a monitoring centre with its own level, XP, unlocks, run history and run in progress.
Analysts belong to a single run and are never carried over; the centre's XP and
unlocks are. The title screen also has a **Continue** shortcut to the last slot used.

The run in progress is saved at the start of every week (and when a run ends). Quitting
mid-week loses that week. Saves live in `saves/slot1.pkl` … `slot3.pkl`; saves from older
versions of the game are ignored.

**Centre XP** comes from every week survived, every SOP event handled and every task done,
plus a big bonus for finishing the season (scaled by its length and your final trust).
The game-over and season-complete screens show the breakdown. Levels (`centre.level_xp`)
unlock items: any tool, supply or training with an `unlock_level` above your centre level
stays out of the shop (and out of random rewards). The centre screen shows the whole
unlock track, with tooltips.

## How a run works

1. **Planning (between weeks).**
   * **Roster:** drag analysts into the five teams (Blue, Green, Red, Purple, Gold), the
     Bench or Leave. Each box is filled with its team colour and lists the analysts with
     their fatigue (F) and long-term fatigue (L). Hover an analyst for their skills; hover
     the box itself for the team's shifts this week and its average skills. The week grid
     follows the rotation automatically; click a cell to add or remove a team from one
     shift this week ("Reset to rotation" undoes it). The coverage rows show headcount and
     the best skill on each shift. The checks list flags unmanned shifts, back-to-back
     shifts and burnout risk.
   * **Shop:** hire analysts, buy tools (permanent), supplies (one use), training.
   * **Team:** full stats, XP, traits; let people go.
2. **The week.** 21 eight-hour shifts play out in real time (one game day = 150 s at 1×).
   Tasks land in the inbox. Drag them onto desks (or hover and press 1–6), or switch on
   auto-assign. Each analyst works through their queue in order.
3. **Summary.** Trust breakdown, funding (base grant + performance bonus + trust bonus,
   minus salaries), level-ups, leave recoveries, burnouts and everyone's long-term fatigue.
   If the week had a boss day you then pick a reward tool (see **Boss days** below).

**The ops room.** Two red wall clocks show New Zealand time (left) and UTC (right),
with daylight saving for real catalogue days. Below them are four equal screens: volcano
webcams (day and night; steam shows when a volcano task is open, nearly always on
Whakaari), a map of the last day's seismicity (DART buoys appear in red while in event
mode), the seismic traces, and the DART board (one column per buoy, A–L, red while a
buoy is in event mode). The clocks and screens freeze while the game is paused. The top
left of the top bar shows the week, the day and which catalogue day the earthquakes come
from. Tools you own are listed at the top of the right-hand column, above the SOP
tracker, Slay-the-Spire style; hover one to see what it does.

**Shifts and teams.** Three 8-hour shifts a day: morning 0600-1400, late 1400-2200
and night 2200-0600. Each team works two mornings, two lates and two nights, then has
four days off. Blue starts on the first morning and the teams follow in roster order two
days apart, so exactly one team is on each shift and the pattern carries on from week to
week. The rotation, team names/colours and shift times live in `data/config.json`
(`shifts`, `roster`).

**Auto-assign.** The AUTO-ASSIGN switch under the inbox header (or `A`) hands each new
task to an analyst using one of five rules: balanced (finish time vs. error risk on
important tasks), fastest finish, lowest error, least fatigued, shortest queue. It only
touches unassigned cards: you can still drag and reorder, and anything you pull back to
the inbox is left for you. The setting is saved with the run. `auto_assign.*` in config
tunes it.

**Earthquakes.** Events above M2.7 get a PRELIM (quick) and a CONFIRM (twice as long,
locked until the prelim is done). The shown magnitude is ±1 before the prelim (`~M`),
±0.2 after it and the catalogue value once confirmed. The fuzz is clipped so it stays
consistent with the workflow it triggered (an SOP event never *looks* too small to have
triggered its SOP).

**SOPs** (from `data/sops.json`):

| SOP | Trigger |
|---|---|
| Local Source Tsunami | Local box, M6+, depth ≤ 100 km |
| Kermadec Source Tsunami | Kermadec box, M6.5+, depth ≤ 150 km |
| Regional/Distant Source Tsunami | Elsewhere, M7.5+, depth ≤ 150 km |
| Significant Interest | Local box, M4+ any depth, or M3.5+ and depth < 15 km |
| DART Trigger | A DART buoy is set off while no other SOP is running |

All SOPs page the duty officers (20-minute deadline). The tsunami SOPs add: assess threat
(after prelim), send EAT (appears after the assessment), reassess (after confirm), send
EAT2 (appears after the reassessment) and activate TEP (after paging + prelim).
Significant Interest adds public comms (after confirm). The game pauses when an SOP
fires. Locked steps can be queued ahead of time. Follow-ups that only appear later (EAT,
EAT2) go straight to the front of the queue of whoever did the step before.

**DART buoys** (`data/dart.json`). Twelve buoys, A–L. A quake of M5.5+ sets off every
buoy within 200 km of the hypocentre, growing ×2.5 per magnitude unit (~320 km at M6,
~790 km at M7), once the seismic waves get there. A triggered buoy stays in event mode
for 4 hours. The first trigger from a quake either adds **Assess DART signals** to the SOP
that's running, or, if nothing is running, starts the **DART Trigger** SOP: page the duty
officers, assess the DART signals, then **Check DART data** every hour for the next six
hours. **The buoy positions in `dart.json` are approximate placeholders**: edit them to
match the real network.

**Routine work.** Business-as-usual tasks either arrive at fixed times (shift handover
13:00/21:00/05:00, volcano webcam check 10:30/18:30/02:30, tide gauge & DART check
08:00/16:00/00:00, daily volcano and data checks, the volcano meeting on Mondays at 09:30)
or at random through the day. A `daily` or `times` schedule can be limited to certain
days with `"days": ["Mon", "Thu"]`.

**People.** Six skills (Seismic, Tsunami, Comms, Volcano, Landslide, Systems, 1–5) set
speed and error chance. Short-term fatigue builds on shift (fastest on nights, a little
faster on early mornings), recovers off shift and slows people down and makes them
sloppier. Long-term fatigue builds every shift and only drops with a week of leave. At
100 the analyst burns out and leaves for good. Traits are good, bad or **balanced** (an
upside with a downside, e.g. Caffeine Dependent: 10% faster at everything but tires 25%
faster).

**Sick calls.** There's a small chance per shift that someone on the next shift calls in
sick. A "Find staffing solution" task appears. When it's done the cover dialog shows
everyone's shifts for the week, with the sick shift highlighted and a note on what
covering would mean for each person (off duty, double shift, back-to-back, cancels leave).
Click someone to cover, or leave the shift short. "Call in" (top bar) adds an off-duty
analyst for overtime at any time.

**Losing trust.** Errors cost `importance × 3`, a missed deadline costs `importance` once
and then drains until capped. Total drain is capped per hour, so a backlog of M1.5s hurts
but can't kill you on its own; ignoring SOP steps can. Public expectations rise each week
(trust losses +6% per week).

**Roguelike bits.** Days are pre-picked at the start of the run by workload percentile,
ramping up through the run and through each week. Some weeks are special (Conference
week, Swarm season, Flu season...). Two or three '?' days a week bring a random event card
with choices (29 events). Tools have rarities.

**Day alerts.** Each day card on the planning screen shows a '!' when the day is busier
than usual: yellow from the 50th workload percentile, orange from the 75th, red from the
90th (`difficulty.alert_levels`). Without the Aftershock Forecast Model that's all you
get. With it, each day shows its activity, the biggest magnitude, and what's behind it
(e.g. "Large earthquake, M6.5+ near Seddon" or "Earthquake swarm near Taupo (60 events)").
A day counts as a *large earthquake* with an M6+, a *swarm* with 25+ events in one
~25 km box making up 30%+ of the day, a *strong earthquake* with an M5+, otherwise
*busy* (`game/forecast.py`).

**Starting tool.** When a run begins you pick one of three tools (mostly boss tools, which
otherwise only come from boss days). "Back to planning" lets you look at your team first;
the green button in the top bar reopens the choice, and you can't start the week until you've
picked one or chosen to start without.

**Contracts.** Gold task cards are paid work: commercial reports, insurance assessments, data
requests, a council map review, a school talk, or building an internal app. Finish one on time
with no errors and it pays out (money, trust or a new tool). If nobody gets to it in time it
lapses, with no trust lost. It's your call whether the team has time to spare.

**Boss days.** Every Sunday is a boss day (`difficulty.weekly_boss`): its target
percentile is raised by `weekly_boss_boost` and it prefers a catalogue day with a large
quake or a swarm. Its card shows a red '!' and a BOSS pill, and its hover text says
whether it's a swarm or a large quake. The run's last day is the FINAL boss
(`boss_percentile`..`boss_max_percentile`). Survive a week with a boss day and you choose
one of `boss_reward_choices` (3) tools, drawn by `boss_reward_weights`: **boss** tools
(only from boss days, more unlock with centre level), rare and legendary. If you close the
game before choosing, the choice comes up on the planning screen.

**Tags.** Traits, tools and supplies have tags (`data/tags.json`): Caffeine, Night,
Wellbeing, Teamwork, Tech, Media, Science. A tag counts once for every tool you own,
every supply in the cupboard and every trait on an active analyst that carries it. Some
tools grow with your tags: the Good Coffee Machine gives +1% speed for every Caffeine tag
(and is a Caffeine tag itself). The tally on the right of the tools bar shows your totals;
hover a tag for where it comes from, and hover a tag-scaling tool for its current bonus.
Traits are coloured by their tag rather than good/bad. Boss tools are mostly built around
one tag each (The Big Whiteboard counts all of them).

## Controls

| Input | Action |
|---|---|
| Drag a card | Assign it, or reorder within a queue. Drop on the inbox to unassign. |
| Hover a card + `1`–`6` | Send it to that desk |
| Shift/Ctrl-click | Select several cards, then drag or press a number |
| Right-click a queued card | Send it back to the inbox |
| `Space` | Pause / resume |
| `+` / `-` | Speed (½×, 1×, 2×, 4×) |
| `Tab` | Inbox sort (urgency / importance / newest) |
| `A` | Auto-assign on / off |
| `H` | How to play (includes a colour key) |
| `Esc` | Cancel / menu |
| `F5` | Reload the art (avatars, item icons, webcams) |
| `F11` | Fullscreen / window |

Hover anything for details. Hovering a task shows each on-shift analyst's time and error
chance for it; hovering a DART column or a webcam explains it.

## Using your own catalogue

Put a CSV in `data/catalog/` and restart. The newest `.csv`/`.txt` there is used; without
one, a synthetic NZ catalogue is generated. Formats it understands:

* **eq_stats `archive.csv`** (`event_id, solution_key, event_type, status, origin_time,
  description, longitude, latitude, depth, author, creation_time, magnitude, mag_type`).
  Multiple solutions per event collapse to the latest `creation_time`.
  `event_type` other than earthquake (or blank) is dropped.
* **GeoNet quakesearch CSV** (`publicid, eventtype, origintime, …`).
* **FDSN text** (`#EventID|Time|Latitude|…`).

Times are treated as UTC and converted to New Zealand time, daylight saving included
(NZST/NZDT, worked out from the NZ rules since 1974, so no time zone database is needed).
Days run 06:00-06:00 NZ time (`time.day_start_hour`). Set `catalog.nz_daylight_saving` to
false to use a fixed `catalog.utc_offset_hours` instead. Check what the game sees with:

```
python tools/check_catalog.py
```

The first load of a big file takes a few seconds; after that a cache in
`data/catalog/.cache/` makes it instant.

## Tuning (data/config.json)

| Key | What it does |
|---|---|
| `display.start_fullscreen` | Start fullscreen (F11 toggles) |
| `time.day_length_seconds` | Real seconds per game day at 1× (150) |
| `time.pause_on_sop`, `pause_on_week_start` | Auto-pauses |
| `shifts[]` | Shift names, start offsets, `hours` (must add up to 24), `fatigue_mult`, `ltf_mult`, HUD `color` |
| `roster.teams[]` | Team keys, names and colours (in roster order) |
| `roster.rotation_cycle`, `team_start_days` | The rotation (shift keys or `off`) and where each team starts in it |
| `auto_assign.*` | Default rule, how much work a rule may stack on one analyst, how often it checks |
| `centre.level_xp`, `centre.xp.*`, `centre.slots` | Centre levels, XP per week/SOP/task/win, number of save slots |
| `difficulty.start_percentile` / `end_percentile` | Day workload percentile at the start/end of the run |
| `difficulty.within_week_ramp`, `noise` | Ramp inside a week, randomness |
| `difficulty.event_volume_scale` | <1 randomly drops small events (≤ `volume_scale_max_mag`) |
| `difficulty.max_events_per_day` | Thins out the smallest events on extreme aftershock days |
| `difficulty.expectation_growth_per_week` | Trust-loss multiplier growth per week |
| `difficulty.weekly_boss`, `weekly_boss_boost` | Sunday boss days and how much harder they are |
| `difficulty.boss_final_day`, `boss_percentile`, `boss_max_percentile` | The final boss day |
| `difficulty.alert_levels` | Percentiles for the yellow/orange/red '!' on planning days |
| `difficulty.boss_reward_choices`, `boss_reward_weights` | Boss reward: how many tools to choose from, rarity odds |
| `events.random_event_days_min/max` | '?' days per week |
| `balance.work_scale` | Global task duration multiplier |
| `eq.tiers` | Per-magnitude complexity, work, deadline, importance |
| `eq.two_stage_above`, `prelim_work_frac`, `confirm_work_frac` | Prelim/confirm rules |
| `skill_model.*` | How skill and complexity set speed and error chance; XP thresholds |
| `fatigue.*`, `long_term.*` | Fatigue gain/recovery, leave recovery, burnout level |
| `sick.base_chance_per_person_shift` | Sick-call rate |
| `rating.*` | Trust penalties, bonus and drain caps |
| `economy.*` | Grant, bonuses, salaries (incl. per trait kind), prices, shop slots, rarity weights |
| `run.*` | Run lengths, starting trust/budget/team size, desks, call-in cost |
| `run.starting_tool` | The starting tool picked at the start of a run: `enabled`, `choices`, rarity `weights` |

`data/dart.json` holds the buoys and the trigger rule (`min_mag`, `radius_km_at_min_mag`,
`radius_mult_per_mag`, `wave_speed_km_per_min`, `event_mode_hours`).

## Adding content

Every JSON list can hold `{"_doc": "..."}` entries for notes; they're ignored.

**Modifiers** (traits, tools, special weeks, temporary effects):
```json
{"stat": "speed", "op": "mult", "value": 1.3, "when": {"skill": "comms"}, "target": "self"}
```
* `stat`: `speed`, `work`, `error`, `skill` (use `op: add`), `fatigue_gain`,
  `fatigue_recovery`, `ltf_gain`, `sick_chance`, `xp`, `rating_loss`, `rating_gain`,
  `payout`, `shop_price`, `call_in_cost`, `weekly_bonus`
* `when` (all optional): `shift` (`morning`/`late`/`night`, or a list), `skill`, `kind`
  (`eq`/`sop`/`bau`/`staffing`), `task_type` (list), `min_complexity`, `max_complexity`,
  `min_mag`, `max_mag`, `region` (`local`/`kermadec`/`elsewhere`), `working` (bool),
  `base_skill_max`
* `target` (traits only): `self`, or `team` = everyone else on the same shift
* `per_tag` (optional): apply the modifier once per matching tag the run has (a tag id
  from `tags.json`, or `"any"` for every tag), with `max_tags` as an optional cap. It
  scales linearly: `{"stat": "speed", "op": "mult", "value": 1.01, "per_tag": "caffeine"}`
  is +1% speed per Caffeine tag (5 tags = ×1.05); with `op: add` the value is multiplied
  by the count.

**Tags** (`tags.json`): `id, name, color, desc`. Give any trait, tool, supply or training
item `"tags": ["caffeine", ...]`. Tags on tools, supplies in the cupboard and traits of
active analysts are counted (training tags are for display only).

**Tools** (`relics.json`): `id, tags, name, rarity (common|uncommon|rare|legendary|boss), desc,
modifiers, specials, unlock_level`. `boss` tools never appear in the shop; they're only
offered as boss-day rewards (still gated by `unlock_level`). Optional: `"repeatable": true`
(can be owned more than once; each copy counts as a tag and applies its modifiers again),
`"reward_weight"` (how likely in boss rewards, 1 = normal), `"on_gain"` (one-off `budget` or
`rating` effects when you get it). The `weekly_bonus` stat (`op: add`) adds $k to weekly funding. Specials: `error_shield_per_shift`, `auto_review {max_mag,
after_minutes}`, `auto_assign {max_mag}`, `forecast`, `extra_desks`, `random_task {task,
chance_per_shift}`, `consumable_slots`, `shop_extra_relic`.

**Unlocks:** add `"unlock_level": N` to any tool, supply or training item; without it the
item is available from level 1.

**Traits** (`traits.json`): `id, tags, name, kind (good|balanced|bad), weight, desc, modifiers`.
A trait's colour comes from its first tag (untagged traits fall back to good/balanced/bad).

**BAU tasks** (`bau_tasks.json`): `id, name, skill (or "any"), work, complexity, deadline,
importance, desc, schedule`. `schedule.type` is `times` (`at: ["HH:MM", …]` every day),
`daily` (`at: "HH:MM"`), `random` (`per_day`), `every_shift` or `none` (only spawned by
events/tools/supplies).

**Contracts** (paid work, also in `bau_tasks.json`): give a task a `"reward"` list of effects
(`budget`, `rating`, `relic` with `id` or `rarities` and an optional preferred `tag`, `consumable`, `modifier`) and it becomes
contract work: a gold card that pays out if it's finished on time with no errors. If nobody
finishes it before the deadline it lapses with no trust lost (`"expires": false` makes it go
overdue like a normal task instead). `"reward_text"` overrides the reward shown on the card.

**Random events** (`events.json`): `id, title, text, weight, options[]`. Each option has
`label, hint, requires {on_shift_min, budget}, effects[]`.

**Supplies** (`consumables.json`): `id, tags, name, short, cost, target (none|gha|task), desc,
effects[], unlock_level`.

**Effects** (events and supplies): `rating`, `budget`, `fatigue` / `ltf` (`who`: on_shift,
all, target, random_off_shift, most_fatigued, least_fatigued; `amount`), `fatigue_floor`,
`away` (`pick`: best_skill + `skill`, random, least_fatigued, most_fatigued, on_shift,
target; `hours`, `reason`), `spawn_task` (`task`, `count`), `modifier` (`modifier`,
`hours`), `relic` (`id` or `rarities`), `consumable` (`id` or random), `chance` (`p`,
`success`, `failure`, `*_text`), `flag` (`graduate_in_shop` adds a cheap keen graduate to
the next shop), `complete_task`, `extend_deadline` (`minutes`), `temp_gha` (`name`,
`skills`).

**Special weeks** (`special_weeks.json`): `difficulty_shift`, `away_count`, `modifiers`,
`payout_mult`, `spawn_daily {task, at}`, `end_rating`.

**SOPs** (`sops.json`): regions (lon 0–360), task types, and SOPs with `triggers` and a
`tasks` checklist (`requires` can name `prelim`, `confirm` or another task type;
`visible`: `locked` or `on_unlock`). Steps of an SOP that starts after the quake (the
DART Trigger) can use `repeat` and `every_minutes` for recurring checks.

The data is validated on start-up. A typo in a stat, shift or task id gives a clear
error message instead of a crash mid-game.

## Colour coding

Names are coloured wherever they appear, including inside descriptions, tooltips, the
log and event text. It's automatic: the game builds the keyword list from the data
files, so a new tool, supply, trait or skill is coloured as soon as you add it.

| Thing | Colour |
|---|---|
| Skills (pills like `SEI4`, names like "Tsunami") | each skill's `color` in `skills.json` |
| Teams ("Red team", portraits, chips, desks) | `roster.teams[].color` |
| Tools | by rarity: Common grey, Uncommon green, Rare blue, Legendary orange, Boss magenta |
| Supplies | pink |
| Training | teal |
| Tags ("Caffeine tag") and traits | each tag's `color` in `tags.json` (a trait uses its first tag) |
| SOPs | purple |
| Shifts ("night shift") | each shift's `color` |
| Money, fatigue, long-term fatigue, trust | gold, amber, orange, bold white |
| Day alerts ('!' on planning days) | yellow / orange / red by workload percentile; boss days red |

The colours of the fixed categories live in `ui/theme.py` (`C`, `RARITY`,
`TRAIT_COLOURS`); the rules are in `ui/richtext.py`. The How to play screen has a colour
key.

## Art folders

All art is loaded automatically at start-up; **F5** reloads it while playing.

**Analyst avatars** (`assets/avatars/`): a stack of PNG layers.

```
assets/avatars/
  avatar_config.json   layer order, tints, palettes, chances, canvas size
  skin/                face, ears, neck, shoulders (greyscale → tinted with a skin tone)
  clothes/             top (greyscale → tinted with the analyst's team colour)
  eyes/  nose/  mouth/
  hair/                greyscale → tinted with a hair colour; name_back.png goes behind
  accessories/         glasses, headsets, hats (put _fixed in a name to keep its colours)
  overlays/tired.png   drawn on analysts with high fatigue
```

Every piece shares one canvas (128×128 by default) and is drawn in place, so stacking
them lines everything up. Drop new PNGs into a folder and they join the random pool.
**Avatars** on the title screen shows random combinations, a face in every team colour
and the tired overlay. `assets/avatars/README.txt` has the details (including how to
use whole pre-drawn faces instead of layers).

**Item icons** (`assets/items/<tools|supplies|training>/<item id>.png`): shown in the
tool row while you play, on supply buttons, in the shop and on the centre's unlock track.
Any square size works. Items without a PNG get a generated badge.

**Volcano webcams** (`assets/webcams/*.png`): the first six (by file name) fill the
webcam screen; the label comes from the file name (`3_ngauruhoe.png` → Ngauruhoe). Draw
them in daylight; the game darkens them at night.

**Fonts** (`assets/fonts/`): set `display.font` in `config.json` to a .ttf/.otf there
(`font_semibold` / `font_bold` for separate weight files, `font_scale`, `fake_bold`).
If the font has no space character the game spaces words itself, and any character the
font can't draw (dashes, arrows, ×, ½, macrons...) is swapped for a plain stand-in
(`-`, `->`, `x`, `1/2`, `o`); the list is `GLYPH_FALLBACKS` in `ui/theme.py`.

The shipped art is all placeholder, drawn by `tools/make_placeholder_avatars.py`,
`make_placeholder_items.py` and `make_placeholder_webcams.py` (`--force` redraws).

## Project layout

```
main.py                 entry point
game/                   simulation (no pygame): runs headless
  engine.py             one week: time, shifts, tasks, auto-assign, DART, fatigue, trust, events
  run.py                new run, analysts, team rotation, week start/finish, payout
  run_builder.py        pre-picks every day of the run from the catalogue
  catalog.py, synth.py  catalogue loading / synthetic catalogue
  profile.py            centre profiles: XP, levels, unlocks, run history
  dart.py               which DART buoys a quake sets off
  tz.py                 NZ time and UTC, with daylight saving (no time zone database needed)
  avatars.py            which avatar piece each analyst gets (file names only)
  tags.py               counting tags and scaling per_tag modifiers
  forecast.py           what kind of day a catalogue day is (large quake, swarm...), day alerts
  tasks.py, effects.py, modifiers.py, shop.py, bot.py, models.py, save.py
ui/                     pygame front end
  avatars.py, icons.py, webcams.py   load and cache the art
  richtext.py           automatic colour coding of names in any text
  scenes/               title, slots, centre, planning (roster/shop/team), shift (+ wall
                        clocks and screens, map, modals), summary, boss_reward, options,
                        gallery
assets/                 avatars, item icons, webcams, fonts (Inter, SIL Open Font License)
data/                   all content and balance (JSON)
tools/
  simulate.py           headless bot playthroughs for balancing
  check_catalog.py      what the game sees in your catalogue
  make_placeholder_*.py redraw the placeholder art
  ui_smoke.py, ui_scenarios.py   headless screenshot tests of every screen
```

## Balancing with the bot

```
python tools/simulate.py --runs 10                         # attentive, triaging bot
python tools/simulate.py --runs 10 --attention 30 --per-look 3
python tools/simulate.py --runs 10 --no-triage             # first-come-first-served
python tools/simulate.py --runs 10 --auto balanced         # the game's auto-assign plays instead
python tools/simulate.py --length long
```

It prints a weekly table: trust, budget, events, SOPs, on-time %, errors, overdue,
sick calls, burnouts, utilisation, fatigue and the trust breakdown. With the shipped
numbers on the synthetic catalogue: a quick triaging bot survives nearly every standard
run, slower ones survive most with lower trust, auto-assign on its own survives most runs
with lower trust, and first-come-first-served play loses. The simulator unlocks every
item. Real catalogue days may feel different, so re-check after dropping in
`archive.csv`.

## Known gaps / next ideas

* No sound yet.
* Hand-drawn, simplified coastline in `data/nz_coast.json` (swap in a proper one).
* DART buoy positions are approximate.
* Saves happen at the start of each week only (pickle; a big code change can invalidate
  an old save).
* Analysts are fictional and randomly generated.

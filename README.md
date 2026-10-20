# peon-ping setup: voice lines for Claude Code and Codex

A ready-to-use configuration for [peon-ping](https://github.com/PeonPing/peon-ping),
the Claude Code / Codex hook that plays a game or TV voice line when an agent
finishes a task or needs your input. One clone has everything: 51 sound packs
(loudness-normalised), the config with its weighted pack rotation, and an
installer.

## Quick start

```bash
git clone https://github.com/Hajadlo/peon-ping-setup.git
cd peon-ping-setup
./install.sh
```

Run it on the machine where Claude Code / Codex run; sounds play there. Linux
or macOS, with `bash`, `curl`, `git` and Python 3.11+.

`./install.sh` installs peon-ping with its upstream installer if it is missing
(Homebrew when `brew` exists), copies the packs, merges the config, and makes
sure Claude Code hooks run Peon (it checks Codex too when `~/.codex` exists).
Anything it replaces is backed up first; `./install.sh --dry-run` shows the
plan without changing anything. Then test it: `peon preview task.complete`, or
start a new session and give the agent a small task.

`./install.sh --help` lists the single steps (`--packs`, `--config`, `--hooks`),
`--refresh-registry` (re-download registry packs from their authors) and
`--normalize` (even out loudness again afterwards; needs ffmpeg).
[SETUP.md](SETUP.md) is the same setup as a runbook for a coding agent.

## What you get

### Config choices

`config.json` is the live config. The settings worth knowing:

- **Only two categories play**: `task.complete` and `input.required`. Session
  start, acknowledgements, errors, resource limits and "spam" lines are off, so
  a sound always means "come and look".
- **`pack_rotation_mode: "shuffle"`** picks a random pack for *every* sound.
  `pack_rotation` deliberately lists packs several times: the count is the
  pack's weight (the *Weight* column below; 193 entries, 49 packs).
  `peon` and `peasant` are installed but not in the rotation (their Czech
  dubs are); `default_pack` is `originalwar-peons`.
- **`volume: 0.5`** with every clip normalised to at most -23 LUFS integrated
  and -6 dBTP true peak, so packs sit at a similar level and nothing blasts.
- **`desktop_notifications: false`**: the IDE already shows a popup; Peon only
  plays sound. Set it to `true` for Peon's own popups.
- **`suppress_subagent_complete: true`**: subagents finishing do not play "done".
- `annoyed_threshold` 3 within `annoyed_window_seconds` 10, and
  `session_start_cooldown_seconds` 30, are the upstream defaults.
- `use_sound_effects_device: true` (macOS: plays on the system sound-effects
  output), `debug: true` with 7-day log retention (`peon logs`), trainer off,
  no `path_rules` or `project_name_map` (add your own per-project packs there).

### Packs

Pack audio is **not** covered by this repo's MIT licence: each pack keeps the
licence stated in its manifest and below. The 39 registry packs come from the
[OpenPeon registry](https://peonping.github.io/registry/) and their authors'
repositories; they are included as installed so one clone is a complete setup,
and `./install.sh --refresh-registry` re-downloads them from the authors instead.
All clips in this repo have been loudness-normalised (attenuated only), so they
differ byte-wise from the originals.

Local change to a registry pack: `seinfeld_kramer` also plays its existing
`giddy-up.wav` for `task.complete` (upstream uses it for `session.start` only).
The upstream `r2d2` manifest references `sounds/Error3.mp3`, which its release
does not ship; Peon skips it.

The `tv-*` packs were made for this setup from short excerpts of TV shows. The
shows and recordings belong to their rightsholders; the clips are used for
personal notification purposes. Each `tv-*` pack's `ADDITIONS-*.md` and README
lists where its later clips came from. `originalwar-peons` is published
separately at <https://github.com/Hajadlo/originalwar-peons>.

#### Warcraft, StarCraft and Original War

| Pack | Author | Source | Licence | Clips | Weight |
| --- | --- | --- | --- | --- | --- |
| `peon` — Orc Peon | [tonyyont](https://github.com/tonyyont) | [PeonPing/og-packs](https://github.com/PeonPing/og-packs/tree/v1.0.0/peon) @ `v1.0.0` | CC-BY-NC-4.0 | 18 | 0 |
| `peasant` — Human Peasant | [thomasKn](https://github.com/thomasKn) | [PeonPing/og-packs](https://github.com/PeonPing/og-packs/tree/v1.0.0/peasant) @ `v1.0.0` | CC-BY-NC-4.0 | 18 | 0 |
| `peon_cz` — Orčí peón (CZ) | [vojtabiberle](https://github.com/vojtabiberle) | [PeonPing/og-packs](https://github.com/PeonPing/og-packs/tree/v1.0.0/peon_cz) @ `v1.0.0` | CC-BY-NC-4.0 | 18 | 7 |
| `peasant_cz` — Lidský rolník (CZ) | [vojtabiberle](https://github.com/vojtabiberle) | [PeonPing/og-packs](https://github.com/PeonPing/og-packs/tree/v1.0.0/peasant_cz) @ `v1.0.0` | CC-BY-NC-4.0 | 18 | 4 |
| `warcraft3-mix` — Warcraft III Mix CZ | [SgtMarmite](https://github.com/SgtMarmite) | [SgtMarmite/peonping-warcraft3-mix](https://github.com/SgtMarmite/peonping-warcraft3-mix) @ `v1.0.0` | CC-BY-NC-4.0 | 225 | 7 |
| `originalwar-peons` — Original War Peons | [Hajadlo](https://github.com/Hajadlo) | [Hajadlo/originalwar-peons](https://github.com/Hajadlo/originalwar-peons) | CC-BY-NC-4.0 | 76 | 11 |
| `sc_battlecruiser` — StarCraft Battlecruiser | [garysheng](https://github.com/garysheng) | [PeonPing/og-packs](https://github.com/PeonPing/og-packs/tree/v1.0.0/sc_battlecruiser) @ `v1.0.0` | CC-BY-NC-4.0 | 12 | 3 |
| `sc_firebat` — StarCraft Firebat | [kschmidtjr1](https://github.com/kschmidtjr1) | [PeonPing/og-packs](https://github.com/PeonPing/og-packs/tree/v1.3.0/sc_firebat) @ `v1.3.0` | CC-BY-NC-4.0 | 17 | 2 |
| `sc_kerrigan` — Sarah Kerrigan (StarCraft) | [garysheng](https://github.com/garysheng) | [PeonPing/og-packs](https://github.com/PeonPing/og-packs/tree/v1.0.0/sc_kerrigan) @ `v1.0.0` | CC-BY-NC-4.0 | 14 | 2 |
| `sc_marine` — StarCraft Marine | [harrymunro](https://github.com/harrymunro) | [PeonPing/og-packs](https://github.com/PeonPing/og-packs/tree/v1.2.0/sc_marine) @ `v1.2.0` | CC-BY-NC-4.0 | 16 | 2 |
| `sc_medic` — StarCraft Medic | [kschmidtjr1](https://github.com/kschmidtjr1) | [PeonPing/og-packs](https://github.com/PeonPing/og-packs/tree/v1.3.0/sc_medic) @ `v1.3.0` | CC-BY-NC-4.0 | 16 | 2 |
| `sc_scv` — StarCraft SCV | [harrymunro](https://github.com/harrymunro) | [PeonPing/og-packs](https://github.com/PeonPing/og-packs/tree/v1.2.0/sc_scv) @ `v1.2.0` | CC-BY-NC-4.0 | 19 | 2 |
| `sc_tank` — StarCraft Siege Tank | [kschmidtjr1](https://github.com/kschmidtjr1) | [PeonPing/og-packs](https://github.com/PeonPing/og-packs/tree/v1.3.0/sc_tank) @ `v1.3.0` | CC-BY-NC-4.0 | 14 | 3 |

#### Dota 2, Deadlock and other games

| Pack | Author | Source | Licence | Clips | Weight |
| --- | --- | --- | --- | --- | --- |
| `dota2-sounds` — Dota 2 Sounds | [darkocejkov](https://github.com/darkocejkov) | [darkocejkov/peonping-dota2-sounds](https://github.com/darkocejkov/peonping-dota2-sounds) @ `v1.0.0` | CC-BY-NC-4.0 | 28 | 5 |
| `dota2_axe` — Axe (Dota 2) | [x-n2o](https://github.com/x-n2o) | [PeonPing/og-packs](https://github.com/PeonPing/og-packs/tree/v1.3.0/dota2_axe) @ `v1.3.0` | CC-BY-NC-4.0 | 20 | 4 |
| `dota2_ember_spirit` — Ember Spirit (Dota 2) | [kmelkon](https://github.com/kmelkon) | [kmelkon/openpeon-dota2](https://github.com/kmelkon/openpeon-dota2/tree/main/dota2_ember_spirit) @ `main` | CC-BY-NC-4.0 | 26 | 5 |
| `dota2_invoker` — Invoker (Dota 2) | [bwarren2](https://github.com/bwarren2) | [bwarren2/peonpack-invoker](https://github.com/bwarren2/peonpack-invoker) @ `v1.0.0` | CC-BY-NC-4.0 | 24 | 3 |
| `dota2_phantom_lancer` — Phantom Lancer (Dota 2) | [kmelkon](https://github.com/kmelkon) | [kmelkon/openpeon-dota2](https://github.com/kmelkon/openpeon-dota2/tree/v1.0.0/dota2_phantom_lancer) @ `v1.0.0` | CC-BY-NC-4.0 | 26 | 5 |
| `dota2_witch_doctor` — Witch Doctor (Dota 2) | [kmelkon](https://github.com/kmelkon) | [kmelkon/openpeon-dota2](https://github.com/kmelkon/openpeon-dota2/tree/main/dota2_witch_doctor) @ `main` | CC-BY-NC-4.0 | 26 | 6 |
| `dota2_zeus` — Zeus (Dota 2) | [kmelkon](https://github.com/kmelkon) | [kmelkon/openpeon-dota2](https://github.com/kmelkon/openpeon-dota2/tree/main/dota2_zeus) @ `main` | CC-BY-NC-4.0 | 34 | 7 |
| `storm-spirit` — Storm Spirit (Dota 2) | [m1z23r](https://github.com/m1z23r) | [m1z23r/openpeon-storm](https://github.com/m1z23r/openpeon-storm) @ `v1.0.0` | fair-use | 34 | 5 |
| `deadlock_dynamo` — Dynamo (Deadlock) | [mwaterman29](https://github.com/mwaterman29) | [mwaterman29/openpeon-deadlock-dynamo](https://github.com/mwaterman29/openpeon-deadlock-dynamo) @ `v1.0.0` | CC-BY-NC-4.0 | 48 | 10 |
| `d2_deckard_cain` — Deckard Cain (Diablo 2) | [rootbarb](https://github.com/rootbarb) | [rootbarb/openpeon-d2-deckard-cain](https://github.com/rootbarb/openpeon-d2-deckard-cain) @ `v1.0.0` | CC-BY-NC-4.0 | 14 | 3 |
| `counterstrike` — Counter-Strike | [colbyfayock](https://github.com/colbyfayock) | [colbyfayock/openpeon-counterstrike](https://github.com/colbyfayock/openpeon-counterstrike) @ `v1.0.2` | CC-BY-NC-4.0 | 15 | 2 |
| `abes-oddysee-abe` — Abe's Oddysee - Abe | [Ioseb Laghidze](https://github.com/onebadninja) | [OneBadNinja/openpeon-abes-oddyssey-abe](https://github.com/OneBadNinja/openpeon-abes-oddyssey-abe) @ `v1.0.0` | CC-BY-NC-4.0 | 11 | 2 |
| `glados` — GLaDOS (Portal) | [DoubleGremlin181](https://github.com/DoubleGremlin181) | [PeonPing/og-packs](https://github.com/PeonPing/og-packs/tree/v1.0.0/glados) @ `v1.0.0` | CC-BY-NC-4.0 | 23 | 3 |

#### Film, TV and sci-fi (community packs)

| Pack | Author | Source | Licence | Clips | Weight |
| --- | --- | --- | --- | --- | --- |
| `futurama_bender` — Bender (Futurama) | [ravenrs](https://github.com/ravenrs) | [ravenrs/peon-ping-futurama-bender-](https://github.com/ravenrs/peon-ping-futurama-bender-) @ `v1.0.0` | CC-BY-NC-4.0 | 18 | 4 |
| `gilfoyle` — Gilfoyle | [mpospirit](https://github.com/mpospirit) | [mpospirit/openpeon-gilfoyle](https://github.com/mpospirit/openpeon-gilfoyle) @ `v1.0.0` | CC-BY-NC-4.0 | 40 | 7 |
| `mr_meeseeks` — Mr. Meeseeks | [kasperhendriks](https://github.com/kasperhendriks) | [kasperhendriks/openpeon-mrmeeseeks](https://github.com/kasperhendriks/openpeon-mrmeeseeks) @ `v1.0.0` | CC-BY-NC-4.0 | 30 | 7 |
| `omar` — Omar Little (The Wire) | [Taylan Aydinli](https://github.com/taylan) | [taylan/openpeon-omar](https://github.com/taylan/openpeon-omar) @ `v1.1.1` | CC-BY-NC-4.0 | 32 | 7 |
| `sopranos` — Tony Soprano | [voider1](https://github.com/voider1) | [PeonPing/og-packs](https://github.com/PeonPing/og-packs/tree/v1.0.0/sopranos) @ `v1.0.0` | CC-BY-NC-4.0 | 30 | 4 |
| `pulp_fiction` — Pulp Fiction | [bdrang](https://github.com/bdrang) | [PeonPing/og-packs](https://github.com/PeonPing/og-packs/tree/c795d88964369d3c60a171a2d6a03cc28d4c0fd9/pulp_fiction) @ `c795d88964369d3c60a171a2d6a03cc28d4c0fd9` | fair-use | 24 | 4 |
| `seinfeld_kramer` — Kramer (Seinfeld) | [bdrang](https://github.com/BaraqD) | [BaraqD/pack-seinfeld_kramer](https://github.com/BaraqD/pack-seinfeld_kramer) @ `v1.0.0` | fair-use | 18 | 3 |
| `tywin-lannister` — Tywin Lannister | [dmltdev](https://github.com/dmltdev) | [dmltdev/openpeon-tywin-lannister](https://github.com/dmltdev/openpeon-tywin-lannister) @ `v1.1.1` | CC-BY-NC-4.0 | 32 | 6 |
| `st_worf` — Worf (Star Trek) | [OmegaZero](https://github.com/OmegaZero) | [OmegaZero/openpeon-worf](https://github.com/OmegaZero/openpeon-worf) @ `v1.0.2` | MIT | 12 | 1 |
| `lcars` — LCARS (Star Trek TNG) | [heidilux](https://github.com/heidilux) | [heidilux/openpeon-lcars](https://github.com/heidilux/openpeon-lcars) @ `v1.0.0` | personal-use | 50 | 7 |
| `r2d2` — R2D2 Pack | [A3mercury](https://github.com/A3mercury) | [A3mercury/openpeon-r2d2](https://github.com/A3mercury/openpeon-r2d2) @ `v1.0.0` | CC-BY-NC-4.0 | 13 | 3 |
| `djt` — Donald J. Trump | [bdrang](https://github.com/BaraqD) | [BaraqD/pack-djt](https://github.com/BaraqD/pack-djt) @ `v1.0.0` | fair-use | 33 | 7 |

#### Czech

| Pack | Author | Source | Licence | Clips | Weight |
| --- | --- | --- | --- | --- | --- |
| `jara-cimrman` — Jára Cimrman | [Majkle](https://github.com/Majkle) | [Majkle/openpeon-jara-cimrman](https://github.com/Majkle/openpeon-jara-cimrman) @ `v1.0.0` | CC-BY-NC-4.0 | 64 | 2 |
| `milujipraci` — Miluji Práci | [František Záhora](https://github.com/arguit) | [arguit/openpeon-milujipraci](https://github.com/arguit/openpeon-milujipraci) @ `v1.0.1` | CC-BY-NC-4.0 | 30 | 7 |

#### TV excerpts made for this setup (`tv-*`)

| Pack | Author | Source | Licence | Clips | Weight |
| --- | --- | --- | --- | --- | --- |
| `tv-breaking-bad` — TV — Breaking Bad | Hajadlo | this repo | fair-use | 5 | 2 |
| `tv-brooklyn-nine-nine` — TV — Brooklyn Nine-Nine | Hajadlo | this repo | fair-use | 3 | 1 |
| `tv-curb-your-enthusiasm` — TV — Curb Your Enthusiasm | Hajadlo | this repo | fair-use | 1 | 2 |
| `tv-house-m-d` — TV — House M.D. | Hajadlo | this repo | fair-use | 2 | 1 |
| `tv-its-always-sunny-in-philadelphia` — TV — It's Always Sunny in Philadelphia | Hajadlo | this repo | fair-use | 6 | 2 |
| `tv-mad-men` — TV — Mad Men | Hajadlo | this repo | fair-use | 4 | 2 |
| `tv-narcos` — TV — Narcos | Hajadlo | this repo | fair-use | 1 | 1 |
| `tv-parks-and-recreation` — TV — Parks and Recreation | Hajadlo | this repo | fair-use | 6 | 2 |
| `tv-red-dwarf` — TV — Red Dwarf | Hajadlo | this repo | fair-use | 2 | 2 |
| `tv-seinfeld` — TV — Seinfeld | Hajadlo | this repo | fair-use | 5 | 1 |
| `tv-the-office-us` — TV — The Office (US) | Hajadlo | this repo | fair-use | 9 | 3 |

`warcraft3-czech` ([gizmax/claude-code-wc3-sounds](https://github.com/gizmax/claude-code-wc3-sounds))
was installed with no sound files and is not part of this repo; install it with
`peon packs install warcraft3-czech` if you want it.

## Advanced: agents on another machine, T3 Code

Most people need none of this. Two optional extras, each with its own README:

- [`extras/remote/`](extras/remote/README.md): agents run on a headless server,
  sounds play on your desktop through a peon relay and an SSH reverse tunnel
  (optionally fanned out to several machines).
- [`extras/t3-code/`](extras/t3-code/README.md): for
  [T3 Code](https://github.com/pingdotgg/t3code), sound only when the main
  thread finishes or needs input, not for every child agent.

## Repo layout

| Path | What |
| --- | --- |
| `install.sh` | The installer (`--help` for single steps) |
| `config.json` | The peon-ping config: categories, volume, cooldowns, weighted rotation |
| `packs/` | 51 OpenPeon packs with audio, manifests and their own README/LICENSE files, ~132 MiB |
| `pack-sources.json` | Author, source repo, ref, licence for every pack |
| `tools/wire_hooks.py` | Adds the hook command to Claude Code settings; prints the Codex block |
| `tools/normalize_peon_audio.py` | Loudness normaliser (-23 LUFS, -6 dBTP ceiling, attenuation only) |
| `extras/` | Remote relay and T3 Code watcher (above) |
| `check.sh` | Shell syntax, optional shellcheck, all unit tests (no audio is played) |

## Credits

- [PeonPing/peon-ping](https://github.com/PeonPing/peon-ping) for the runtime,
  relay and the [OpenPeon registry](https://github.com/PeonPing/registry).
- Every pack author listed above. Game and show voice lines belong to their
  respective publishers and rightsholders.

## Licence

Scripts, config and docs: [MIT](LICENSE). Pack audio and pack manifests: the
licence of each pack (see the table and each pack's files); not MIT.

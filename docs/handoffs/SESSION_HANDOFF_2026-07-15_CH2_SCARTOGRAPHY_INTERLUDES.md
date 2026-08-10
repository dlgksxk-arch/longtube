# Session Handoff 2026-07-15 - CH2 Scartography Interludes

## Completed Work

- Channel: CH2
- YouTube brand: `Scartography` (`@scartography`)
- Template project: `e6619f7e` (`딸깍폼-Scartography`)
- Current content: English European history documentaries
- CH2 queue at verification: 34 pending episodes, EP001-EP034

The retired `Jerry's Archaeo` opening, intermission, and ending were replaced with new Scartography-branded clips. The approved visual system follows the actual channel avatar: black stone, antique gold, dark crimson, a relief map of Europe, compass, classical column, and crown.

## Registered Assets

Project template assets:

- `C:\Users\Ai_M9\Desktop\longsult\_system\projects\e6619f7e\interlude\opening.mp4`
- `C:\Users\Ai_M9\Desktop\longsult\_system\projects\e6619f7e\interlude\intermission.mp4`
- `C:\Users\Ai_M9\Desktop\longsult\_system\projects\e6619f7e\interlude\ending.mp4`

CH2 channel fallback assets:

- `C:\Users\Ai_M9\Desktop\longsult\channels\CH2\interlude\opening.mp4`
- `C:\Users\Ai_M9\Desktop\longsult\channels\CH2\interlude\intermission.mp4`
- `C:\Users\Ai_M9\Desktop\longsult\channels\CH2\interlude\ending.mp4`

All three are 5.0 seconds, 1920x1080, 30 fps, H.264 video, AAC stereo audio at 48 kHz. Project and CH2 fallback copies have matching SHA-256 hashes for each kind.

## Text

- Opening: `SCARTOGRAPHY` / `EUROPEAN HISTORY DOCUMENTARIES`
- Intermission: `SCARTOGRAPHY` / `MYTHS · EMPIRES · BORDERS`
- Ending: `SCARTOGRAPHY` / `@SCARTOGRAPHY`

The `T` in `SCARTOGRAPHY` is dark crimson, matching the verified channel avatar. Text is rendered deterministically in post-processing, not generated inside the source image.

## Registration State

`projects.config.interlude` for `e6619f7e` now points to:

- `interlude/opening.mp4`
- `interlude/intermission.mp4`
- `interlude/ending.mp4`

Each entry has `source: generated-brand`, exact file size, 5.0-second duration, and a generation timestamp. Existing insertion intervals were preserved: `intermission_every_sec: 180` and `intermission_every_cuts: 180`.

## Generation Logic

- `backend/scripts/ch2_build_brand_interludes.py`

The script generates overlays and original synthesized sound design, renders staged videos, performs full decode and media-contract checks, backs up previous assets and the SQLite database, atomically installs the files, mirrors them to the CH2 fallback directory, and updates the template config.

The runtime `interlude` directory contains only the three MP4 files so template cloning does not copy backups or source images. Rebuild sources are stored separately under `brand_sources/interlude`, and backups are stored under `interlude_backups`.

## Backups

- Retired Jerry's Archaeo assets: `C:\Users\Ai_M9\Desktop\longsult\_system\projects\e6619f7e\interlude_backups\20260715_200113`
- Pre-final-layout Scartography assets: `C:\Users\Ai_M9\Desktop\longsult\_system\projects\e6619f7e\interlude_backups\20260715_200350`
- Final database backup: `C:\Users\Ai_M9\Desktop\longtube\data\longtube.before_ch2_interludes_20260715_200350.db`

## Verification

- Dry-run render and decode: passed for all three clips.
- Visual frame inspection: passed for all three clips.
- Final decode and media contract: passed.
- Audio mean volume: approximately -20.7 to -20.8 dB.
- Audio maximum peak: -3.4 to -4.2 dB.
- DB registration: verified directly after commit.
- Live API endpoint was reachable but returned the expected login-required response without an authenticated UI session.

No CH2 episode was started, scheduled, or uploaded by this work.

# EN_BTS Discovery Gate v1.1 — official data collection only

**State:** offline tests PASS; live API **BLOCKED until the user's API key is configured**. Does NOT select a topic, score outliers, or call GREENLIGHT. No paid model, no image/video generation, no pip installs.

## Installation footprint

Python 3.11 standard library only. No external packages. Source code and fixture < 50 KB; run artifacts depend on candidate counts, normally < 2 MB. GitHub-hosted Action uses the existing runner image. No Mac/Windows local install necessary.

## Authentication (user action)

1. Open [Google Cloud Console](https://console.cloud.google.com/) and create or select a project. Enable [YouTube Data API v3](https://console.cloud.google.com/apis/library/youtube.googleapis.com).
2. Go to [Credentials](https://console.cloud.google.com/apis/credentials), create an **API key** for this project. Add **API restriction = YouTube Data API v3**. Keep it private; GitHub-hosted runners have changing egress IPs, so do not set a single-IP allowlist that will reject them. Consider quotas & usage alerts and rotate the key if it is exposed.
3. In GitHub `Kapka87/longform-factory-updates` go to **Settings → Secrets and variables → Actions → New repository secret**. Name exactly `YOUTUBE_API_KEY` and paste the key **there**. Do not paste it in ChatGPT or the code repository.
4. When the new workflow is merged to `main`, go to **Actions → EN BTS Discovery Gate - manual official collection → Run workflow → main**.
5. After the run shows ✅, click the run → **Artifacts** → download `en-bts-discovery-v1-…`; inspect `report.md`, `candidates.csv`, `candidates.json`. The artifact expires after 7 days. Share **report and candidate file** for D2 review, not the key.

## Execution contract

- 26 `search.list` queries across broad, YouTube categories and format phrases, interleaved (no narrow topic prefilter). Official public metadata cross-checked via `videos.list` & `channels.list`. This is a best-effort search sample, **not an exhaustive chart**.
- Last 90 days; actual duration ≥480 seconds; subscriber count ≤10,000; each small channel max 3 entries; no duplicate video IDs; missing language explicitly `UNVERIFIED` rather than assumed English.
- Raw comparable view counts from recent public uploads, unadjusted for video age; **not** an independently approved outlier ratio. Metadata cannot confirm video content, audio language, rights, viewer retention, CTR, or monetization.
- No custom scores, no production go decisions, no data committed to repo. Stop on 401/403/429 and report safe status without printing credentials.
- D0/D1 input only: existing D0→D1→D2 and 100-point Hard Kill GREENLIGHT authority remain unchanged.
- Scheduled weekly runs **disabled** until first live run and QC. Existing Factory release workflows and feed files untouched.

## Local offline tests

```sh
cd tools/discovery_gate_v1
python -m unittest discover -s tests -v
python discovery_gate.py --fixture tests/sample_fixture.json --date 2026-10-17T00:00:00Z --out demo-output
```

## Live result QC criteria

- Run `LIVE_API`, not `OFFLINE_FIXTURE`.
- `small_channel_candidates > 0`, enough distinct channels for meaningful exploration (recommended ≥10, not a hard PASS until measured).
- Confirm a random sample of ≥5 video URLs, published date, duration, subscriber count and view counts against the current official API/YouTube interface. Disagreement => HOLD.
- Ensure no invented outlier multiplier, CTR or retention. Any unverified language flagged.
- After successful run: consider separate repository, then optional schedule/weekly summary (explicit user approval).

## Why shared repository initially?

The GitHub integration can write to the existing `Kapka87/longform-factory-updates` repository but cannot create a new repository or manage Actions secrets. This collector is isolated under `tools/discovery_gate_v1/` and a separate, **manual-only** workflow. A PR/branch keeps current release paths untouched. No production updater step is modified. Moving to a dedicated repo can be done later without altering this program.

### v1.1.1 metadata-only QC patch (2026-10-17)

The first live run confirmed 36 candidates across 35 channels, but metadata declared `en` for some videos whose titles include non-Latin scripts and surfaced film-based titles. The collector now emits **review-only** flags `TITLE_SCRIPT_REVIEW_ONLY` and `THIRD_PARTY_MEDIA_RIGHTS_REVIEW_ONLY` from titles. These are not proof that the audio is non-English or that copyrights were infringed. Audio, visuals, rights, authenticity, and Outlier validation still require D2 manual checks. The original first-run artifact remains unchanged.
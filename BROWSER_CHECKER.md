# Follower-only browser checker (v17)

Replaces curl profile/embed requests with headless Chromium. No windows on
employee computers, no TikTok login, no CAPTCHA solver. A challenge that does
not resolve through normal page execution remains an error, never zero or DIE.
Only exact followers for the correct username count as success. No embed or
video-list API calls are made by the checker. Profile scripts may make their
own requests; image/media/font downloads are blocked. Successful results have
empty videos and zero sample views, replacing previous samples as before.

## Local Windows first

Activate the same virtual environment used to start the server:

```powershell
python -m pip install -r requirements.txt
python -m playwright install chromium
python server.py
```

Chromium downloads once. Test one known account, then five, then fifty.
Compare current followers against TikTok; old database counts after an error
do not prove success. Default three concurrent tabs, maximum five, configured
by TIKTOK_BROWSER_TABS. One browser is reused; each account has an isolated,
temporary context closed after use. Existing timeout includes waiting for a
tab, first browser launch and hydration. No additional video checks or delays.

## Render only after local verification

Start Command: `python server.py`. Build Command: `bash render-build.sh`.
Set this environment variable so build and runtime find the same browser:

```text
PLAYWRIGHT_BROWSERS_PATH=/opt/render/project/src/.cache/ms-playwright
TIKTOK_BROWSER_TABS=3
```

The build script now installs Chromium. If launch reports missing Linux system
libraries, use a Docker deployment installing them during image build with
`python -m playwright install --with-deps chromium`. Do not install system
libraries on every startup. Native Render compatibility and free-tier RAM are
not guaranteed. Measure memory/latency before production. Headless browsers
can be heavier/slower than curl and can still encounter TikTok verification.

Tests use browser doubles for lifecycle, hydration, exact counts, deadlines
and concurrency; passing tests do not prove real TikTok success rates.

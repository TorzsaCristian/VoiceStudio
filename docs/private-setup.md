# Private and secure setup

VoiceStudio runs speech models on your own machine. Nothing is uploaded unless
you choose a feature that needs the network, and analytics stay off unless you
say **Yes** at the first-run prompt. This page shows how to install from source
with pinned dependencies, keep every default local, and limit what else on the
machine can reach the app. The same steps work on macOS, Windows and Linux;
shell examples use POSIX syntax (on Windows, set variables with PowerShell
`$env:NAME = "value"` for one session).

## Install from source with locked dependencies

```bash
git clone https://github.com/debpalash/VoiceStudio.git
cd VoiceStudio
bun install --frozen-lockfile   # fails instead of re-resolving bun.lock
uv sync --locked                # fails instead of re-resolving uv.lock
bun run --cwd electron dev      # skips the root `predev: bun install`
```

- `bun.lock` and `uv.lock` pin every package by hash. The two flags make the
  install refuse to run if either lock is out of date.
- Only `electron`, `esbuild`, `electron-builder` and `app-builder-bin` may run
  install scripts (`trustedDependencies`); Bun blocks every other package's.
- From source, the backend listens on `127.0.0.1` only. The desktop auto-update
  check and the managed-runtime installer run in packaged builds only.
- `scripts/setup.py` (run by `bun run setup:api`) does nothing on macOS, so
  `uv sync --locked` alone is enough there.

## Keep defaults local

Set these before launching. Each one closes a path that could otherwise reach
the network without an explicit click:

| Variable | Effect |
|---|---|
| `OMNIVOICE_ANALYTICS_DISABLED=1` | Turns off the backend analytics client. Also answer **No** at the consent prompt, which turns off the interface's analytics. |
| `HF_HUB_DISABLE_TELEMETRY=1` | Turns off Hugging Face library telemetry. |
| `OMNIVOICE_HF_ENDPOINT_MODE=manual` | Stops setup and diagnostics from probing `huggingface.co` and `hf-mirror.com` to pick the faster one. |
| `FFMPEG_PATH`, `FFPROBE_PATH` | Point at your own ffmpeg and ffprobe so first-run setup never downloads a copy. |
| `TRANSLATE_PROVIDER=argos` | API or MCP translation requests that name no provider use local Argos instead of Google. |
| `LLM_DEFAULT_PROVIDER=ollama` (or `lmstudio`) | AI text features use a local model. |
| Unset `OPENAI_API_KEY`, `GROQ_API_KEY`, `OPENROUTER_API_KEY`, `HF_TOKEN`, … | A cloud key in the environment makes that provider the default for AI text features. |
| `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1` | Once you have downloaded the models you use, blocks all Hugging Face network access. |

Settings → Privacy shows analytics consent, the watermark and history retention
(see [Electron privacy](electron-privacy.md)). The invisible AudioSeal watermark
is on by default; your first generation downloads its checkpoint from Hugging
Face.

## Features that use the network

These all stay off until you use them:

- **Model downloads** from Hugging Face (Model Store, or the first use of an
  engine).
- **Optional engines** (IndexTTS, CosyVoice, MOSS, dots.tts, Confucius4) clone
  upstream repositories at pinned commits and run their install code in a
  separate environment. MOSS-TTS-Nano and MOSS v1.5 load models with
  `trust_remote_code`; pin `OMNIVOICE_MOSS_TTS_V15_REVISION` if you install them.
  SoniTranslate installs its latest upstream code, unpinned.
- **Remote ASR, cloud LLM and online translators** (Google, DeepL, Microsoft,
  MyMemory) send audio or text to that provider.
- **Dubbing from a URL** or YouTube search uses yt-dlp. **Update yt-dlp** installs
  the latest release from PyPI.
- **Community voices** tab, **portrait search** (sends the voice name to Google
  and Openverse), **voice preview gallery**, **Pro license** activation.
- **LAN share**, **Tailscale share**, **remote workers** and **phone calls**
  open or use network listeners.
- **Report a bug** opens a prefilled GitHub issue in your browser; nothing is
  sent automatically.

## Limit who can reach the backend

- The backend trusts requests from the same machine without a credential. It
  refuses browser pages that are not VoiceStudio: a request must use a loopback
  `Host`, and its `Origin` must be the app's own (see
  [API authentication](api-auth.md)). Other
  programs running as your user can still call it, so quit VoiceStudio when you
  are not using it.
- `bun run dev:web` binds `0.0.0.0:3900`, so other devices on your network can
  reach it. Prefer `bun run --cwd electron dev`, or set `OMNIVOICE_API_KEY` to a
  long random value.
- In Docker, publish the port on loopback only (`-p 127.0.0.1:3900:3900`) and
  set `OMNIVOICE_API_KEY`.
- Keep Settings → Sharing & Remote Access off unless you are using it.
- A system firewall that blocks incoming connections is a useful second layer.
- Grant microphone access, and Accessibility access on macOS (needed only for
  typing dictation into other apps), only when you use those features. Copy-only
  dictation output needs no Accessibility permission.

## Where your data lives

Voices, outputs, dub jobs, the history database and logs live in the backend
data folder: `~/Library/Application Support/OmniVoice` on macOS, or the folder
set by `OMNIVOICE_DATA_DIR`. Models are cached in `~/.cache/huggingface`. Logs
record errors, not the text you synthesize. Use full-disk encryption (FileVault,
BitLocker, LUKS), or point `OMNIVOICE_DATA_DIR` at an encrypted volume.

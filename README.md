# Transcriber

Local transcription of audio and video with speaker separation, per-segment language detection,
translation, a voiceprint gallery, live streaming, burned-in subtitles, an HTTP service and a web
interface. Every building block is a replaceable plug-in. No cloud service is involved; the
machine-learning models run on the GPU of the local host.

- Version: 0.1.0
- Licence: MIT (see `LICENSE`)
- Python: 3.12
- Platform used for the measurements in this file: Linux, NVIDIA RTX 4060 Laptop (8 GB), 31 GB RAM

## Status

All six planned stages are built. Every acceptance criterion from `SPEC.md` maps to a named test
and, where a real run was possible, has been run on real material.

| Stage | Content | Evidence |
|---|---|---|
| P0 | Core, data model, adapter registry, exporters, command line | `EVIDENCE-P0.md` |
| P1 | ASR, diarization, language ID, translation with real models | `EVIDENCE-P1.md` |
| P2 | Voiceprint gallery: enrolment with consent, deletion, locking | `EVIDENCE-P2.md` |
| P3 | Streaming with VAD, microphone, speaker tracking | `EVIDENCE-P3.md` |
| P4 | Burned-in subtitles | `EVIDENCE-P4.md`, `EVIDENCE-YOUTUBE.md` |
| P5 | HTTP service (FastAPI): jobs, export, WebSocket stream | `EVIDENCE-P5.md` |
| P6 | Web interface (Flet) | section "Tests and quality" |

## What it does

One run turns an audio or video file into a transcript:

- segments with start and end time,
- a speaker label per segment (`S1`, `S2`, … ; a name if the gallery recognises the voice),
- the detected language per segment,
- the original text,
- one translation per target language.

The result is available as JSON, SRT, VTT and plain text. It can be returned over HTTP, shown in
the web interface, or burned into the video as subtitles.

## Architecture

The core knows only interfaces. Adapters are chosen by name in a configuration file and are loaded
only when they are needed.

| Port | Purpose | Default adapter |
|---|---|---|
| `AsrEngine` | audio → text with timing | `faster-whisper` (large-v3) |
| `Diarizer` | audio → speaker turns | `pyannote` (speaker-diarization-3.1) |
| `LanguageId` | segment → language | `voxlingua` (ECAPA on VoxLingua107) |
| `Translator` | text → target language | `madlad` (MADLAD-400-3B-MT) |
| `Voiceprint` | segment → embedding, gallery match | `wespeaker` |
| `Vad` | audio → speech spans (streaming) | `energy` (model-free), `silero` |
| `Exporter` | transcript → file | `json`, `srt`, `vtt`, `txt` |
| `VideoRenderer` | video + subtitles → video | `ffmpeg` (libass) |
| `UiApp` | web interface | `flet` |

Rules that hold for the whole code base:

- The core imports no machine-learning code. Models are imported inside the adapter constructor.
- Adapters are created per stage and released afterwards, so Whisper and the 3B translator are
  never resident at the same time on an 8 GB GPU.
- A plug-in from another package registers itself through the Python entry point group
  `transcriber.adapters`; no change to the core is needed.
- Listing adapters or validating a configuration does not touch a GPU.

## Installation

```bash
git clone <this repository>
cd transcriber
uv sync
```

`uv sync` installs the pinned set. The pins are deliberate; reasons are in `LICENSES.md` and
`SPEC.md` section 9:

| Pin | Reason |
|---|---|
| `pyannote.audio<4` | 4.x resolves `speaker-diarization-3.1` to a different, gated model under a different licence |
| `torch<2.9`, `torchaudio<2.9` | pyannote 3.4 needs `torchaudio.AudioMetaData`, removed in 2.9 |
| `av<17` | faster-whisper 1.2.1 passes `metadata_errors`, unknown to PyAV 17 and later |

Two models are gated on Hugging Face. Accept the conditions for
`pyannote/speaker-diarization-3.1` and `pyannote/segmentation-3.0` once, then store the token where
the code reads it:

```bash
install -m 600 /dev/null ~/.cache/huggingface/token
printf '%s' 'hf_...' > ~/.cache/huggingface/token
```

The first run downloads about 10 GB of model weights into `~/.cache/huggingface`.

## Usage

### Command line

```bash
# one file or a whole folder, JSON and SRT
uv run transcriber transcribe recording.mp3 --target de --out out --format json --format srt

# several target languages at once
uv run transcriber transcribe talk.wav --target de --target en --out out

# with a voiceprint gallery: known speakers get their names
uv run transcriber transcribe meeting.m4a --target de --gallery ~/.local/share/transcriber/gallery.db

# gallery administration
uv run transcriber gallery enroll voice.wav --name "Ms Example" --consent
uv run transcriber gallery list
uv run transcriber gallery delete "Ms Example"

# subtitles burned into the video
uv run transcriber render talk.mp4 --transcript out/talk.json --out out/talk.burned.mp4 --subtitle-lang de

# streaming: file or microphone, events while audio arrives
uv run transcriber stream --source recording.wav --out out
uv run transcriber stream --source mic --seconds 30 --out out

# local HTTP service and web interface
uv run transcriber serve --port 8000
uv run transcriber ui --port 8550 --api http://127.0.0.1:8000

# what is available, and under which licence
uv run transcriber adapters
uv run transcriber licenses
```

Exit codes: `0` success, `1` processing error (for example an unreadable file), `2` usage error
(unknown target language, missing consent, unknown adapter). A folder run does not abort on the
first bad file; it reports the failed file and continues.

### Python API

```python
from transcriber import RunConfig, export, run_file

transcript = run_file(
    "recording.mp3",
    config=RunConfig(
        asr="faster-whisper",
        diarizer="pyannote",
        language_id="voxlingua",
        translator="madlad",
        voiceprint=None,
        target_languages=["de"],
    ),
)
export(transcript, "out", formats=("json", "srt"))
```

### HTTP service

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/jobs` | upload a file, returns `job_id` |
| `GET` | `/jobs` | all jobs with state |
| `GET` | `/jobs/{id}` | state: `queued`, `running`, `done`, `failed` plus error text |
| `GET` | `/jobs/{id}/transcript` | transcript as JSON |
| `GET` | `/jobs/{id}/export/{fmt}` | `json`, `srt`, `vtt`, `txt` |
| `DELETE` | `/jobs/{id}` | delete job and its files |
| `WS` | `/stream` | raw float32 audio in (16 kHz, mono), JSON events out |
| `GET` | `/openapi.json` | self-description |

The service binds to `127.0.0.1` unless `--host` says otherwise. It has no authentication and no
TLS: it is meant for the local machine.

### Streaming protocol

The WebSocket endpoint accepts audio as raw little-endian float32 blocks at 16 kHz, mono. Send an
empty message to signal the end of the audio; the server then flushes the last utterance and
closes. Each event carries `index`, `start_s`, `end_s`, `speaker`, `language`, `text`, `is_final`.

## Output format

```json
{
  "schema_version": 1,
  "mode": "file",
  "created_at": "2026-10-31T15:20:00+00:00",
  "source": {
    "path": "/abs/path/recording.mp3",
    "sha256": "…",
    "duration_s": 267.0,
    "sample_rate_hz": 16000,
    "channels": 1
  },
  "config": {
    "asr": "faster-whisper",
    "diarizer": "pyannote",
    "language_id": "voxlingua",
    "translator": "madlad",
    "voiceprint": "wespeaker",
    "gallery": "/home/user/.local/share/transcriber/gallery.db",
    "target_languages": ["de"]
  },
  "speakers": [
    {"id": "S1", "name": "Ms Example", "voiceprint_match": 0.954,
     "speech_s": 30.8, "segment_count": 19}
  ],
  "segments": [
    {"id": "seg-0001", "start_s": 3.32, "end_s": 4.5, "speaker": "S1",
     "language": "de", "language_confidence": 0.98,
     "text": "Großer Goldzahn!",
     "translations": {"de": "Großer Goldzahn!"},
     "translated_from": null, "is_final": true}
  ],
  "warnings": []
}
```

Rules: `text` is always the original. `translations` maps language to text; a segment already in a
target language carries the same text there. `translated_from` is `null` when no translation was
needed. Segments are sorted and do not overlap. Voice embeddings never appear in the output — only
name and similarity.

## Models and licences

All components are usable commercially. The table with sources, dates and the exact API calls is
in `LICENSES.md`; mandatory attribution is in `NOTICE`.

| Purpose | Model | Licence |
|---|---|---|
| Speech recognition | Systran/faster-whisper-large-v3 | MIT |
| Speaker diarization | pyannote/speaker-diarization-3.1, pyannote/segmentation-3.0 | MIT (gated) |
| Speaker embedding | pyannote/wespeaker-voxceleb-resnet34-LM | CC-BY-4.0, attribution required |
| Language identification | speechbrain/lang-id-voxlingua107-ecapa | Apache-2.0 |
| Translation | google/madlad400-3b-mt | Apache-2.0 |

Rejected because they are not commercially usable: `facebook/nllb-200-*` and
`facebook/seamless-m4t-v2-large` (CC-BY-NC-4.0), `nvidia/diar_sortformer_4spk-v1` (CC-BY-NC-4.0).

`transcriber licenses` prints the table; a test fails if a non-commercial licence enters the
default configuration.

## Voiceprint gallery and data protection

Voice embeddings are biometric data. Under the GDPR (Art. 9) they need a legal basis, which is the
operator's responsibility, not the software's. The software enforces the technical part:

- enrolment only with explicit consent (`--consent`); without it nothing is stored,
- deletion per person by name or id, with `PRAGMA secure_delete` and `VACUUM` afterwards,
- the gallery is a local SQLite file with mode 600 in a directory with mode 700,
- embeddings never leave the machine and never appear in a transcript,
- concurrent writers are serialised; a unique index on the name prevents duplicates.

## Configuration

```toml
[adapters]
asr = "faster-whisper"
diarizer = "pyannote"
language_id = "voxlingua"
translator = "madlad"
voiceprint = "wespeaker"     # empty string disables the gallery

[gallery]
path = "/home/user/.local/share/transcriber/gallery.db"

[targets]
languages = ["de"]
```

Pass it with `--config file.toml`. Options on the command line win over the file.

## Writing a plug-in

```python
# my_plugin/__init__.py
from transcriber.ports import AsrSegment
from transcriber.registry import Registry


class MyAsr:
    def transcribe(self, path, options=None):
        return [AsrSegment(0.0, 1.0, "hello", "en")]

    def release(self):
        pass


def register(registry: Registry) -> None:
    registry.register("asr", "my-asr", MyAsr)
```

```toml
[project.entry-points."transcriber.adapters"]
my_plugin = "my_plugin:register"
```

`examples/demo-plugin` is a working example with deterministic adapters and no models; it is
useful to test the whole pipeline (decode, export, HTTP, subtitles) without a GPU.

## Languages

Documentation exists in English (`README.md`) and German (`README.de.md`) with an identical section
structure; a test enforces that. Messages, the command line and the web interface can be switched
between German and English with `--lang` and the language selector; German is the default.
Technical identifiers (`S1`, `job_id`, field names, exit codes) are never translated.

Language handling inside a transcript: Whisper determines the language of the whole file and is
robust at that. A segment keeps a different language only if it is at least 3 seconds long and the
segment-level detector is at least 80 % sure. On a German-dubbed film this reduced the number of
reported languages from 20 to 4.

## Tests and quality

```bash
uv run pytest                        # unit tests, no models, no network
uv run pytest -m integration        # real models on a public-domain sample
uv run pytest --cov=transcriber     # coverage
uv run mypy                         # strict
uv run ruff check
uv run python tools/run_mutants.py   # manual mutants against the suite
```

Measured state at version 0.1.0:

| Aspect | Value |
|---|---|
| Unit tests | 161, all green |
| Integration tests | 6, all green (real Whisper, pyannote, VoxLingua, MADLAD on `jfk.wav`) |
| Coverage | 91 % of 1794 statements |
| Static types | mypy strict, no findings, 23 files |
| Lint | ruff, no findings |
| Mutation testing | 26 of 30 mutants killed; the 4 survivors are documented equivalents |
| Real audio run | 11 s audio in 21 s including model loading, 14.9 GB peak RSS |
| Real video run | 267 s film section in 59 s, 5 speakers, subtitles burned in |
| HTTP run | upload → done → transcript → SRT → delete, with real models |
| Web interface | serves HTTP 200 in web mode |

The integration suite needs `tools/fetch_samples.py` once (it downloads an 11-second public-domain
recording) and roughly 10 GB of model weights.

## Performance and limits

Measured on an RTX 4060 Laptop with 8 GB VRAM:

- 267 s of film audio: 59 s of processing (0.22 × real time), 5 speakers found, verified against
  the user's count.
- Model loading dominates short files: 11 s of audio takes about 21 s in total.
- Whisper and the 3B translator do not fit into 8 GB at the same time; the core therefore loads and
  releases them stage by stage. Streaming runs without translation for the same reason.
- Two runs on the same file are **not** identical: VAD and beam search on the GPU are not bit-exact.
  Observed: 72 and 79 segments on the same input. The core is deterministic and tested as such;
  real model output is an approximation.

Known limits:

- Speaker **identity** is not verified beyond counting: without a reference list, the mapping from
  label to person is unproven.
- Language detection still mislabels occasional segments in music-heavy material.
- The HTTP service has no authentication and keeps jobs in memory only; a restart loses them.
- The WebSocket stream sends raw float32 blocks; no ready-made browser client ships with this
  project.
- Burned-in subtitles share one style for all speakers, positioned at the bottom centre.
- Video is re-encoded (`libx264`, CRF 20); image quality against the source was not measured.

## Project layout

```
src/transcriber/
  core.py            file pipeline: ASR → diarization → language → translation
  stream.py          streaming pipeline with VAD and speaker tracking
  models.py          pydantic data model, validated
  registry.py        adapter registry, entry points
  gallery.py         voiceprint gallery (SQLite, consent, deletion, locking)
  exporters.py       JSON, SRT, VTT, TXT
  service.py         FastAPI application and job manager
  ui.py              Flet web interface and HTTP client
  adapters/          model adapters, VAD, audio I/O, ffmpeg renderer
  i18n/              German and English message catalogues
tests/               unit, edge-case, property, integration and service tests
tools/               sample download, mutant runner, YouTube test
SPEC.md              the contract: scope, data model, acceptance criteria
EVIDENCE-*.md        what was built, what was measured, what is not proven
LICENSES.md          licence audit with dates and sources
NOTICE               attribution required by the licences
```

## Licence

MIT, see `LICENSE`. Third-party components keep their own licences; see `LICENSES.md` and `NOTICE`.

The `ffmpeg` build used on the development host is a GPL build (`--enable-gpl`). Local use is
unproblematic; redistributing the product together with that build triggers GPL obligations, so
ship an LGPL build if you redistribute.

## Development notes

- `SPEC.md` is the contract. Every acceptance criterion (S1…S31) maps to a named test. Behaviour
  changes go through the specification first.
- Every stage ends with an evidence report listing the commands run and their real output,
  including what was not tested.
- The mutant runner edits source files in place and restores them; do not run it while another test
  run is active in the same directory.

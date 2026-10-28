# Transcriber

Transcription of audio files with speaker separation, language detection per segment,
translation into one or more target languages, speaker recognition against a local voiceprint
gallery, live streaming from a microphone, burned-in subtitles and a web interface.
Every building block is a replaceable plug-in.

Status: **P0 und P1 fertig.** Kern, Datenmodell, Adapter-Registry, Exporte, Kommandozeile und die
vier Modelladapter (faster-whisper large-v3, pyannote 3.1, VoxLingua107, MADLAD-400-3B-MT) sind
gebaut, getestet und auf echter Sprache gelaufen (`EVIDENCE-P0.md`, `EVIDENCE-P1.md`).
Die Galerie (P2), Streaming (P3), Video-Untertitel (P4), der HTTP-Dienst (P5) und die
Flet-Oberfläche (P6) sind **nicht gebaut**.

## What it does

One run turns one audio file into a transcript. The transcript holds segments with start and
end time, speaker label, detected language, the original text and the translation. Speakers are
labelled `S1`, `S2`, … and get a name when the voiceprint gallery recognises them.

## Scope (v1)

| Feature | Stage |
|---|---|
| File transcription, JSON/SRT/VTT/TXT export | P0 |
| ASR, diarization, language ID, translation adapters | P1 |
| Voiceprint gallery, consent, deletion | P2 |
| Streaming from microphone and stdin | P3 |
| Burned-in subtitles | P4 |
| HTTP service (FastAPI) | P5 |
| Web interface (Flet) | P6 |

## Install

```bash
uv sync
```

Python 3.12 is pinned. The host Python 3.14 is not used because the ML wheels target 3.12.

## Usage

```bash
uv run transcriber transcribe audio.mp3 --target de --out out --format json --format srt
uv run transcriber adapters
uv run transcriber licenses
```

Messages are German by default. Add `--lang en` for English.

## Configuration

```toml
[adapters]
asr = "faster-whisper"
diarizer = "pyannote"
language_id = "voxlingua"
translator = "madlad"
voiceprint = "wespeaker"

[targets]
languages = ["de"]
```

## Adapters and plug-ins

The core knows only interfaces. An adapter is chosen by name in the configuration.
A plug-in from another package registers itself through the Python entry point group
`transcriber.adapters`; each entry point is a callable that receives the registry.
No change to the core is needed.

## Output format

```json
{
  "schema_version": 1,
  "mode": "file",
  "source": {"path": "...", "sha256": "...", "duration_s": 2.0,
             "sample_rate_hz": 16000, "channels": 1},
  "config": {"asr": "fake", "diarizer": "fake", "language_id": "fake",
             "translator": "fake", "voiceprint": null, "target_languages": ["de"]},
  "speakers": [{"id": "S1", "name": null, "voiceprint_match": null,
                "speech_s": 1.0, "segment_count": 1}],
  "segments": [{"id": "seg-0001", "start_s": 0.0, "end_s": 1.0, "speaker": "S1",
                "language": "de", "language_confidence": 0.9, "text": "Hallo Welt",
                "translations": {"de": "Hallo Welt"}, "translated_from": null,
                "is_final": true}],
  "warnings": []
}
```

## Languages

Documentation exists in English (`README.md`) and German (`README.de.md`) with the same
sections. Messages and the interface can be switched between German and English; German is the
default. Technical identifiers (`S1`, `job_id`, field names, exit codes) are never translated.

## Licences

The intended models and libraries are all usable commercially: MIT, Apache-2.0, BSD-3 and one
CC-BY-4.0 model that requires attribution. NLLB-200 was rejected because it is CC-BY-NC-4.0.
See `LICENSES.md` for the table with the verification date, and `NOTICE` for attribution.

The ffmpeg build on this host is a GPL build (`--enable-gpl`). Local use is unproblematic.
Redistributing the product together with that build triggers GPL obligations; plan an LGPL
build for distribution.

## Tests and quality

```bash
uv run pytest
uv run mypy
uv run ruff check
```

Acceptance criteria are listed in `SPEC.md`, section 5. Every criterion maps to one test.

## Status

Stage P0 complete. The next stage P1 needs the gated pyannote models; access is granted and
verified by a real download.

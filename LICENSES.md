# Lizenzen der verwendeten Komponenten

Prüfdatum: 2026-10-28. Bedingung: alles muss kommerziell nutzbar sein.
Geprüft über die HuggingFace-Modell-API (`https://huggingface.co/api/models/<id>`), die
PyPI-Metadaten (`https://pypi.org/pypi/<paket>/json`) und die GitHub-Lizenz (API oder
`LICENSE`-Datei). Ein automatischer Test prüft die Standardkonfiguration:
`tests/test_licensing.py`.

## Laufzeit und Modelle

| Komponente | Quelle | Lizenz | Kommerziell | Bemerkung |
|---|---|---|---|---|
| faster-whisper, CTranslate2 | PyPI / GitHub SYSTRAN, OpenNMT | MIT | ja | — |
| Systran/faster-whisper-large-v3 (Gewichte) | HF | MIT | ja | keine Freigabe nötig |
| pyannote.audio (Code) | GitHub CNRS | MIT | ja | — |
| pyannote/speaker-diarization-3.1 | HF | MIT | ja | gated: Bedingungen annehmen, Token nötig |
| pyannote/segmentation-3.0 | HF | MIT | ja | gated |
| pyannote/wespeaker-voxceleb-resnet34-LM | HF | CC-BY-4.0 | ja | **Namensnennung nötig**, siehe `NOTICE` |
| speechbrain | PyPI / GitHub | Apache-2.0 | ja | — |
| speechbrain/lang-id-voxlingua107-ecapa | HF | Apache-2.0 | ja | Trainingsdaten aus YouTube-Mitschnitten (VoxLingua107), Restrisiko notiert |
| google/madlad400-3b-mt | HF | Apache-2.0 | ja | 400+ Sprachen |
| silero-vad | PyPI / GitHub snakers4 | MIT | ja | noch nicht angeschlossen (P3) |
| sounddevice | PyPI / GitHub spatialaudio | MIT | ja | noch nicht angeschlossen (P3) |
| flet | PyPI / GitHub flet-dev | Apache-2.0 | ja | noch nicht angeschlossen (P6) |
| fastapi | PyPI / GitHub | MIT | ja | noch nicht angeschlossen (P5) |
| uvicorn | PyPI / GitHub encode | BSD-3 | ja | noch nicht angeschlossen (P5) |
| python-multipart | PyPI / GitHub Kludex | Apache-2.0 | ja | noch nicht angeschlossen (P5) |
| websockets | PyPI / GitHub python-websockets | BSD-3 | ja | noch nicht angeschlossen (P5) |
| numpy | PyPI | BSD-3 | ja | — |
| transformers, tokenizers, safetensors | PyPI | Apache-2.0 | ja | — |
| torch, torchaudio | PyPI | BSD-3 (PyTorch-Variante) | ja | Namensnennung siehe `NOTICE` |
| av (PyAV), soundfile | PyPI | BSD-3 | ja | — |
| typer, pydantic | PyPI | MIT | ja | im Einsatz |
| huggingface-hub | PyPI | Apache-2.0 | ja | — |
| httpx (nur Tests) | PyPI | BSD-3 | ja | noch nicht verwendet |

## Werkzeug auf dem Host

| Komponente | Lizenz | Bewertung |
|---|---|---|
| ffmpeg / ffprobe 9.0.1 (Host-Build) | **GPL-Build** (`--enable-gpl`) | Eigene Nutzung unproblematisch. Weitergabe des Produkts mit diesem Build löst GPL-Pflichten aus; für die Weitergabe ist ein LGPL-Build einzuplanen. |

## Abgelehnt: nicht kommerziell nutzbar

| Komponente | Lizenz | Grund |
|---|---|---|
| facebook/nllb-200-* | CC-BY-NC-4.0 | Non-Commercial, aus dem Plan entfernt |
| facebook/seamless-m4t-v2-large | CC-BY-NC-4.0 | Non-Commercial |
| nvidia/diar_sortformer_4spk-v1 | CC-BY-NC-4.0 | Non-Commercial, war als Ausweichoption gedacht |

## Pflichten

1. `NOTICE` mitführen, solange das Wespeaker-Modell und PyTorch verwendet werden.
2. Bei Weitergabe: ffmpeg-Lizenz klären (LGPL-Build) und diese Tabelle mitliefern.
3. Lizenz erneut prüfen, wenn ein Modell getauscht oder neu geladen wird. Diese Tabelle ist ein
   Stand, keine Gewissheit.

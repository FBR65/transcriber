"""Property-Tests ohne Zusatzpaket: Zufallseingaben prüfen Invarianten (SPEC Abschnitt 12)."""

from __future__ import annotations

import random
from datetime import UTC, datetime

from transcriber.core import assign_speakers
from transcriber.models import RunConfig, Segment, Source, SpeakerInfo, Transcript


def build_transcript(rng: random.Random) -> Transcript:
    segments: list[Segment] = []
    cursor = 0.0
    for index in range(rng.randint(0, 12)):
        length = rng.uniform(0.05, 3.0)
        start = cursor + rng.uniform(0.0, 1.0)
        end = start + length
        cursor = end
        language = rng.choice(["de", "en", "fr"])
        text = f"Text {index}"
        segments.append(
            Segment(
                id=f"seg-{index:04d}",
                start_s=start,
                end_s=end,
                speaker=rng.choice(["S1", "S2", "S3"]),
                language=language,
                language_confidence=rng.random(),
                text=text,
                translations={language: text},
            )
        )
    speakers = [
        SpeakerInfo(
            id=speaker,
            speech_s=sum(s.end_s - s.start_s for s in segments if s.speaker == speaker),
            segment_count=sum(1 for s in segments if s.speaker == speaker),
        )
        for speaker in sorted({segment.speaker for segment in segments})
    ]
    return Transcript(
        created_at=datetime.now(UTC).replace(microsecond=0),
        source=Source(
            path="/tmp/x.wav",
            sha256="0" * 64,
            duration_s=max((segment.end_s for segment in segments), default=0.0),
            sample_rate_hz=16000,
            channels=1,
        ),
        config=RunConfig(
            asr="a", diarizer="b", language_id="c", translator="d", target_languages=["de"]
        ),
        speakers=speakers,
        segments=segments,
    )


def test_model_roundtrip_is_stable() -> None:
    rng = random.Random(20261028)
    for _ in range(200):
        transcript = build_transcript(rng)
        once = transcript.to_dict()
        twice = Transcript.model_validate(once).to_dict()
        assert once == twice
        assert [segment["start_s"] for segment in once["segments"]] == sorted(
            segment["start_s"] for segment in once["segments"]
        )


def test_assign_speakers_always_returns_a_known_label() -> None:
    rng = random.Random(4711)
    for _ in range(300):
        count = rng.randint(1, 5)
        turns: list[tuple[float, float, str]] = []
        cursor = 0.0
        for index in range(count):
            length = rng.uniform(0.1, 4.0)
            turns.append((cursor, cursor + length, f"S{index + 1}"))
            cursor += length + rng.uniform(0.0, 1.0)
        start = rng.uniform(-1.0, cursor + 1.0)
        end = start + rng.uniform(0.01, 5.0)
        chosen = assign_speakers(start, end, turns)
        assert chosen in {label for _, _, label in turns}

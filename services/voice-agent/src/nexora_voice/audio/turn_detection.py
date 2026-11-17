"""End-of-turn detection.

* auto (hands-free / wake word): Silero VAD and LiveKit's semantic multilingual turn-detector model,
  with dynamic endpointing. The model judges whether the sentence is complete, so a fixed silence
  timer is not the only signal. For languages the model doesn't cover (Tamil, as of 1.8), LiveKit
  falls back to VAD endpointing with the dynamic delay window.
* manual (hold-to-talk): the browser commits turns explicitly with the `nexora.end_turn` RPC.
"""

from __future__ import annotations

import logging
from typing import Any

from livekit.agents import TurnHandlingOptions

from nexora_voice.config import Settings

logger = logging.getLogger("nexora.voice.turns")


def build_turn_handling(settings: Settings, turn_mode: str) -> TurnHandlingOptions:
    detection: Any
    if turn_mode == "manual":
        detection = "manual"
    elif settings.turn_detector == "multilingual":
        try:
            from livekit.plugins.turn_detector.multilingual import MultilingualModel

            detection = MultilingualModel()
        except Exception as exc:  # model files missing: run `python -m nexora_voice.main download-files`
            logger.warning("turn detector unavailable (%s); falling back to VAD endpointing", exc)
            detection = "vad"
    else:
        detection = "vad"
    return {
        "turn_detection": detection,
        "endpointing": {
            "mode": "dynamic",
            "min_delay": settings.min_endpointing_delay,
            "max_delay": settings.max_endpointing_delay,
        },
        "interruption": {
            "enabled": True,
            "mode": "vad",
            "min_duration": 0.4,
            "resume_false_interruption": True,
            "false_interruption_timeout": 1.5,
        },
        # Preemptive generation would start server-side turns (and DB writes) that may be discarded.
        "preemptive_generation": {"enabled": False},
    }

"""Per-turn voice latency: end-of-utterance delay, STT, LLM time-to-first-token, TTS time-to-first-byte."""

from __future__ import annotations

from livekit.agents import metrics

from nexora_voice.schemas.events import TurnMetrics


class TurnLatencyTracker:
    """Collects metrics events. A turn is complete when the TTS reports for the reply."""

    def __init__(self) -> None:
        self.current = TurnMetrics()

    def add(self, m: metrics.AgentMetrics) -> TurnMetrics | None:
        if isinstance(m, metrics.EOUMetrics):
            self.current = TurnMetrics(
                eou_delay_ms=m.end_of_utterance_delay * 1000, stt_ms=m.transcription_delay * 1000
            )
        elif isinstance(m, metrics.STTMetrics) and m.duration:
            self.current.stt_ms = self.current.stt_ms or m.duration * 1000
        elif isinstance(m, metrics.LLMMetrics):
            self.current.llm_ttft_ms = m.ttft * 1000 if m.ttft and m.ttft > 0 else None
        elif isinstance(m, metrics.TTSMetrics) and self.current.llm_ttft_ms is not None:
            self.current.tts_ttfb_ms = m.ttfb * 1000 if m.ttfb and m.ttfb > 0 else None
            parts = [self.current.eou_delay_ms, self.current.llm_ttft_ms, self.current.tts_ttfb_ms]
            self.current.end_to_end_ms = sum(p for p in parts if p is not None)
            done, self.current = self.current, TurnMetrics()
            return done
        return None

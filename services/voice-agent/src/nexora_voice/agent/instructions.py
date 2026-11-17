"""Agent-side text. Reasoning instructions live in the core API (one prompt for text and voice);
these are only the fixed phrases the agent speaks itself."""

GREETINGS = {
    "ta": "வணக்கம்! நான் நெக்ஸோரா. உங்களுக்கு என்ன உதவி வேண்டும்?",
    "en": "Hi, I'm Nexora. How can I help?",
}

ERROR_REPLY = {
    "ta": "மன்னிக்கவும், இப்போது பதில் தர முடியவில்லை. மீண்டும் முயற்சிக்கவும்.",
    "en": "Sorry, I couldn't reach my assistant service just now. Please try again.",
}

FAREWELL = {
    "ta": "இந்த உரையாடல் நேர வரம்பை எட்டியது. மீண்டும் சந்திப்போம்!",
    "en": "We've reached the time limit for this voice session. Talk soon!",
}

# The local Agent needs instructions, but the server-side graph makes every decision.
AGENT_INSTRUCTIONS = "Relay the user's speech to the Nexora assistant service and speak its replies."


def pick(table: dict[str, str], language: str) -> str:
    return table.get(language, table["en"])

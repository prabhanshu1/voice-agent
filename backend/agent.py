from dotenv import load_dotenv

from livekit import agents
from livekit.agents import AgentSession, Agent, RoomInputOptions
from livekit.plugins import (
    openai,
    noise_cancellation,
    silero,
)
from livekit.plugins.turn_detector.multilingual import MultilingualModel
import asyncio

from custom_stt import mySTT
from custom_tts import myTTS
from custom_llm import myLLM

import settings

load_dotenv()

class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(instructions=settings.LLM_PROMPT) ## LLM Prompt for AI


async def entrypoint(ctx: agents.JobContext):
    await ctx.connect()

    session = AgentSession(
        stt=mySTT(),
        # llm=openai.with_ollama(base_url=settings.LLM_SERVER_URL),
        llm=myLLM.with_ollama(model=settings.LLM_MODEL, base_url=settings.LLM_SERVER_URL),
        tts=myTTS(),
        vad=silero.VAD.load(),
        turn_detection=MultilingualModel(),
    )

    await session.start(
        room=ctx.room,
        agent=Assistant(),
        room_input_options=RoomInputOptions(
            noise_cancellation=noise_cancellation.BVC(),
        ),
    )

    await asyncio.sleep(1)
    await session.say(settings.GREETING_MESSAGE, allow_interruptions=True)

    # await session.generate_reply(
    #     # instructions="Greet the user and offer your assistance."
    # )


if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))
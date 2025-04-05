import asyncio

from dotenv import load_dotenv
from livekit.agents import AutoSubscribe, JobContext, WorkerOptions, cli, llm
from livekit.agents.voice_assistant import VoiceAssistant
from livekit.plugins import openai, silero
# from api import AssistantFnc
from custom_stt import mySTT
from custom_tts import myTTS
import settings

load_dotenv()


async def entrypoint(ctx: JobContext):
    initial_ctx = llm.ChatContext().append(
        role="system",
        text=(
            "You are a cyberfraud help assistant created by Government of India. Your interface with users will be voice. "
            "your response help users to reveal what happened to them and assist them in reporting cyberfraud."
            "You should ask important question related to this, and avoiding usage of unpronouncable punctuation."
        ),
    )
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
    # fnc_ctx = AssistantFnc()
    print("inside entrypoint -before assistant")
    assitant = VoiceAssistant(
        vad=silero.VAD.load(),
        # stt=openai.STT(),
        stt = mySTT(),
        # llm=openai.LLM(),
        llm = openai.LLM.with_ollama(model=settings.LLM_MODEL, base_url=settings.LLM_SERVER_URL),
        # tts=openai.TTS(),
        tts = myTTS(),
        chat_ctx=initial_ctx,
        # fnc_ctx=fnc_ctx,
    )
    assitant.start(ctx.room)

    await asyncio.sleep(1)
    await assitant.say("Hi, I am cyberfraud agent!", allow_interruptions=True)


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
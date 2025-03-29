import io
import logging
import wave
# import requests
from dotenv import load_dotenv
from livekit.agents import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    tts,
    utils,
)
from typing import Union


from livekit.agents.utils import AudioBuffer
from pydub import AudioSegment
from faster_whisper import WhisperModel
model_size = "tiny"
model = WhisperModel(model_size, device="cpu", compute_type="float32")


load_dotenv(dotenv_path=".env.local")
logger = logging.getLogger("voice-agent")

class mySTT(tts.TTS):
    def __init__(
        self,
    ):

        super().__init__(
            capabilities=tts.TTSCapabilities(
                streaming=False,
            ),
        )

    async def _recognize_impl(
        self, buffer: AudioBuffer, *, language: Union[str, None] = None
    ) -> stt.SpeechEvent:
        
        resultText = model.transcribe("speech_Claribel.wav") 
        print("transcribed-text: ",resultText["text"])
        
        logger.info(f"response: {resultText}")

        return stt.SpeechEvent(
            type=stt.SpeechEventType.FINAL_TRANSCRIPT,
            alternatives=[
                stt.SpeechData(text=resultText or "", language=language or "")
            ],
        )
   
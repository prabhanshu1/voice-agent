import io
import logging
import wave
import httpx
from dotenv import load_dotenv
from livekit.agents import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    stt,
    utils,
)
from typing import Union
from livekit.agents.utils import AudioBuffer
from livekit.agents.types import APIConnectOptions
import settings

load_dotenv(dotenv_path=".env.local")
logger = logging.getLogger("[STT]")


class mySTT(stt.STT):
    def __init__(self):
        super().__init__(
            capabilities=stt.STTCapabilities(streaming=False, interim_results=False)
        )

    async def _recognize_impl(
        self, buffer: AudioBuffer, *, language: Union[str, None] = None, conn_options: APIConnectOptions = APIConnectOptions(),
    ) -> stt.SpeechEvent:
        """
        Recognize speech from the given audio buffer using the locally running Whisper server.

        Args:
            buffer (AudioBuffer): The audio buffer containing the speech data.
            language (Union[str, None]): The language of the speech (optional).

        Returns:
            stt.SpeechEvent: The transcription result.
        """
        try:
            # Merge audio frames into a single buffer
            buffer = utils.merge_frames(buffer)

            # Convert the audio buffer to WAV format
            io_buffer = io.BytesIO()
            with wave.open(io_buffer, "wb") as wav:
                wav.setnchannels(buffer.num_channels)
                wav.setsampwidth(2)  # 16-bit
                wav.setframerate(buffer.sample_rate)
                wav.writeframes(buffer.data)

            # Prepare the request payload
            io_buffer.seek(0)  # Reset the buffer position
            # files = {"audio": ("audio.wav", io_buffer, "audio/wav")}  # Use "audio" as the key
            files = {"file": ("audio.wav", io_buffer, "audio/wav")}  # Use "audio" as the key
            data = {"language": language} if language else {}

            # Send the audio to the locally running Whisper server
            async with httpx.AsyncClient() as client:
                logger.info("Sending audio to Whisper server...")
                response = await client.post(settings.STT_SERVER_URL, 
                                             files=files, 
                                             data=data)
                response.raise_for_status()

            # Parse the transcription result
            transcription = response.json()
            print("Here is transcription:", transcription)
            # result_text = transcription.get("transcription", "")  # Use "transcription" as the key
            result_text = transcription.get("text", "")
            logger.info(f"Transcription language: {language}")
            logger.info(f"Transcription result: {result_text}")

            return stt.SpeechEvent(
                type=stt.SpeechEventType.FINAL_TRANSCRIPT,
                alternatives=[
                    stt.SpeechData(text=result_text or "", language=language or "")
                ],
            )
        except httpx.TimeoutException:
            logger.error("Timeout while connecting to the Whisper server")
            raise APITimeoutError()
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error from Whisper server: {e.response.text}")
            raise APIStatusError(
                e.response.text,
                status_code=e.response.status_code,
                request_id=None,
                body=e.response.content,
            )
        except Exception as e:
            logger.exception("Failed to process audio with Whisper server")
            raise APIConnectionError() from e
# import io
# import logging
# from dotenv import load_dotenv
# from livekit.agents import tts
# from typing import Union
# import wave

# load_dotenv(dotenv_path=".env.local")
# logger = logging.getLogger("voice-agent")

# class myTTS(tts.TTS):
#     def __init__(self):
#         super().__init__(
#             capabilities=tts.TTSCapabilities(
#                 streaming=False,  # Set to True if you want streaming TTS
#             ),
#             sample_rate=48000,
#             num_channels=1,
#         )

#     async def _synthesize_impl(
#         self, text: str, *, language: Union[str, None] = None
#     ) -> bytes:
#         """
#         Synthesize speech from the given text.

#         Args:
#             text (str): The input text to convert to speech.
#             language (Union[str, None]): The language of the text (optional).

#         Returns:
#             bytes: The synthesized audio data in WAV format.
#         """
#         logger.info(f"Synthesizing speech for text: {text}")

#         # Example: Generate a dummy WAV file (replace this with your TTS logic)
#         sample_rate = 16000  # 16 kHz sample rate
#         duration_seconds = 2  # 2 seconds of silence
#         num_samples = sample_rate * duration_seconds
#         silence = (b"\x00\x00" * num_samples)  # Generate silence

#         # Create a WAV file in memory
#         wav_buffer = io.BytesIO()
#         with wave.open(wav_buffer, "wb") as wav_file:
#             wav_file.setnchannels(1)  # Mono audio
#             wav_file.setsampwidth(2)  # 16-bit samples
#             wav_file.setframerate(sample_rate)
#             wav_file.writeframes(silence)

#         logger.info("Speech synthesis complete")
#         return wav_buffer.getvalue()
    
#     async def synthesize(
#         self, text: str, *, language: Union[str, None] = None
#     ) -> bytes:
#         """
#         Public method to synthesize speech. This calls the internal _synthesize_impl.
#         """
#         return await self._synthesize_impl(text, language=language)


from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Optional

import httpx
from livekit.agents import (
    APIConnectionError,
    APIConnectOptions,
    APIStatusError,
    APITimeoutError,
    tts,
    utils,
)

from log import logger

XTTS_SAMPLE_RATE = 48000
XTTS_CHANNELS = 1

DEFAULT_MODEL = "xtts-default"
DEFAULT_VOICE = "default-voice"


@dataclass
class _TTSOptions:
    model: str
    voice: str
    speed: float
    instructions: Optional[str] = None


class myTTS(tts.TTS):
    def __init__(
        self,
        *,
        model: str = DEFAULT_MODEL,
        voice: str = DEFAULT_VOICE,
        speed: float = 1.0,
        instructions: Optional[str] = None,
        base_url: str = "http://localhost:8020",  # Local XTTS server URL
    ) -> None:
        """
        Create a new instance of XTTS TTS.

        ``base_url`` must point to the locally running XTTS server.
        """
        super().__init__(
            capabilities=tts.TTSCapabilities(
                streaming=False,
            ),
            sample_rate=XTTS_SAMPLE_RATE,
            num_channels=XTTS_CHANNELS,
        )

        self._opts = _TTSOptions(
            model=model,
            voice=voice,
            speed=speed,
            instructions=instructions,
        )
        self._base_url = base_url
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=15.0, read=5.0, write=5.0, pool=5.0),
            follow_redirects=True,
        )

    def update_options(
        self,
        *,
        model: str | None,
        voice: str | None,
        speed: float | None,
        instructions: Optional[str] = None,
    ) -> None:
        self._opts.model = model or self._opts.model
        self._opts.voice = voice or self._opts.voice
        self._opts.speed = speed or self._opts.speed
        self._opts.instructions = instructions or self._opts.instructions

    def synthesize(
        self,
        text: str,
        *,
        conn_options: Optional[APIConnectOptions] = None,
    ) -> "ChunkedStream":
        print("inside myTTS, synthesise: ", text)
        return ChunkedStream(
            tts=self,
            input_text=text,
            conn_options=conn_options,
            opts=self._opts,
            client=self._client,
        )


class ChunkedStream(tts.ChunkedStream):
    def __init__(
        self,
        *,
        tts: TTS,
        input_text: str,
        conn_options: Optional[APIConnectOptions] = None,
        opts: _TTSOptions,
        client: httpx.AsyncClient,
    ) -> None:
        super().__init__(tts=tts, input_text=input_text, conn_options=conn_options)
        self._client = client
        self._opts = opts

    async def _run(self):
        try:
            print("inside tts: self._client: ", self._client)
            print("inside tts: self.input_text: ", self.input_text)
            # Send a request to the local XTTS server
            response = await self._client.post(
                f"{self._tts._base_url}/tts_to_audio/",
                json={
                    "text": self.input_text,
                    # "model": self._opts.model,
                    "speaker_wav": "male",
                    "language": "en"
                    # "voice": self._opts.voice,
                    # "speed": self._opts.speed,
                    # "instructions": self._opts.instructions,
                },
            )
            print("inside tts2: self.input_text: ", response)
            response.raise_for_status()
            print("inside tts3: self.input_text: ", response)
            # Stream the audio data from the response
            decoder = utils.codecs.AudioStreamDecoder(
                sample_rate=XTTS_SAMPLE_RATE,
                num_channels=XTTS_CHANNELS,
            )

            request_id = utils.shortuuid()

            @utils.log_exceptions(logger=logger)
            async def _decode_loop():
                try:
                    async for chunk in response.aiter_bytes():
                        decoder.push(chunk)
                finally:
                    decoder.end_input()

            decode_task = asyncio.create_task(_decode_loop())

            try:
                emitter = tts.SynthesizedAudioEmitter(
                    event_ch=self._event_ch,
                    request_id=request_id,
                )
                async for frame in decoder:
                    emitter.push(frame)
                emitter.flush()
            finally:
                await utils.aio.gracefully_cancel(decode_task)
                await decoder.aclose()

        except httpx.TimeoutException:
            raise APITimeoutError()
        except httpx.HTTPStatusError as e:
            raise APIStatusError(
                e.response.text,
                status_code=e.response.status_code,
                request_id=None,
                body=e.response.content,
            )
        except Exception as e:
            raise APIConnectionError() from e
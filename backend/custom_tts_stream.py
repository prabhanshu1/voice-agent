import httpx
from dataclasses import dataclass
from typing import Optional
from livekit.agents import (
    APIConnectionError,
    APIConnectOptions,
    APIStatusError,
    APITimeoutError,
    tts,
    utils,
)

import logging
logger = logging.getLogger("[TTS-Stream]")


@dataclass
class _StreamTTSOptions:
    model: str
    voice: str
    speed: float
    instructions: Optional[str] = None



class TTSStream(tts.SynthesizeStream):
    def __init__(
        self,
        *,
        tts: tts.TTS,
        conn_options: Optional[APIConnectOptions] = None,
        opts: _StreamTTSOptions,
        client: httpx.AsyncClient,
    ) -> None:
        super().__init__(tts=tts, conn_options=conn_options)
        self._client = client
        self._opts = opts

    async def _run(self):
        try:
            logger.info(f"Streaming text to TTS server: {self._opts}")
            response = await self._client.post(
                f"{self._tts._base_url}/api/tts",
                json={
                    "text": self.input_text,
                    "model_name": self._opts.model,
                    "voice": self._opts.voice,
                    "speed": self._opts.speed,
                },
            )
            response.raise_for_status()

            logger.info("TTS server response received. Streaming audio...")

            # Stream the audio data from the response
            async for chunk in response.aiter_bytes():
                logger.info(f"Audio chunk received: {len(chunk)} bytes")
                self._event_ch.send_nowait(chunk)

            logger.info("TTS audio streaming completed.")

        except httpx.TimeoutException:
            logger.error("Timeout while connecting to the TTS server.")
            raise APITimeoutError()
        except httpx.HTTPStatusError as e:
            logger.error(f"TTS server returned an error: {e.response.text}")
            raise APIStatusError(
                e.response.text,
                status_code=e.response.status_code,
                request_id=None,
                body=e.response.content,
            )
        except Exception as e:
            logger.exception("Error while streaming audio from TTS server.")
            raise APIConnectionError() from e
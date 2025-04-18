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
    tokenize,
)
import settings, helpers
import logging
from custom_tts_stream import TTSStream

logger = logging.getLogger("[TTS]")


XTTS_SAMPLE_RATE = 22050
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
        base_url: str = settings.TTS_SERVER_URL,  # Local XTTS server URL
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
            timeout=httpx.Timeout(connect=15.0, read=60.0, write=15.0, pool=5.0),
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
    def stream(
        self, *, conn_options: Optional[APIConnectOptions] = None
    ) -> tts.SynthesizeStream:
        # return TTSStream(
        #     tts=self,
        #     conn_options=conn_options,
        #     opts=self._opts,
        #     client=self._client,
        # )
        raise NotImplementedError(
            "Hey guys --- streaming is not supported by this TTS, please use a different TTS or use a StreamAdapter"
        )
        # return tts.SynthesizeStream(tts=self, conn_options=conn_options)
        # return tts.StreamAdapterWrapper(
        #     tts=self,
        #     conn_options=conn_options,
        #     wrapped_tts=self,
        #     sentence_tokenizer=tokenize.basic.SentenceTokenizer(),
        # )
 



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
            opts = helpers._strip_nones({
                "text": self.input_text,
                "split_sentences":True,
                "repetition_penalty" : 4.0,
                # "model_name": "tts_models/multilingual/multi-dataset/your_tts",
            })
            response = await self._client.post(
                f"{self._tts._base_url}", json=opts, timeout=30.0
                # params={
                #     "text": self.input_text,
                #     #https://github.com/coqui-ai/TTS/blob/dev/TTS/.models.json
                #     # "model_name": "tts_models/multilingual/multi-dataset/xtts_v2", # RTF - 0.08
                #     # "model_name": "tts_models/multilingual/multi-dataset/your_tts",
                #     # "model_name": "tts_models/en/ljspeech/speedy-speech",# RTF - 0.08
                #     # "model_name": "tts_models/en/ljspeech/tacotron2-DDC", # RTF - 0.08
                #     # "model_name": "tts_models/en/ljspeech/glow-tts", # RTF - 0.08
                #     # "language": "en"
                #     # "voice": self._opts.voice,
                #     # "speed": self._opts.speed,
                #     # "instructions": self._opts.instructions,
                #     "split_sentences":True,
                #     "repetition_penalty" : 4.0,
                # },
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
                        logger.info(f"Audio chunk received: {len(chunk)} bytes")
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
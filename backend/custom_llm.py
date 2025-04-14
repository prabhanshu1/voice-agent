# Copyright 2023 LiveKit, Inc.
#

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


from __future__ import annotations
from dataclasses import asdict

import base64
from collections import OrderedDict
from collections.abc import Awaitable
from dataclasses import dataclass, field
from typing import Any, Callable, Union

import json
from dataclasses import dataclass
from typing import Any

import httpx

import openai
from livekit.agents import APIConnectionError, APIStatusError, APITimeoutError, llm
from livekit.agents.llm import ToolChoice, utils as llm_utils
from livekit.agents.llm.chat_context import ChatContext
from livekit.agents.llm.tool_context import FunctionTool
from livekit.agents.types import (
    DEFAULT_API_CONNECT_OPTIONS,
    NOT_GIVEN,
    APIConnectOptions,
    NotGivenOr,
)
from livekit.agents.utils import is_given
from openai.types.chat import (
    ChatCompletionChunk,
    ChatCompletionToolChoiceOptionParam,
    completion_create_params,
)
from openai.types.chat.chat_completion_chunk import Choice

# from ._oai_api import build_oai_function_description
from log import logger
from models import (
    ChatModels,
)
from custom_llm_utils import build_oai_message, to_chat_ctx, strip_nones, build_oai_context
import re
from pprint import pprint


@dataclass
class _LLMOptions:
    model: str | ChatModels
    user: NotGivenOr[str]
    temperature: NotGivenOr[float]
    parallel_tool_calls: NotGivenOr[bool]
    tool_choice: NotGivenOr[ToolChoice]
    store: NotGivenOr[bool]
    metadata: NotGivenOr[dict[str, str]]

class myLLM(llm.LLM):
    def __init__(
        self,
        *,
        model: str | ChatModels = "gpt-4o",
        api_key: NotGivenOr[str] = NOT_GIVEN,
        base_url: NotGivenOr[str] = NOT_GIVEN,
        client: openai.AsyncClient | None = None,
        user: NotGivenOr[str] = NOT_GIVEN,
        temperature: NotGivenOr[float] = NOT_GIVEN,
        parallel_tool_calls: NotGivenOr[bool] = NOT_GIVEN,
        tool_choice: NotGivenOr[ToolChoice] = NOT_GIVEN,
        store: NotGivenOr[bool] = NOT_GIVEN,
        metadata: NotGivenOr[dict[str, str]] = NOT_GIVEN,
        timeout: httpx.Timeout | None = None,
    ) -> None:
        """
        Create a new instance of OpenAI LLM.

        ``api_key`` must be set to your OpenAI API key, either using the argument or by setting the
        ``OPENAI_API_KEY`` environmental variable.
        """
        super().__init__()
        self._opts = _LLMOptions(
            model=model,
            user=user,
            temperature=temperature,
            parallel_tool_calls=parallel_tool_calls,
            tool_choice=tool_choice,
            store=store,
            metadata=metadata,
        )
        self._client = client or openai.AsyncClient(
            api_key=api_key if is_given(api_key) else None,
            base_url=base_url if is_given(base_url) else None,
            max_retries=0,
            http_client=httpx.AsyncClient(
                timeout=timeout
                if timeout
                else httpx.Timeout(connect=15.0, read=5.0, write=5.0, pool=5.0),
                follow_redirects=True,
                limits=httpx.Limits(
                    max_connections=50,
                    max_keepalive_connections=50,
                    keepalive_expiry=120,
                ),
            ),
        )
    
    @staticmethod
    def with_ollama(
        *,
        model: str = "llama3.1",
        base_url: str = "http://localhost:11434/v1",
        client: openai.AsyncClient | None = None,
        temperature: NotGivenOr[float] = NOT_GIVEN,
        parallel_tool_calls: NotGivenOr[bool] = NOT_GIVEN,
        tool_choice: ToolChoice = "auto",
    ) -> myLLM:
        """
        Create a new instance of Ollama LLM.
        """

        return myLLM(
            model=model,
            api_key="ollama",
            base_url=base_url,
            client=client,
            temperature=temperature,
            parallel_tool_calls=parallel_tool_calls,
            tool_choice=tool_choice,
        )

    def chat(
        self,
        *,
        chat_ctx: ChatContext,
        tools: list[FunctionTool] | None = None,
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
        parallel_tool_calls: NotGivenOr[bool] = NOT_GIVEN,
        tool_choice: NotGivenOr[ToolChoice] = NOT_GIVEN,
        response_format: NotGivenOr[
            completion_create_params.ResponseFormat | type[llm_utils.ResponseFormatT]
        ] = NOT_GIVEN,
        extra_kwargs: NotGivenOr[dict[str, Any]] = NOT_GIVEN,
    ) -> LLMStream:
        extra = {}
        if is_given(extra_kwargs):
            extra.update(extra_kwargs)

        if is_given(self._opts.metadata):
            extra["metadata"] = self._opts.metadata

        if is_given(self._opts.user):
            extra["user"] = self._opts.user

        parallel_tool_calls = (
            parallel_tool_calls if is_given(parallel_tool_calls) else self._opts.parallel_tool_calls
        )
        if is_given(parallel_tool_calls):
            extra["parallel_tool_calls"] = parallel_tool_calls

        tool_choice = tool_choice if is_given(tool_choice) else self._opts.tool_choice  # type: ignore
        if is_given(tool_choice):
            oai_tool_choice: ChatCompletionToolChoiceOptionParam
            if isinstance(tool_choice, dict):
                oai_tool_choice = {
                    "type": "function",
                    "function": {"name": tool_choice["function"]["name"]},
                }
                extra["tool_choice"] = oai_tool_choice
            elif tool_choice in ("auto", "required", "none"):
                oai_tool_choice = tool_choice
                extra["tool_choice"] = oai_tool_choice

        if is_given(response_format):
            extra["response_format"] = llm_utils.to_openai_response_format(response_format)

        return LLMStream(
            self,
            model=self._opts.model,
            client=self._client,
            chat_ctx=chat_ctx,
            tools=tools or [],
            conn_options=conn_options,
            extra_kwargs=extra,
        )


class LLMStream(llm.LLMStream):
    def __init__(
        self,
        llm: LLM,
        *,
        model: str | ChatModels,
        client: openai.AsyncClient,
        chat_ctx: llm.ChatContext,
        tools: list[FunctionTool],
        conn_options: APIConnectOptions,
        extra_kwargs: dict[str, Any],
    ) -> None:
        super().__init__(llm, chat_ctx=chat_ctx, tools=tools, conn_options=conn_options)
        self._model = model
        self._client = client
        self._llm = llm
        self._extra_kwargs = extra_kwargs

    async def _run(self) -> None:
        # current function call that we're waiting for full completion (args are streamed)
        # (defined inside the _run method to make sure the state is reset for each run/attempt)
        self._oai_stream: openai.AsyncStream[ChatCompletionChunk] | None = None
        self._tool_call_id: str | None = None
        self._fnc_name: str | None = None
        self._fnc_raw_arguments: str | None = None
        self._tool_index: int | None = None
        retryable = True

        try:
            
            # self._oai_stream = stream = await self._client.chat.completions.create(
            #     messages=to_chat_ctx(self._chat_ctx, id(self._llm)),
            #     tools=to_fnc_ctx(self._tools) if self._tools else openai.NOT_GIVEN,
            #     model=self._model,
            #     stream_options={"include_usage": True},
            #     stream=True,
            #     **self._extra_kwargs,
            # )
            # print(type(self._chat_ctx))
            # print(vars(self._chat_ctx))
            # pprint(dir(self._chat_ctx))

            if self._chat_ctx is None:
                print("Chat context is None")
                raise ValueError("Chat context is None")
            else:
                print("Chat context is not None")
            messages = build_oai_context(self._chat_ctx, id(self))
            opts = strip_nones({
                # "model": self._model,
                "messages": messages,
                # "temperature": self._temperature,
                "max_tokens": 128,
                "stop": ["<end_of_turn>"],
                "stream": False,
            })
            print("within llm: ", self._client.base_url)
            print("\n\nwithin llm2: ", opts)
            
            base_url = str(self._llm._client.base_url).rstrip("/")
            print("base_url: ", base_url)
            # Use httpx to send the request directly to the Ollama server
            async with httpx.AsyncClient(follow_redirects=True) as client:
                print("\n\nwithin llm3: client ", client)

                response = await client.post(base_url, json=opts, timeout=30)
                print("\n\nwithin llm4: ", response)
                response.raise_for_status()
                print("\n\nwithin llm5: ", response)
                # Process the response stream
                # Parse the full response
            response_json = response.json()
            print("LLM Response JSON:", response_json)

            # Extract the final content from the response
            final_output = ""
            # for choice in response_json.get("choices", []):
            #     print("Choice:", choice)
            # print(type(response_json))
            
            # pprint(dir(response_json))
            # final_output += response_json.get("response", {})
            final_output += response_json["choices"][0]["message"]["content"]

            final_output = re.sub(r"[^a-zA-Z0-9\s\?\.\,\!']", "", str(final_output))
            # final_output = response_json.get("message")
            print("Final LLM Output:", final_output)
            self._event_ch.send_nowait(
                llm.ChatChunk(
                id=response_json.get("id", ""),
                delta=llm.ChoiceDelta(content=final_output, role="assistant")
                )
            )
            # Send the final output to the pipeline
            # self._event_ch.send_nowait(
            #     llm.ChatChunk(
            #         request_id=response_json.get("id", ""),
            #         choices=[
            #             llm.ChoiceDelta(
            #                 delta=llm.ChoiceDelta(content=final_output, role="assistant"),
            #                 index=0,
            #             )
            #         ],
            #     )
            # )




            # async with stream:
            #     async for chunk in stream:
            #         for choice in chunk.choices:
            #             chat_chunk = self._parse_choice(chunk.id, choice)
            #             if chat_chunk is not None:
            #                 retryable = False
            #                 self._event_ch.send_nowait(chat_chunk)

            #         if chunk.usage is not None:
            #             retryable = False
            #             chunk = llm.ChatChunk(
            #                 id=chunk.id,
            #                 usage=llm.CompletionUsage(
            #                     completion_tokens=chunk.usage.completion_tokens,
            #                     prompt_tokens=chunk.usage.prompt_tokens,
            #                     total_tokens=chunk.usage.total_tokens,
            #                 ),
            #             )
            #             self._event_ch.send_nowait(chunk)

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
        # current function call that we're waiting for full completion (args are streamed)
        # (defined inside the _run method to make sure the state is reset for each run/attempt)
        # self._oai_stream: openai.AsyncStream[ChatCompletionChunk] | None = None
        # self._tool_call_id: str | None = None
        # self._fnc_name: str | None = None
        # self._fnc_raw_arguments: str | None = None
        # self._tool_index: int | None = None
        # retryable = True

        # try:
        #     if self._fnc_ctx and len(self._fnc_ctx.ai_functions) > 0:
        #         tools = [
        #             build_oai_function_description(fnc, self._llm._capabilities)
        #             for fnc in self._fnc_ctx.ai_functions.values()
        #         ]
        #     else:
        #         tools = None

        #     opts: dict[str, Any] = {
        #         "tools": tools,
        #         "parallel_tool_calls": self._parallel_tool_calls if tools else None,
        #         "tool_choice": (
        #             {"type": "function", "function": {"name": self._tool_choice.name}}
        #             if isinstance(self._tool_choice, ToolChoice)
        #             else self._tool_choice
        #         )
        #         if tools is not None
        #         else None,
        #         "temperature": self._temperature,
        #         "metadata": self._llm._opts.metadata,
        #         "max_tokens": self._llm._opts.max_tokens,
        #         "store": self._llm._opts.store,
        #         "n": self._n,
        #         "stream": True,
        #         "stream_options": {"include_usage": True},
        #         "user": self._user or openai.NOT_GIVEN,
        #     }
        #     # remove None values from the options
        #     opts = _strip_nones(opts)

        #     messages = _build_oai_context(self._chat_ctx, id(self))
        #     print("within llm: ", self._client)
        #     print("\n\n within llm: ", messages)
        #     stream = await self._client.chat.completions.create(
        #         messages=messages,
        #         model=self._model,
        #         **opts,
        #     )
        #     print("\n\n within llm 3: ", stream)

        #     async with stream:
        #         async for chunk in stream:
        #             for choice in chunk.choices:
        #                 chat_chunk = self._parse_choice(chunk.id, choice)
        #                 if chat_chunk is not None:
        #                     retryable = False
        #                     self._event_ch.send_nowait(chat_chunk)

        #             if chunk.usage is not None:
        #                 usage = chunk.usage
        #                 self._event_ch.send_nowait(
        #                     llm.ChatChunk(
        #                         request_id=chunk.id,
        #                         usage=llm.CompletionUsage(
        #                             completion_tokens=usage.completion_tokens,
        #                             prompt_tokens=usage.prompt_tokens,
        #                             total_tokens=usage.total_tokens,
        #                         ),
        #                     )
        #                 )

        # except openai.APITimeoutError:
        #     raise APITimeoutError(retryable=retryable)
        # except openai.APIStatusError as e:
        #     raise APIStatusError(
        #         e.message,
        #         status_code=e.status_code,
        #         request_id=e.request_id,
        #         body=e.body,
        #     )
        # except Exception as e:
        #     raise APIConnectionError(retryable=retryable) from e

    def _parse_choice(self, id: str, choice: Choice) -> llm.ChatChunk | None:
        delta = choice.delta

        # https://github.com/livekit/agents/issues/688
        # the delta can be None when using Azure OpenAI (content filtering)
        if delta is None:
            return None

        if delta.tool_calls:
            for tool in delta.tool_calls:
                if not tool.function:
                    continue

                call_chunk = None
                if self._tool_call_id and tool.id and tool.index != self._tool_index:
                    call_chunk = llm.ChatChunk(
                        id=id,
                        delta=llm.ChoiceDelta(
                            role="assistant",
                            content=delta.content,
                            tool_calls=[
                                llm.FunctionToolCall(
                                    arguments=self._fnc_raw_arguments or "",
                                    name=self._fnc_name or "",
                                    call_id=self._tool_call_id or "",
                                )
                            ],
                        ),
                    )
                    self._tool_call_id = self._fnc_name = self._fnc_raw_arguments = None

                if tool.function.name:
                    self._tool_index = tool.index
                    self._tool_call_id = tool.id
                    self._fnc_name = tool.function.name
                    self._fnc_raw_arguments = tool.function.arguments or ""
                elif tool.function.arguments:
                    self._fnc_raw_arguments += tool.function.arguments  # type: ignore

                if call_chunk is not None:
                    return call_chunk

        if choice.finish_reason in ("tool_calls", "stop") and self._tool_call_id:
            call_chunk = llm.ChatChunk(
                id=id,
                delta=llm.ChoiceDelta(
                    role="assistant",
                    content=delta.content,
                    tool_calls=[
                        llm.FunctionToolCall(
                            arguments=self._fnc_raw_arguments or "",
                            name=self._fnc_name or "",
                            call_id=self._tool_call_id or "",
                        )
                    ],
                ),
            )
            self._tool_call_id = self._fnc_name = self._fnc_raw_arguments = None
            return call_chunk

        return llm.ChatChunk(
            id=id,
            delta=llm.ChoiceDelta(content=delta.content, role="assistant"),
        )
# Agent Orchestration Framework - Necessary Requirements:
1. Open source - 
    - good community support(star, fork)
    - stable version, 
2. integrate with local AI models
3. Configurable/Features 
    - Low-latency - overall - less than 1 sec. - streaming, 
    - Speech to Text - VAD, intrupption handling, multilingual
    - llm - act as call centre agent
    - Text to Speech - Multilingual/regional, natural voice
4. Integration with peripherial systems like PJSIP, Asterisk, IVR system



# Basic improvement
- uvicorn + FastAPI server to reduce ~100 ms

# STT
* python server with "openai/whisper-large-v3-turbo" = was better
* with whisper.cpp - quantised model - fast, but less precision.
- large-v3-turbo.bin is not that good
- large-v3-q5_0.bin is similar


# LLM
- Quantized model - reduced time to 1/10
- token size reduced to 56 - 1-2 sentence : helped reduce ~100 ms
- model configs: Llama.from_pretrained(...) call.
 - n_batch = 64, #  controls how many tokens are processed in parallel.  # good balance for 24GB GPU, can go higher (try 128)
 - n_threads=8  # or equal to vCPUs available
 - n_gpu_layers to max( like 100)
- llm("Warmup prompt", max_tokens=1)
Latency - 0.2-0.4 sec

## Llama-server:
* faster,
* but do not adhere to max token - just cuts off the response after 64 token
### With ./bin/llama-server -m ~/models/gemma/gemma-3-4b-it-q4_0.gguf -ngl 100 -c 2048 --no-webui --mlock --log-timestamps -v --host 0.0.0.0 --port 8080
- prompt eval time = 18.27 ms / 17 tokens (~1.07 ms per token)
- eval time        = 619.35 ms / 64 tokens (~9.68 ms per token)
- total time       = 637.62 ms / 81 tokens

### With 1b model:
- prompt eval time =      11.61 ms /    19 tokens (    **0.61 ms per token**,  1637.08 tokens per second)
- eval time =     308.67 ms /    64 tokens (    **4.82 ms per token**,   207.34 tokens per second)

- total time =     320.27 ms /    83 tokens

### LLM Performance
| LLM | Prompt Length basis | response token basis latency|
------|---|------------|
|Gemma3-4b-it - llama-cpp-python| ||
| Gemma3-4b-it - llama-cpp| 1ms/token | 10 ms/token|
| Gemma3-12b-it - llama-cpp|  1 ms/token | 21 ms/token|
|TheBloke/deepseek-llm-7B-chat-GGUF| 0.7 ms/token | 12 ms/token|
|microsft/phi-4.gguf|1 ms/token | 22 ms/token|

huggingface-cli download TheBloke/phi-2-GGUF phi-2.Q4_K_M.gguf --local-dir . --local-dir-use-symlinks False



# TODO
- Truncating history - to reduce prompt length
- prompt engineering
    - no smiley [Done]
    - no * [Done]
    - one question at a time
    - shorter reply
- streaming on
    - Fast API also: 
        from fastapi.responses import StreamingResponse

        @app.post("/api/chat/")
        async def chat(request: ChatRequest):
            def stream_generator():
                for output in llm(conversation, stream=True, **generation_args):
                    yield output["choices"][0]["text"]

            return StreamingResponse(stream_generator(), media_type="text/plain")
- explore Quantized LLMs that have lower latency and good for conversation/agentic function: 
    - mistral-7b-instruct-q4_0
    - Phi-2
- Fine tuning for cyber-security related incidents.




## TTS:
- not able to pronounce **?**
- [**'(Alarmed)',** 'I apologize, but I must politely decline.']

### solution:
- model.tts(
    text=input_text,
    speaker=speaker_id,
    max_decoder_steps=2000,  # Reduce from 10,000
)

## Judging speech quality - naturalness
* TTS - **en** models Ranked
    |name| RTF | audio quality | clarity | naturalness|
    -----|------|--|---|--|
    |tacotron2-DDC_ph| 0.06| good| clear|same|
    |vits-neon | 0.05 | good | clear | same|
    |vits| 0.1 | good|clear|same|
    |overflow | 0.1 | medium | clear| same|
    |fast_pitch | 0.06| break | clear | similar - pitch higher |
    | neural_hmm| - |breaking voice| not clear| same|

# Kokoro TTS - good - with speed
| language | processing_time | quality | clarity| naturalness|
|----| ---|---|----|---|
| af_heart | 0.1-0.2 | great | great | better|
|af_sarah | same | great | great | much better|
| af_alloy | same | great | great| good|
| af_bella | 0.1 | good | fast| good|
|af_aoede| same | same | same| same
| bf_emma | same | low| low | good| 
|af_nicole| same | good | great | sexy|
|af_kore| |bad|


## Hindi
|am_psi| 0.1 sec| great | great| great|
|am_omega| 0.1 sec| good| good| good|
|af_alpha | 0.1 sec| good | bad(Date, amount) | good
|af_beta| same| average | average | average|




# GPU efficient for handling bfloat16 operations - NVIDIA RTX

## Livekit Resources:
1. https://docs.livekit.io/agents/ops/deployment/
    - worker pool model suited for container orchestration
    - **Each worker — an instance of python main.py start** — registers with LiveKit server.
    - The workers themselves spawn a new sub-process for each job(dispatched by livekit-server)
    - Workers use a WebSocket connection
    - LiveKit recommends 4 cores and 8GB of memory for every 25 concurrent sessions as a starting rule
    - Load balancing by livekit server - Round robin
    - Worker availability is defined by the load_fnc and load_threshold parameters in the WorkerOptions configuration.
        - The load_fnc must return a value between 0 and 1, indicating how busy the worker is. load_threshold is the load value above which the worker stops accepting new jobs.
    - A LiveKit session is often referred to simply as a "room."
    - Worker lifecycle
        - Worker registration & wait
        - On Job Request by User: Agent dispatch - worker starts a new process to handle the job
        - Job : initiated by **entrypoint function**
        - LiveKit session close: automatically when the last non-agent participant leaves.
    - Additional worker feature:
        - Workers automatically exchange availability with livekit server - enabling load balancing of incoming requests.
        - Each worker can run multiple jobs simultaneously - **separate process** -  If one crashes, it won’t affect others running on the same worker.
    - Agent Dispatch:
        - Automatic
        - Explicit - through workerOption by specifying agent-name - more control over behaviour
        - SIP dispatch rules - can define one or more agents using the **room_config.agents** field.
            - LiveKit recommends explicit agent dispatch; as it allows multiple agents within a single project.
        - Via API 
    - The job.metadata passed to the agent includes the metadata set in the dispatch request
        - async def entrypoint(ctx: JobContext):
            - logger.info(f"job metadata: {ctx.job.metadata}")
    - Worker Options
    - Entrypoint:
        -  runs before the agent joins the room





## Resources that helped:
1. https://anakin.ai/blog/how-to-make-ollama-faster/
2. 



# TODO: 14th April 2025: before demo
1. explore better english TTS for more human like voice
2. multiple session -
2. explore hindi/marathi options.




# Decison on how to support multilingual option for user
## Options - Pros and Cons:
* Best case scenario: Single Agent, Both in multi-language
    - Run a lightweight audio language classifier (e.g., speechbrain/lang-id-voxlingua107-ecapa) => to classify the audio
    - Give input to whisper and specify language for precise STT
    - You can expect around a 20–30% relative reduction in errors
    * Pros
        - Seamless experience (no room switch)
        - Better for switching mid-convo
    * cons
        - More complex STT/TTS logic
        - Need best STT - better the STT, better the interaction/experience
        - Need TTS that can speak in multiple language effortlessly
1. Single Agent - No Call transfer; Both in one language
    * Pros
        - Clean separation of pipelines
        - Easy to manage specialized models per room
    * Cons:
        - Requires reconnect logic (token issuance, room switching)
        - Small delay/friction in transition
2. Single Agent - No call transfer; User in Multi-language
    * cons:
        - - Need an STT with very high high precision 
3. Single Agent - Can switch language dynamically based on keywords like when user says "Hindi", it switches to Hindi mode.
    * Pros
        - Feels very natural
        - No need to break or reconnect
    * Cons:
        - engineering effort : detecting the keywords
4. Multiple Agent - each for one language; Both in one language


### going with option 1, with focus on moving to the best case scenario
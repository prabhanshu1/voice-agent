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

# To Improve

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
### With ./bin/llama-server -m ~/models/gemma/gemma-3-4b-it-q4_0.gguf -ngl 100 -c 2048 --no-webui --mlock --log-timestamps -v --host 0.0.0.0 --port 8080
- prompt eval time = 18.27 ms / 17 tokens (~1.07 ms per token)
- eval time        = 619.35 ms / 64 tokens (~9.68 ms per token)
- total time       = 637.62 ms / 81 tokens

### With 1b model:
- prompt eval time =      11.61 ms /    19 tokens (    0.61 ms per token,  1637.08 tokens per second)
- eval time =     308.67 ms /    64 tokens (    4.82 ms per token,   207.34 tokens per second)
- total time =     320.27 ms /    83 tokens

# TODO
- Truncating history - to reduce prompt length
- prompt engineering
    - no smiley
    - no * 
- streaming on
    - Fast API also: 
        from fastapi.responses import StreamingResponse

        @app.post("/api/chat/")
        async def chat(request: ChatRequest):
            def stream_generator():
                for output in llm(conversation, stream=True, **generation_args):
                    yield output["choices"][0]["text"]

            return StreamingResponse(stream_generator(), media_type="text/plain")
- Other faster quantized model : mistral-7b-instruct-q4_0



# llama-cpp - cpp based server
slot         init: id  0 | task -1 | new slot n_ctx_slot = 4096
main: model loaded
main: chat template, chat_template: {{ bos_token }} {%- if messages[0]['role'] == 'system' -%} {%- if messages[0]['content'] is string -%} {%- set first_user_prefix = messages[0]['content'] + '\n' -%} {%- else -%} {%- set first_user_prefix = messages[0]['content'][0]['text'] + '\n' -%} {%- endif -%} {%- set loop_messages = messages[1:] -%} {%- else -%} {%- set first_user_prefix = "" -%} {%- set loop_messages = messages -%} {%- endif -%} {%- for message in loop_messages -%} {%- if (message['role'] == 'user') != (loop.index0 % 2 == 0) -%} {{ raise_exception("Conversation roles must alternate user/assistant/user/assistant/...") }} {%- endif -%} {%- if (message['role'] == 'assistant') -%} {%- set role = "model" -%} {%- else -%} {%- set role = message['role'] -%} {%- endif -%} {{ '<start_of_turn>' + role + '\n' + (first_user_prefix if loop.first else "") }} {%- if message['content'] is string -%} {{ message['content'] | trim }} {%- elif message['content'] is iterable -%} {%- for item in message['content'] -%} {%- if item['type'] == 'image' -%} {{ '<start_of_image>' }} {%- elif item['type'] == 'text' -%} {{ item['text'] | trim }} {%- endif -%} {%- endfor -%} {%- else -%} {{ raise_exception("Invalid content type") }} {%- endif -%} {{ '<end_of_turn>\n' }} {%- endfor -%} {%- if add_generation_prompt -%} {{'<start_of_turn>model\n'}} {%- endif -%}, example_format: '<start_of_turn>user
You are a helpful assistant

Hello<end_of_turn>
<start_of_turn>model
Hi there<end_of_turn>
<start_of_turn>user
How are you?<end_of_turn>
<start_of_turn>model
'
main: server is listening on http://127.0.0.1:8080 - starting the main loop
srv  update_slots: all slots are idle




## TTS:
- not able to pronounce **?**
- [**'(Alarmed)',** 'I apologize, but I must politely decline.']

### solution:
- model.tts(
    text=input_text,
    speaker=speaker_id,
    max_decoder_steps=2000,  # Reduce from 10,000
)




# GPU efficient for handling bfloat16 operations - NVIDIA RTX
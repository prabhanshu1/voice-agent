#! /bin/bash

nohup ./whisper.cpp/build/bin/whisper-server -m whisper.cpp/models/ggml-large-v3-turbo.bin --host 0.0.0.0 --port 8000 -t $(nproc) -ps -pc -pr -l en &

nohup ./llama.cpp/build/bin/llama-server -m ~/models/gemma/gemma-3-4b-it-q4_0.gguf -ngl 100 -c 2048 -b 2048 --no-webui --mlock --threads $(nproc) --chat-template gemma --host 0.0.0.0 --port 8080 &



cd ~/meet
nohup pnpm dev &

nohup livekit-server --dev --bind 0.0.0.0 &

# Terminal 1
./start_voice_agent.sh
ngrok start --all

# Terminal 2
source .venvTTS/bin/activate && cd local-TTS 
LANG_CODE=a VOICE=af_sarah uvicorn kokoroTTS:app --host 0.0.0.0 --port 5002


# Terminal 3
source .venvVoiceAgent/bin/activate
python voice-agent/backend/agent.py dev

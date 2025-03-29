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


|Aspects | LiveKit | PipeCat|
| -------- | ------- | -------|
|Open Source| ✅ ✅| ✅ ❌|
|local AI models| ✅ more flexible| ✅ less flexible in STT and TTS



Pipecat is better for AI orchestration - if we are using microservices, as it can stream among the AI models running on different hosts.
However, Livekit is better for low latency voice transfer from user to the system and vice-versa. Also, it has support to integrate with Asterisk for telephony. Can stream llm output to tts through Ollama.stream().

Currently, since we have done some research and dev on Livekit - should continue - as deadline is nearing. 
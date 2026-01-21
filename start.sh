#!/bin/bash

# 1. Start Redis in the background
redis-server --daemonize yes

# 2. Start the Worker (Updated path)
# We use "-m" to run it as a module from the root folder
python -u -m ai_engine.worker &

# 3. Start the Website
uvicorn main:app --host 0.0.0.0 --port 7860

FROM python:3.12-slim

# 1. Install Redis (Critical for your graph caching)
USER root
RUN apt-get update && apt-get install -y redis-server && rm -rf /var/lib/apt/lists/*

# Set the working directory to /code
WORKDIR /code

# Copy requirements and install
COPY ./requirements.txt /code/requirements.txt
RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

# Set up a new user named "user" with user ID 1000
RUN useradd -m -u 1000 user

# Switch to the "user" user
USER user
ENV PYTHONUNBUFFERED=1
# Set home to the user's home directory
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

# Set the working directory to the user's home directory
WORKDIR $HOME/app

# Copy the current directory contents into the container
COPY --chown=user . $HOME/app

# 2. Make the start script executable
# (We do this after copying)
RUN chmod +x start.sh

# Expose port 7860 for Hugging Face Spaces
EXPOSE 7860

# 3. Run the start script instead of just uvicorn
CMD ["./start.sh"]
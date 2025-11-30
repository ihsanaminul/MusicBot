
FROM python:3.12-slim
WORKDIR /app

# Install FFmpeg and Playwright dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ffmpeg \
    git \
    chromium && \
    rm -rf /var/lib/apt/lists/*


COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Install playwright and its dependencies
RUN pip install playwright && playwright install-deps && playwright install

COPY . .

CMD ["python", "playify.py"]

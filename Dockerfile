FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends libsodium23 \
    && rm -rf /var/lib/apt/lists/*
RUN useradd --uid 10001 --create-home legitzk && install -d -o legitzk -g legitzk -m 0700 /data
WORKDIR /opt/legitzk
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 LEGITZK_DATA=/data
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py protocol.py rangeproof.py verify.py ./
COPY web/ web/
COPY benchmarks/summary.json benchmarks/summary.json
USER legitzk
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--no-access-log"]

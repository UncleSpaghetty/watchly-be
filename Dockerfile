FROM python:3.12-slim AS builder
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /src
COPY requirements.txt ./
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade "pip>=26.2.2" \
    && /opt/venv/bin/pip install -r requirements.txt

FROM python:3.12-slim
ENV PATH="/opt/venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN useradd --system --uid 10001 --create-home watchly
WORKDIR /
COPY --from=builder /opt/venv /opt/venv
COPY app /app
COPY migrations /migrations
COPY run.py /run.py
COPY run.sh /run.sh
RUN chmod +x /run.sh \
    && chown -R watchly:watchly /app /migrations /run.py /run.sh
USER watchly
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --retries=4 CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/live', timeout=3)"]
CMD ["/bin/sh", "/run.sh"]

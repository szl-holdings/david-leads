FROM python:3.11-slim
WORKDIR /code
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN useradd --create-home --uid 10001 david-leads
COPY --chown=david-leads:david-leads app ./app
COPY --chown=david-leads:david-leads PUBLICATION_READINESS.md PUBLIC_DATA_OPERATING_MODEL.md SPACE_PROVENANCE.json ./
COPY --chown=david-leads:david-leads THIRD_PARTY_NOTICES.md ./
COPY --chown=david-leads:david-leads research/COMPETITIVE_SYNTHESIS_2026-08-26.md ./research/COMPETITIVE_SYNTHESIS_2026-08-26.md
COPY --chown=david-leads:david-leads ops/credential-rotation.md ./ops/credential-rotation.md
USER david-leads
EXPOSE 7860
# HF Spaces inject secrets as env vars: SZL_COSIGN_PRIVATE_PEM, SZL_COSIGN_PUBLIC_PEM,
# DAVID_USER, DAVID_PASS, DAVID_ACCESS_KEY, DAVID_DATABASE_URL, CENSUS_API_KEY.
# Production readiness requires POSTGRES_READY or an absolute durable file path.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:7860/readyz', timeout=3).read()"]
CMD ["uvicorn", "app.server:app", "--host", "0.0.0.0", "--port", "7860"]

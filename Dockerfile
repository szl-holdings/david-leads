FROM python:3.11-slim
WORKDIR /code
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN useradd --create-home --uid 10001 david-leads
COPY --chown=david-leads:david-leads app ./app
COPY --chown=david-leads:david-leads PUBLICATION_READINESS.md PUBLIC_DATA_OPERATING_MODEL.md SPACE_PROVENANCE.json ./
USER david-leads
EXPOSE 7860
# HF Spaces inject secrets as env vars: SZL_COSIGN_PRIVATE_PEM, SZL_COSIGN_PUBLIC_PEM,
# DAVID_USER, DAVID_PASS, DAVID_ACCESS_KEY, CENSUS_API_KEY. Production readiness
# also requires an absolute, durable DAVID_DEAL_DESK_PATH.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:7860/readyz', timeout=3).read()"]
CMD ["uvicorn", "app.server:app", "--host", "0.0.0.0", "--port", "7860"]

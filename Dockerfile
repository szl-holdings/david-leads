FROM python:3.11-slim
WORKDIR /code
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
EXPOSE 7860
# HF Spaces inject secrets as env vars: SZL_COSIGN_PRIVATE_PEM, SZL_COSIGN_PUBLIC_PEM,
# DAVID_USER, DAVID_PASS, DAVID_ACCESS_KEY, CENSUS_API_KEY (all optional; app degrades honestly)
CMD ["uvicorn", "app.server:app", "--host", "0.0.0.0", "--port", "7860"]

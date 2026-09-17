FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONUTF8=1
COPY pyproject.toml ./
COPY src ./src
COPY mcp_server ./mcp_server
ARG INSTALL_MODELS=true
RUN pip install --no-cache-dir . && if [ "$INSTALL_MODELS" = "true" ]; then pip install --no-cache-dir '.[models]'; fi
COPY config ./config
COPY data ./data
RUN mkdir -p /app/runtime
EXPOSE 8000 8001
CMD ["python", "-m", "uvicorn", "bidpilot.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]

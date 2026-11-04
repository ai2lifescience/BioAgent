FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt pytest
# Ship the complete pinned distribution: execution workers have no network.
RUN apt-get update && apt-get install -y --no-install-recommends default-jre-headless curl ca-certificates \
    && curl -fsSL --retry 3 https://github.com/nextflow-io/nextflow/releases/download/v25.10.9/nextflow-25.10.9-dist -o /usr/local/bin/nextflow \
    && echo '8f3e6efe3b700c298aedf45ba2d5ec0d17bd5f480362b1b46145ea6bfbe46987  /usr/local/bin/nextflow' | sha256sum -c - \
    && chmod 755 /usr/local/bin/nextflow && rm -rf /var/lib/apt/lists/*
COPY harness /app/harness
COPY auth /app/auth
COPY web_bridge /app/web_bridge
COPY isolation /app/isolation
COPY models /app/models
COPY tools /app/tools
RUN find /app -type d -name __pycache__ -prune -exec rm -rf {} + && chmod -R a+rX /app
LABEL io.bioagent.worker-protocol="3"
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/tmp USER=worker LOGNAME=worker AGENT_AUTH_MODE=local
ENV NXF_OFFLINE=true NXF_HOME=/tmp/nextflow NXF_OPTS="-Xms128m -Xmx512m -XX:ActiveProcessorCount=1"
USER 10001:10001
ENTRYPOINT ["python", "-m", "isolation.worker"]

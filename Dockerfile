FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml constraints.txt ./
COPY src ./src

RUN pip install --no-cache-dir -c constraints.txt .

ENV PORT=8080
EXPOSE 8080

CMD ["python", "-m", "deadman.service"]

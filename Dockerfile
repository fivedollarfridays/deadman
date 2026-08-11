FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml constraints.txt ./
COPY src ./src

# `.[firestore]`, not `.`, because the deployed service stores ingested
# evidence durably and `FirestoreEvidenceStore` raises `StoreSdkMissing` at
# construction when the SDK is absent — fail-closed, which means the image
# must carry it or the service will not start. The test suite still installs
# neither: see the note beside the extra in pyproject.toml.
RUN pip install --no-cache-dir -c constraints.txt '.[firestore]'

ENV PORT=8080
EXPOSE 8080

CMD ["python", "-m", "deadman.service"]

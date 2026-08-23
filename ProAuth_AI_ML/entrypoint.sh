#!/bin/sh
# Fetches model artifacts from S3 (if S3_MODEL_BUCKET is set) before handing
# off to the real CMD. See scripts/fetch_models.py for why this runs as a
# separate process, before uvicorn/torch ever load.
set -e

if [ -n "$S3_MODEL_BUCKET" ]; then
  python /app/scripts/fetch_models.py
fi

exec "$@"

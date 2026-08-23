"""
Fetch model artifacts from S3 into the exact hardcoded paths this image's
loading code already expects (ml/model.py's MODEL_PATH,
priority_intelligence/config.py's RANKER_PATH/RANKER_METADATA_PATH).

Runs as a standalone process invocation from entrypoint.sh, BEFORE uvicorn
(and therefore before anything imports torch/sentence-transformers) even
starts — see policy-rag/main.py and priority_intelligence/ranker.py's own
docstrings for why priority_intelligence's XGBoost-backed model must never
share a process with torch until after it's already loaded. Doing the fetch
as a separate process here sidesteps that constraint entirely rather than
having to respect it: nothing here imports either library.

No changes needed to ml/model.py or priority_intelligence/ranker.py/config.py
— both already load from fixed, hardcoded local paths; this script's only
job is to make sure a real file exists at each path before the app boots.
"""
import os
import sys

import boto3
from botocore.exceptions import ClientError

# (bucket-relative key, destination path inside the container)
ARTIFACTS = [
    ("proauth_best_model.pkl", "/app/policy-rag/ml/models/proauth_best_model.pkl"),
    ("priority_ranker.joblib", "/app/priority_intelligence/models/priority_ranker.joblib"),
    ("priority_ranker_metadata.json", "/app/priority_intelligence/models/priority_ranker_metadata.json"),
]


def main():
    bucket = os.environ.get("S3_MODEL_BUCKET")
    if not bucket:
        # No bucket configured — local dev / a bind-mount already put the
        # real files in place. Nothing to do; not an error.
        print("[fetch_models] S3_MODEL_BUCKET not set — skipping S3 fetch.")
        return

    prefix = os.environ.get("S3_MODEL_PREFIX", "models").strip("/")
    client = boto3.client("s3")

    for key_name, dest_path in ARTIFACTS:
        key = f"{prefix}/{key_name}" if prefix else key_name
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        try:
            client.download_file(bucket, key, dest_path)
        except ClientError as exc:
            print(f"[fetch_models] FAILED to fetch s3://{bucket}/{key} -> {dest_path}: {exc}", file=sys.stderr)
            sys.exit(1)
        size = os.path.getsize(dest_path)
        print(f"[fetch_models] OK s3://{bucket}/{key} -> {dest_path} ({size} bytes)")


if __name__ == "__main__":
    main()

"""Prediction interface — model-agnostic, reads whatever artifact
train.py saved (LogisticRegression or RandomForest, doesn't matter here:
both expose .predict_proba() and the artifact always carries its own
decision_threshold, features list, and class mapping)."""
import pickle
import pandas as pd

import config

FEATURES = config.FEATURES
MODEL_PATH = config.MODEL_PATH


def load_artifact():
    with open(MODEL_PATH, "rb") as f:
        return pickle.load(f)


def predict(request: dict) -> dict:
    artifact = load_artifact()
    x = pd.DataFrame([{k: request[k] for k in FEATURES}])
    proba = float(artifact["model"].predict_proba(x)[0, 1])
    label = "APPROVE" if proba >= artifact["decision_threshold"] else "PEND"
    return {
        "approve_probability": proba,
        "decision": label,
        "threshold": artifact["decision_threshold"],
        "model_name": artifact["model_name"],
    }


if __name__ == "__main__":
    example = {
        "policy_score": 82.0,
        "documentation_score": 100.0,
        "clinical_evidence_score": 75.0,
        "diagnosis_supported": 1,
    }
    print(predict(example))

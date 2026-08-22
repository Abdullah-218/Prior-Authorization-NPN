from pathlib import Path
BASE_DIR=Path(__file__).resolve().parent
ROOT_DIR=BASE_DIR.parent
TRAINING_SET_PATH=BASE_DIR/'data'/'priority_training_set_PEND_ONLY.csv'
QUEUE_SNAPSHOT_PATH=BASE_DIR/'data'/'pending_queue_snapshot_PEND_ONLY.csv'
RANKER_PATH=BASE_DIR/'models'/'priority_ranker.joblib'
RANKER_METADATA_PATH=BASE_DIR/'models'/'priority_ranker_metadata.json'
RANDOM_STATE=42
SLA_HOURS_BY_URGENCY={'routine':72.0,'urgent':24.0,'emergency':4.0}
URGENCY_WEIGHT={'routine':1.0,'urgent':2.0,'emergency':3.0}
CARE_SETTING_WEIGHT={'Outpatient':1.0,'Ambulatory':1.05,'Inpatient':1.35,'Emergency Department':1.6}
SLA_BREACH_OVERRIDE_HOURS=2.0

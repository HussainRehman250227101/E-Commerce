"""Train XGBoost after labeling query/product relevance examples."""

import csv
from collections import Counter
from pathlib import Path

import xgboost as xgb

APP_DIR = Path(__file__).resolve().parent
DATA_PATH = APP_DIR / "data" / "ranking_training.csv"
OUTPUT_PATH = APP_DIR / "artifacts" / "xgboost_ranker.json"
FEATURES = ["price", "rating", "price_rank", "rating_rank", "text_relevance", "in_stock", "brand_match", "budget_fit"]


def main():
    if not DATA_PATH.exists():
        raise SystemExit(f"Create {DATA_PATH} from data/ranking_training_template.csv and add judged examples first.")
    with DATA_PATH.open(newline="", encoding="utf-8-sig") as file:
        rows = sorted(csv.DictReader(file), key=lambda row: row["query_id"])
    if len(rows) < 4:
        raise SystemExit("Add at least four candidate rows across two or more query_id groups.")
    counts = Counter(row["query_id"] for row in rows)
    if len(counts) < 2 or any(count < 2 for count in counts.values()):
        raise SystemExit("Each of at least two query_id groups needs at least two candidates.")
    try:
        x_values = [[float(row[key]) for key in FEATURES] for row in rows]
        y_values = [float(row["relevance"]) for row in rows]
    except (KeyError, TypeError, ValueError) as exc:
        raise SystemExit(f"Invalid CSV feature or relevance: {exc}") from exc
    model = xgb.XGBRanker(
        objective="rank:ndcg", eval_metric="ndcg@5", n_estimators=100,
        max_depth=4, learning_rate=0.05, subsample=0.9, colsample_bytree=0.9, random_state=42,
    )
    model.fit(x_values, y_values, group=list(counts.values()))
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    model.save_model(OUTPUT_PATH)
    print(f"Saved ranker to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()

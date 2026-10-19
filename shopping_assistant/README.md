# Shopping Assistant starter

Small Django REST Framework endpoint for natural-language product search. It does not import or modify `store/recommender.py`.

## API
POST `/store/assistant/chat/`
```json
{ "message": "Find the cheapest highly rated iPhone" }
```

The response contains `message`, `intent`, `products` (real database IDs, prices, ratings, images and frontend URLs), `filters_applied`, and `ranking_strategy`.

## DistilBERT
The starter model is based on `distilbert/distilbert-base-uncased`. Fine-tune it from the repository root:
```bash
python -m shopping_assistant.nlp.train_intent
```
Training data lives in `nlp/data/intent_examples.jsonl`. The saved model is written to `shopping_assistant/artifacts/intent_model`. Set `SHOPPING_INTENT_MODEL_PATH` if you store it elsewhere. Until the model artifact exists, intent classification falls back to simple rules. Budget, brand, model and rating extraction currently use lightweight rules.

The dataset is only a starter and its validation result is not evidence of production accuracy; add varied examples and evaluate against a held-out set.

## Ranking
Explicit cheapest and top-rated queries respect the user's requested sort. Other queries use the trained XGBoost ranker if `shopping_assistant/artifacts/xgboost_ranker.json` (or `SHOPPING_XGBOOST_MODEL_PATH`) exists; otherwise they use a clear rating/value baseline.

XGBoost needs real labeled query/product examples. Copy `data/ranking_training_template.csv` to `data/ranking_training.csv`, add one row per candidate and a relevance label, and run `python -m shopping_assistant.train_ranker`. Do not train on invented labels.

## Setup
The main requirements file includes PyTorch, Transformers, scikit-learn and XGBoost. No database migration is required. Model files are not committed to Git.

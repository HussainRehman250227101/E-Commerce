"""Fine-tune DistilBERT for shopping intents from the repository root."""

import json
import random
from pathlib import Path

import torch
from sklearn.model_selection import train_test_split
from torch.utils.data import DataLoader, Dataset
from transformers import AutoModelForSequenceClassification, AutoTokenizer, get_linear_schedule_with_warmup

CHECKPOINT = "distilbert/distilbert-base-uncased"
APP_DIR = Path(__file__).resolve().parents[1]
DATA_PATH = Path(__file__).resolve().parent / "data" / "intent_examples.jsonl"
OUTPUT_PATH = APP_DIR / "artifacts" / "intent_model"
SEED, MAX_LENGTH, BATCH_SIZE, EPOCHS = 42, 64, 8, 3


class IntentDataset(Dataset):
    def __init__(self, texts, labels, tokenizer, label_to_id):
        self.tokens = tokenizer(texts, max_length=MAX_LENGTH, truncation=True, padding="max_length", return_tensors="pt")
        self.labels = [label_to_id[label] for label in labels]

    def __len__(self):
        return len(self.labels)

    def __getitem__(self, index):
        item = {key: value[index] for key, value in self.tokens.items()}
        item["labels"] = torch.tensor(self.labels[index], dtype=torch.long)
        return item


def main():
    random.seed(SEED)
    torch.manual_seed(SEED)
    records = [json.loads(line) for line in DATA_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    texts, labels = [r["text"] for r in records], [r["intent"] for r in records]
    names = sorted(set(labels))
    label_to_id = {label: idx for idx, label in enumerate(names)}
    id_to_label = {idx: label for label, idx in label_to_id.items()}
    train_x, val_x, train_y, val_y = train_test_split(texts, labels, test_size=0.2, random_state=SEED, stratify=labels)

    tokenizer = AutoTokenizer.from_pretrained(CHECKPOINT)
    model = AutoModelForSequenceClassification.from_pretrained(
        CHECKPOINT, num_labels=len(names), label2id=label_to_id, id2label=id_to_label
    )
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device)
    train_loader = DataLoader(IntentDataset(train_x, train_y, tokenizer, label_to_id), batch_size=BATCH_SIZE, shuffle=True)
    val_loader = DataLoader(IntentDataset(val_x, val_y, tokenizer, label_to_id), batch_size=BATCH_SIZE)
    optimizer = torch.optim.AdamW(model.parameters(), lr=3e-5)
    steps = max(1, len(train_loader) * EPOCHS)
    scheduler = get_linear_schedule_with_warmup(optimizer, int(steps * 0.1), steps)

    for epoch in range(EPOCHS):
        model.train()
        loss_sum = 0.0
        for batch in train_loader:
            batch = {key: value.to(device) for key, value in batch.items()}
            optimizer.zero_grad(set_to_none=True)
            loss = model(**batch).loss
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            scheduler.step()
            loss_sum += float(loss.item())

        model.eval()
        correct = total = 0
        with torch.no_grad():
            for batch in val_loader:
                batch = {key: value.to(device) for key, value in batch.items()}
                logits = model(input_ids=batch["input_ids"], attention_mask=batch["attention_mask"]).logits
                correct += int((logits.argmax(dim=1) == batch["labels"]).sum().item())
                total += int(batch["labels"].shape[0])
        print(f"Epoch {epoch + 1}/{EPOCHS}: loss={loss_sum / max(len(train_loader), 1):.4f}, val_accuracy={correct / max(total, 1):.3f}")

    OUTPUT_PATH.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(OUTPUT_PATH)
    tokenizer.save_pretrained(OUTPUT_PATH)
    print(f"Saved intent model to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()

"""Train the 5-second window classifier.

    python -m src.train_window --data data/full_features.csv --model models/window_model.joblib

Evaluation holds out whole capture files (one per app), so test windows come
from sessions the model never saw. The saved model is then refit on all files.
"""
import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score

from src.window_features import COLUMNS


def make_model():
    return RandomForestClassifier(n_estimators=300, class_weight="balanced", n_jobs=-1, random_state=42)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data", default="data/full_features.csv")
    p.add_argument("--model", default="models/window_model.joblib")
    p.add_argument("--labels", nargs="*", help="only use these apps, e.g. --labels youtube web")
    args = p.parse_args()

    df = pd.read_csv(args.data, encoding="utf-8-sig")
    if args.labels:
        df = df[df["app_label"].isin(args.labels)]
    labels = sorted(df["app_label"].unique())
    X, y = df[COLUMNS], df["app_label"]

    # Hold out one capture file per app (needs >= 2 files per app).
    rng = np.random.default_rng(42)
    test_files = [rng.choice(sorted(g.unique())) for _, g in df.groupby("app_label")["pcap_filename"]
                  if g.nunique() >= 2]
    is_test = df["pcap_filename"].isin(test_files)
    print(f"apps={labels}\ntest files={test_files}\ntrain={(~is_test).sum()} test={is_test.sum()} windows\n")

    if is_test.any():
        m = make_model().fit(X[~is_test], y[~is_test])
        pred = m.predict(X[is_test])
        print(f"accuracy={accuracy_score(y[is_test], pred):.3f}  macro-F1={f1_score(y[is_test], pred, average='macro'):.3f}")
        print(classification_report(y[is_test], pred, zero_division=0))
        print(pd.DataFrame(confusion_matrix(y[is_test], pred, labels=labels), index=labels, columns=labels), "\n")

    model = make_model().fit(X, y)
    imp = pd.Series(model.feature_importances_, index=COLUMNS).sort_values(ascending=False)
    print("feature importance:\n" + imp.round(3).to_string() + "\n")

    Path(args.model).parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": model, "columns": COLUMNS, "labels": labels}, args.model)
    # Plain-text copy of the input contract for teammates.
    Path(args.model).with_suffix(".json").write_text(
        json.dumps({"columns": COLUMNS, "labels": labels, "window_sec": 5}, indent=2), encoding="utf-8")
    print(f"saved (trained on all {len(df)} windows) -> {args.model}")


if __name__ == "__main__":
    main()

"""Train and compare classifiers on the flow-feature CSV.

    python -m src.train --data data/features.csv --model models/model.joblib

--no-port drops server_port so the model must rely on traffic shape only.
"""
import argparse
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder

DROP = ["label", "source"]


def build_models():
    models = {"random_forest": RandomForestClassifier(n_estimators=300, n_jobs=-1, random_state=42)}
    try:
        from xgboost import XGBClassifier

        models["xgboost"] = XGBClassifier(n_estimators=300, max_depth=6, learning_rate=0.1, random_state=42)
    except ImportError:
        print("xgboost not installed - skipping (pip install xgboost)")
    return models


def split(df, y, by_file: bool):
    # Splitting by capture file keeps flows from the same session out of both
    # sets; otherwise accuracy is optimistic. Needs >= 2 files per label.
    if by_file and df.groupby("label")["source"].nunique().min() >= 2:
        # Hold out ~25% of each app's capture files (at least one), so every
        # app appears in both train and test.
        rng = np.random.default_rng(42)
        test_files = set()
        for _, files in df.groupby("label")["source"].unique().items():
            files = rng.permutation(files)
            test_files.update(files[: max(1, round(len(files) * 0.25))])
        is_test = df["source"].isin(test_files).to_numpy()
        print("Split: by capture file")
        return np.where(~is_test)[0], np.where(is_test)[0]
    print("Split: random stratified (use >= 2 captures per app for a file-wise split)")
    idx = range(len(df))
    return train_test_split(list(idx), test_size=0.25, stratify=y, random_state=42)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data", default="data/features.csv")
    p.add_argument("--model", default="models/model.joblib")
    p.add_argument("--no-port", action="store_true")
    p.add_argument("--random-split", action="store_true", help="ignore capture files when splitting")
    args = p.parse_args()

    df = pd.read_csv(args.data)
    drop = DROP + (["server_port"] if args.no_port else [])
    X = df.drop(columns=drop)
    enc = LabelEncoder()
    y = enc.fit_transform(df["label"])

    tr, te = split(df, y, by_file=not args.random_split)
    X_tr, X_te, y_tr, y_te = X.iloc[tr], X.iloc[te], y[tr], y[te]
    print(f"train={len(tr)} test={len(te)} classes={list(enc.classes_)}\n")

    best_name, best_model, best_f1 = None, None, -1.0
    for name, model in build_models().items():
        model.fit(X_tr, y_tr)
        pred = model.predict(X_te)
        f1 = f1_score(y_te, pred, average="macro")
        print(f"== {name}: accuracy={accuracy_score(y_te, pred):.3f} macro-F1={f1:.3f}")
        print(classification_report(y_te, pred, target_names=enc.classes_, zero_division=0))
        print(pd.DataFrame(confusion_matrix(y_te, pred), index=enc.classes_, columns=enc.classes_), "\n")
        if f1 > best_f1:
            best_name, best_model, best_f1 = name, model, f1

    if hasattr(best_model, "feature_importances_"):
        imp = pd.Series(best_model.feature_importances_, index=X.columns).sort_values(ascending=False)
        print(f"Top features ({best_name}):\n{imp.head(10).to_string()}\n")

    Path(args.model).parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": best_model, "encoder": enc, "columns": list(X.columns)}, args.model)
    print(f"Saved best model ({best_name}, macro-F1={best_f1:.3f}) -> {args.model}")


if __name__ == "__main__":
    main()

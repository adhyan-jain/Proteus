"""Baseline Random Forest classifier + metrics."""
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, confusion_matrix


def train_classifier(X_train, y_train, n_estimators=100):
    clf = RandomForestClassifier(n_estimators=n_estimators, random_state=42, n_jobs=-1)
    clf.fit(X_train, y_train)
    return clf


def evaluate(clf, X_test, y_test, class_names):
    y_pred = clf.predict(X_test)
    report = classification_report(
        y_test, y_pred, target_names=class_names, output_dict=True, zero_division=0)
    cm = confusion_matrix(y_test, y_pred, labels=list(range(len(class_names))))
    macro_f1 = report["macro avg"]["f1-score"]
    return {"report": report, "confusion_matrix": cm.tolist(), "macro_f1": macro_f1,
            "y_pred": y_pred.tolist()}


def confidence_distribution(clf, X):
    """Max predicted-probability per sample -- used by the drift detector."""
    proba = clf.predict_proba(X)
    return proba.max(axis=1)

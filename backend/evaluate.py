import os
import sys
import pandas as pd
import numpy as np
from sklearn.metrics import classification_report, confusion_matrix, precision_recall_fscore_support

try:
    from models.text_model import check_and_rewrite_headline
except Exception:
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    from models.text_model import check_and_rewrite_headline


def safe_mkdir(path):
    try:
        os.makedirs(path, exist_ok=True)
    except Exception:
        pass


def _save_dataframe(df, path):
    try:
        df.to_csv(path, index=False)
        print(f"[INFO] Saved CSV: {path}")
    except Exception as e:
        print(f"[WARN] Failed to save CSV {path}: {e}")


def plot_evaluation(y_true, y_pred, summary_df, out_dir):
    try:
        import matplotlib
        import matplotlib.pyplot as plt
    except Exception as e:
        print(f"[PLOT] matplotlib not available: {e}")
        return

    backend = ""
    try:
        backend = matplotlib.get_backend().lower()
    except Exception:
        backend = ""
    non_interactive = ("agg" in backend) or ("inline" in backend)

    safe_mkdir(out_dir)

    try:
        cm = confusion_matrix(y_true, y_pred, labels=[0, 1])
        if cm.shape != (2, 2):
            new_cm = np.zeros((2, 2), dtype=int)
            for i, lab_i in enumerate([0, 1]):
                for j, lab_j in enumerate([0, 1]):
                    new_cm[i, j] = int(((np.array(y_true) == lab_i) & (np.array(y_pred) == lab_j)).sum())
            cm = new_cm

        
        total = cm.sum() if cm.size > 0 else 0
        accuracy = (int(np.trace(cm)) / int(total)) if total > 0 else 0.0

        fig_cm, ax_cm = plt.subplots(figsize=(5, 4))
        im = ax_cm.imshow(cm, interpolation='nearest')
        ax_cm.set_title(f"Confusion Matrix (Accuracy: {accuracy:.2%})")
        tick_labels = ["Not Misleading (0)", "Misleading (1)"]
        ax_cm.set_xticks([0, 1])
        ax_cm.set_yticks([0, 1])
        ax_cm.set_xticklabels(tick_labels, rotation=30, ha='right')
        ax_cm.set_yticklabels(tick_labels)
        ax_cm.set_ylabel("True label")
        ax_cm.set_xlabel("Predicted label")

        
        ax_cm.text(0.1, -0.12, f"Accuracy: {accuracy:.2%}", transform=ax_cm.transAxes,
                   ha='center', va='center', fontsize=10)

        thresh = cm.max() / 2.0 if cm.max() > 0 else 0.0
        for i in range(cm.shape[0]):
            for j in range(cm.shape[1]):
                ax_cm.text(j, i, format(int(cm[i, j]), 'd'),
                           ha="center", va="center",
                           fontsize=12,
                           color="white" if cm[i, j] > thresh else "black")
        fig_cm.tight_layout()
        cm_path = os.path.join(out_dir, "eval_confusion.png")
        try:
            fig_cm.savefig(cm_path, bbox_inches='tight')
            print(f"[PLOT] Saved confusion matrix to: {cm_path}")
        except Exception as e:
            print(f"[PLOT] Failed to save confusion matrix: {e}")
        if not non_interactive:
            try:
                plt.show()
            except Exception:
                pass
        plt.close(fig_cm)
    except Exception as e:
        print(f"[PLOT] Error while creating confusion matrix: {e}")

    try:
        metrics_df = summary_df.copy()
        metrics_df = metrics_df.set_index('class')
        required_metrics = ['precision', 'recall', 'f1']
        for m in required_metrics:
            if m not in metrics_df.columns:
                metrics_df[m] = 0.0
        labels = list(metrics_df.index.astype(str).tolist())
        values = [metrics_df.loc[l, required_metrics].astype(float).tolist() for l in labels]

        values_arr = np.array(values)

        n_classes = len(labels)
        n_metrics = len(required_metrics)

        fig_bar, ax_bar = plt.subplots(figsize=(8, 4.5))
        ind = np.arange(n_classes)
        total_width = 0.75
        width = total_width / n_metrics
        offsets = np.linspace(-total_width/2 + width/2, total_width/2 - width/2, n_metrics)

        bars = []
        for i, metric in enumerate(required_metrics):
            bar = ax_bar.bar(ind + offsets[i], values_arr[:, i], width, label=metric.capitalize())
            bars.append(bar)

            for rect in bar:
                h = rect.get_height()
                if 0.0 <= h <= 1.0:
                    txt = f"{h:.2%}"
                else:
                    txt = f"{h:.4g}"
                ax_bar.annotate(txt, xy=(rect.get_x() + rect.get_width() / 2, h),
                                xytext=(0, 4), textcoords="offset points",
                                ha='center', va='bottom', fontsize=9)

        ax_bar.set_ylabel("Score")
        ax_bar.set_title("Precision / Recall / F1 by class")
        ax_bar.set_xticks(ind)
        ax_bar.set_xticklabels(labels, rotation=20, ha='right')
        ax_bar.set_ylim(0, 1.05)

        ax_bar.legend(loc='upper center', bbox_to_anchor=(0.5, 1.04), ncol=n_metrics, frameon=False)
        fig_bar.tight_layout(rect=[0, 0, 1, 0.93])

        metrics_path = os.path.join(out_dir, "eval_metrics.png")
        try:
            fig_bar.savefig(metrics_path, bbox_inches='tight')
            print(f"[PLOT] Saved metrics chart to: {metrics_path}")
        except Exception as e:
            print(f"[PLOT] Failed to save metrics chart: {e}")
        if not non_interactive:
            try:
                plt.show()
            except Exception:
                pass
        plt.close(fig_bar)
    except Exception as e:
        print(f"[PLOT] Error while creating metrics bar chart: {e}")


def main():
    true_path = r"D:\\edai TY sem 1\\News_dataset\\True.csv"
    fake_path = r"D:\\edai TY sem 1\\News_dataset\\Fake.csv"
    n = 300

    true_df = pd.read_csv(true_path)
    fake_df = pd.read_csv(fake_path)

    true_df = true_df.iloc[:, :2].copy()
    true_df["label"] = 0
    fake_df = fake_df.iloc[:, :2].copy()
    fake_df["label"] = 1

    df = pd.concat([true_df, fake_df], ignore_index=True)

    if n > len(df):
        n = len(df)

    sample_df = df.sample(n=n, random_state=42).reset_index(drop=True)

    titles = sample_df.iloc[:, 0].astype(str).tolist()
    texts = sample_df.iloc[:, 1].astype(str).tolist()
    y_true = sample_df["label"].tolist()

    y_pred = []
    predictions_out = []
    for idx, (title, text) in enumerate(zip(titles, texts)):
        try:
            res = check_and_rewrite_headline(title, text)
        except Exception:
            res = {"is_misleading": False, "similarity": None, "method": None, "suggested_title": None}
        pred = 1 if res.get("is_misleading") else 0
        y_pred.append(pred)
        row_out = {
            "index": idx,
            "title": title,
            "text_snippet": (text[:300] + "...") if len(text) > 300 else text,
            "predicted_label": pred,
            "is_misleading": bool(res.get("is_misleading")),
            "similarity": res.get("similarity"),
            "method": res.get("method"),
            "suggested_title": res.get("suggested_title"),
        }
        predictions_out.append(row_out)

    out_path = os.path.join(os.path.dirname(__file__), "eval_results.csv")
    try:
        pd.DataFrame(predictions_out).to_csv(out_path, index=False)
        print(f"[INFO] Saved evaluation results to: {out_path}")
    except Exception as e:
        print(f"[WARN] Failed to save eval_results.csv: {e}")

    try:
        print(classification_report(y_true, y_pred, target_names=["Not Misleading", "Misleading"]))
    except Exception as e:
        print(f"[WARN] Failed to produce classification report: {e}")
    try:
        print(confusion_matrix(y_true, y_pred))
    except Exception as e:
        print(f"[WARN] Failed to produce confusion matrix printout: {e}")

    try:
        p, r, f, support = precision_recall_fscore_support(y_true, y_pred, labels=[0, 1], zero_division=0)
        summary = pd.DataFrame({
            "class": ["Not Misleading", "Misleading"],
            "precision": p,
            "recall": r,
            "f1": f,
            "support": support
        })
        summary_path = os.path.join(os.path.dirname(__file__), "eval_summary.csv")
        summary.to_csv(summary_path, index=False)
        print(f"[INFO] Saved evaluation summary to: {summary_path}")
    except Exception as e:
        print(f"[WARN] Failed to create/save eval_summary.csv: {e}")
        summary = pd.DataFrame({
            "class": ["Not Misleading", "Misleading"],
            "precision": [0.0, 0.0],
            "recall": [0.0, 0.0],
            "f1": [0.0, 0.0],
            "support": [0, 0]
        })

    out_dir = os.path.dirname(__file__)
    try:
        plot_evaluation(y_true, y_pred, summary, out_dir)
    except Exception as e:
        print(f"[PLOT] Unexpected plotting failure: {e}")


if __name__ == "__main__":
    main()

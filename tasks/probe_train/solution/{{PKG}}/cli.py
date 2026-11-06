"""Command-line entry point: train the {{PROBE_NOUN}} on an activations file and print its metrics."""
from __future__ import annotations

import argparse

from {{PKG}}.data import label_counts, load_activations, make_synthetic, train_test_split
from {{PKG}}.train import train_and_evaluate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", help="activations .npz (keys X, y), or 'synthetic'")
    parser.add_argument("--test-frac", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--lr", type=float, default=0.5)
    parser.add_argument("--epochs", type=int, default=300)
    parser.add_argument("--l2", type=float, default=0.0)
    parser.add_argument("--top-k", type=int, default=0, help="also print the k most important features")
    parser.add_argument("--save", default=None, help="write the trained probe weights to this .npz file")
    args = parser.parse_args(argv)

    if args.path == "synthetic":
        X, y = make_synthetic(seed=args.seed)
    else:
        try:
            X, y = load_activations(args.path)
        except (OSError, ValueError, KeyError) as e:
            parser.error(f"cannot read activations from {args.path}: {e}")
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, args.test_frac, args.seed)
    out = train_and_evaluate(X_tr, y_tr, X_te, y_te, lr=args.lr, epochs=args.epochs, l2=args.l2)
    print(f"{{ITEMS}}: {len(y)}  {label_counts(y)}")
    print(f"train accuracy: {out['train_accuracy']:.3f}")
    print(f"test accuracy:  {out['test_accuracy']:.3f}")
    print(f"test auroc:     {out['test_auroc']:.3f}")
    if args.top_k:
        print("top features:", out["probe"].feature_importance(args.top_k))
    if args.save:
        out["probe"].save(args.save)
        print(f"saved probe to {args.save}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

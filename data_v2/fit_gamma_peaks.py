"""
fit_gamma_peaks.py

Adds Gamma-distribution shape parameters and derived peak positions to the
simulation summary table, using two methods per run:

  1. Method-of-moments (closed form, uses WeightedMeanPosition /
     WeightedStdPosition already in the summary table -- no raw file read
     needed for this part).
  2. Nonlinear least-squares fit of
         y = A * x^(k-1) * exp(-x/theta)
     to the raw per-bin data in data_v2/runs/{RunID}.csv, seeded with the
     moment estimates from (1) for robustness.

New columns added to the summary table:
  GammaK_mom, GammaTheta_mom, GammaPeak_mom        -- method of moments
  GammaA_fit, GammaK_fit, GammaTheta_fit           -- nonlinear fit params
  GammaPeak_fit, GammaPeak_fit_stderr              -- fit peak + uncertainty
  GammaR2_fit                                      -- fit quality
  GammaFitStatus                                   -- "ok" / "failed" / "skipped"

Usage:
    python fit_gamma_peaks.py \
        --summary data_v2/summary_v2.csv \
        --runs-dir data_v2/runs \
        --output data_v2/summary_v2_with_gamma.csv
"""

import argparse
import sys

import numpy as np
import pandas as pd
from scipy.optimize import curve_fit


def gamma_shape(x, A, k, theta):
    """Unnormalized Gamma-shaped curve: A * x^(k-1) * exp(-x/theta)."""
    return A * np.power(x, k - 1) * np.exp(-x / theta)


def r_squared(y, y_fit):
    ss_res = np.sum((y - y_fit) ** 2)
    ss_tot = np.sum((y - np.mean(y)) ** 2)
    if ss_tot == 0:
        return np.nan
    return 1 - ss_res / ss_tot


def moment_estimate(mean, std):
    """
    Method-of-moments estimate for Gamma shape/scale from mean and std.
    Gamma: mean = k*theta, var = k*theta^2
      => k = mean^2 / var
      => theta = var / mean
    Returns (k, theta, peak) or (nan, nan, nan) if inputs are invalid.
    """
    if not np.isfinite(mean) or not np.isfinite(std) or mean <= 0 or std <= 0:
        return np.nan, np.nan, np.nan

    var = std ** 2
    k = (mean ** 2) / var
    theta = var / mean
    peak = (k - 1) * theta if k > 1 else 0.0
    return k, theta, peak


def fit_one_run(run_csv_path, k0, theta0):
    """
    Load one run's raw bin data and fit the Gamma-shaped curve.
    Returns a dict of fit results, or None if the file couldn't be read.
    """
    try:
        df = pd.read_csv(run_csv_path)
    except Exception as exc:
        print(f"  [!] could not read {run_csv_path}: {exc}", file=sys.stderr)
        return None

    x = df["x_bin_position"].to_numpy(dtype=float)
    y = df["x_bin"].to_numpy(dtype=float)

    # Seed amplitude from the data itself: at x = mode, gamma_shape ~ peak y value.
    peak_y_guess = y.max() if y.max() > 0 else 1.0
    mode_guess = max(theta0 * (k0 - 1), 1.0) if np.isfinite(k0) and np.isfinite(theta0) else x[np.argmax(y)]
    # Back out an amplitude guess so the curve's height roughly matches the data's peak.
    with np.errstate(all="ignore"):
        shape_at_mode = (mode_guess ** (k0 - 1)) * np.exp(-mode_guess / theta0) if np.isfinite(k0) else np.nan
    A0 = peak_y_guess / shape_at_mode if np.isfinite(shape_at_mode) and shape_at_mode > 0 else peak_y_guess

    if not (np.isfinite(k0) and np.isfinite(theta0) and k0 > 0 and theta0 > 0):
        # Fall back to a generic guess if moments were unusable for this run.
        k0 = 3.0
        theta0 = max(x[np.argmax(y)] / 2.0, 1.0)
        A0 = peak_y_guess

    try:
        popt, pcov = curve_fit(
            gamma_shape,
            x,
            y,
            p0=[A0, k0, theta0],
            bounds=([0, 1.0001, 1e-6], [np.inf, np.inf, np.inf]),
            maxfev=20000,
        )
    except Exception as exc:
        print(f"  [!] fit failed for {run_csv_path}: {exc}", file=sys.stderr)
        return {"status": "failed"}

    A, k, theta = popt
    y_fit = gamma_shape(x, *popt)
    r2 = r_squared(y, y_fit)

    # Peak position and its uncertainty via the delta method.
    # peak = (k - 1) * theta
    # d(peak)/dk = theta ; d(peak)/dtheta = (k - 1)
    peak = (k - 1) * theta
    try:
        var_k = pcov[1, 1]
        var_theta = pcov[2, 2]
        cov_k_theta = pcov[1, 2]
        peak_var = (theta ** 2) * var_k + ((k - 1) ** 2) * var_theta + 2 * theta * (k - 1) * cov_k_theta
        peak_stderr = np.sqrt(peak_var) if peak_var >= 0 else np.nan
    except Exception:
        peak_stderr = np.nan

    return {
        "status": "ok",
        "GammaA_fit": A,
        "GammaK_fit": k,
        "GammaTheta_fit": theta,
        "GammaPeak_fit": peak,
        "GammaPeak_fit_stderr": peak_stderr,
        "GammaR2_fit": r2,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", required=True, help="Path to summary_v2.csv")
    parser.add_argument("--runs-dir", required=True, help="Path to directory containing run_v2_*.csv files")
    parser.add_argument("--output", required=True, help="Path to write the augmented summary CSV")
    parser.add_argument(
        "--skip-nonlinear-fit",
        action="store_true",
        help="Only compute method-of-moments columns; skip reading raw run files entirely.",
    )
    args = parser.parse_args()

    summary = pd.read_csv(args.summary)

    # --- Method of moments (fast, no raw file reads) ---
    mom_results = summary.apply(
        lambda row: moment_estimate(row["WeightedMeanPosition"], row["WeightedStdPosition"]),
        axis=1,
        result_type="expand",
    )
    mom_results.columns = ["GammaK_mom", "GammaTheta_mom", "GammaPeak_mom"]
    summary = pd.concat([summary, mom_results], axis=1)

    if args.skip_nonlinear_fit:
        summary.to_csv(args.output, index=False)
        print(f"Wrote moment-only columns for {len(summary)} runs to {args.output}")
        return

    # --- Nonlinear fit, seeded by the moment estimates ---
    fit_rows = []
    n = len(summary)
    for i, row in summary.iterrows():
        run_id = row["RunID"]
        run_path = f"{args.runs_dir.rstrip('/')}/{run_id}.csv"

        result = fit_one_run(run_path, row["GammaK_mom"], row["GammaTheta_mom"])

        if result is None:
            fit_rows.append({"GammaFitStatus": "skipped"})
        elif result.get("status") == "failed":
            fit_rows.append({"GammaFitStatus": "failed"})
        else:
            result = dict(result)
            result["GammaFitStatus"] = "ok"
            del result["status"]
            fit_rows.append(result)

        if (i + 1) % 50 == 0 or (i + 1) == n:
            print(f"  fit {i + 1}/{n} runs...")

    fit_df = pd.DataFrame(fit_rows)
    summary = pd.concat([summary, fit_df], axis=1)

    n_ok = (summary["GammaFitStatus"] == "ok").sum()
    n_failed = (summary["GammaFitStatus"] == "failed").sum()
    n_skipped = (summary["GammaFitStatus"] == "skipped").sum()
    low_r2 = (summary.loc[summary["GammaFitStatus"] == "ok", "GammaR2_fit"] < 0.95).sum()

    print(f"\nDone: {n_ok} ok, {n_failed} failed, {n_skipped} skipped (missing files).")
    print(f"Of the {n_ok} successful fits, {low_r2} have R2 < 0.95 (flag these for manual review).")

    summary.to_csv(args.output, index=False)
    print(f"Wrote augmented summary table to {args.output}")


if __name__ == "__main__":
    main()

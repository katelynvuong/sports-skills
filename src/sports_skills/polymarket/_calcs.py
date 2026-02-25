"""Monte Carlo bet analysis — Kelly criterion, drawdown, and risk simulation.

Pure-computation module (no network calls). Uses stdlib only (random, math).
Implements a five-step framework for evaluating prediction market bets:

1. Kelly Criterion — optimal bet sizing
2. Empirical Return Set — build returns from historical bet outcomes
3. Monte Carlo Resampling — simulate N wealth paths
4. Maximum Drawdown — worst peak-to-trough loss per path
5. Uncertainty-Adjusted Kelly — shrink Kelly by edge uncertainty
"""

from __future__ import annotations

import math
import random

# ============================================================
# Response Helpers
# ============================================================


def _success(data, message=""):
    return {"status": True, "data": data, "message": message}


def _error(message, data=None):
    return {"status": False, "data": data, "message": message}


# ============================================================
# 1. Kelly Criterion
# ============================================================


def kelly_criterion(request_data: dict) -> dict:
    """Compute the Kelly fraction for a binary bet.

    f* = (p * b - q) / b
    where q = 1 - p

    Params:
        p (float): Probability of winning (0-1).
        b (float): Net odds received on the bet (e.g. 2.0 means you win $2
                    for every $1 wagered, *not* including the stake back).
    """
    params = request_data.get("params", {})
    try:
        p = float(params.get("p", 0))
        b = float(params.get("b", 0))
    except (TypeError, ValueError) as e:
        return _error(f"Invalid parameters: {e}")

    if not 0 < p < 1:
        return _error("p must be between 0 and 1 (exclusive)")
    if b <= 0:
        return _error("b must be positive (net odds received)")

    q = 1.0 - p
    f_star = (p * b - q) / b
    edge = p * b - q  # expected value per $1

    return _success(
        {
            "kelly_fraction": round(f_star, 6),
            "edge": round(edge, 6),
            "p": p,
            "q": round(q, 6),
            "b": b,
            "recommendation": "bet" if f_star > 0 else "no bet",
        },
        f"Kelly fraction: {f_star:.4f} ({'positive edge' if f_star > 0 else 'negative edge'})",
    )


# ============================================================
# 2 & 3. Monte Carlo Resampling
# ============================================================


def monte_carlo_sim(request_data: dict) -> dict:
    """Run Monte Carlo resampling on an empirical return set.

    Takes a set of historical returns and simulates N wealth paths by
    randomly resampling (with replacement) from those returns.

    Params:
        returns (str): Comma-separated returns as decimals (e.g. "0.08,-0.04,0.06,-0.03,0.07").
        n_simulations (int): Number of simulated paths (default: 10000).
        n_periods (int): Number of periods per path (default: length of returns).
        initial_bankroll (float): Starting bankroll (default: 1000).
        seed (int): Random seed for reproducibility (optional).
    """
    params = request_data.get("params", {})

    # Parse returns
    raw = params.get("returns", "")
    if not raw:
        return _error("returns is required (comma-separated decimals, e.g. '0.08,-0.04,0.06')")
    try:
        if isinstance(raw, str):
            returns = [float(r.strip()) for r in raw.split(",")]
        elif isinstance(raw, list):
            returns = [float(r) for r in raw]
        else:
            return _error("returns must be a comma-separated string or list of numbers")
    except (TypeError, ValueError) as e:
        return _error(f"Invalid returns format: {e}")

    if len(returns) < 2:
        return _error("Need at least 2 return values")

    n_sims = int(params.get("n_simulations", 10000))
    n_periods_raw = params.get("n_periods")
    n_periods = int(n_periods_raw) if n_periods_raw is not None else len(returns)
    bankroll = float(params.get("initial_bankroll", 1000.0))
    seed = params.get("seed")

    if n_sims < 1 or n_sims > 100000:
        return _error("n_simulations must be between 1 and 100,000")
    if n_periods < 1:
        return _error("n_periods must be >= 1")

    rng = random.Random(int(seed)) if seed is not None else random.Random()

    # Run simulations
    final_values = []
    max_drawdowns = []
    paths_summary = []  # store subset for visualization

    for j in range(n_sims):
        # Resample returns with replacement
        path_returns = [rng.choice(returns) for _ in range(n_periods)]

        # Build wealth path
        wealth = [bankroll]
        for r in path_returns:
            wealth.append(wealth[-1] * (1.0 + r))

        final_values.append(wealth[-1])

        # Compute max drawdown for this path
        peak = wealth[0]
        mdd = 0.0
        for w in wealth[1:]:
            if w > peak:
                peak = w
            dd = (w - peak) / peak if peak != 0 else 0.0
            if dd < mdd:
                mdd = dd
        max_drawdowns.append(mdd)

        # Store first 20 paths for visualization
        if j < 20:
            paths_summary.append({
                "path_id": j,
                "final_value": round(wealth[-1], 2),
                "max_drawdown": round(mdd, 4),
                "values": [round(w, 2) for w in wealth[:: max(1, len(wealth) // 50)]],
            })

    # Compute statistics
    final_values.sort()
    max_drawdowns.sort()
    n = len(final_values)

    mean_final = sum(final_values) / n
    median_final = final_values[n // 2]
    p5 = final_values[int(n * 0.05)]
    p25 = final_values[int(n * 0.25)]
    p75 = final_values[int(n * 0.75)]
    p95 = final_values[int(n * 0.95)]
    prob_profit = sum(1 for v in final_values if v > bankroll) / n
    prob_ruin = sum(1 for v in final_values if v <= bankroll * 0.1) / n

    mean_mdd = sum(max_drawdowns) / n
    median_mdd = max_drawdowns[n // 2]
    worst_mdd = max_drawdowns[0]  # most negative
    p5_mdd = max_drawdowns[int(n * 0.05)]

    return _success(
        {
            "simulations": n_sims,
            "periods": n_periods,
            "initial_bankroll": bankroll,
            "returns_used": returns,
            "final_value": {
                "mean": round(mean_final, 2),
                "median": round(median_final, 2),
                "p5": round(p5, 2),
                "p25": round(p25, 2),
                "p75": round(p75, 2),
                "p95": round(p95, 2),
                "min": round(final_values[0], 2),
                "max": round(final_values[-1], 2),
            },
            "probability_of_profit": round(prob_profit, 4),
            "probability_of_ruin": round(prob_ruin, 4),
            "max_drawdown": {
                "mean": round(mean_mdd, 4),
                "median": round(median_mdd, 4),
                "worst": round(worst_mdd, 4),
                "p5": round(p5_mdd, 4),
            },
            "sample_paths": paths_summary,
        },
        f"Simulated {n_sims} paths over {n_periods} periods",
    )


# ============================================================
# 4. Maximum Drawdown (standalone)
# ============================================================


def max_drawdown(request_data: dict) -> dict:
    """Compute the maximum drawdown from a wealth/equity series.

    Peak: Pt = max(s<=t) Ws
    Drawdown: DDt = (Wt - Pt) / Pt
    MDD = min(DDt)

    Params:
        values (str): Comma-separated wealth values (e.g. "1000,1080,1040,1100,1050").
    """
    params = request_data.get("params", {})
    raw = params.get("values", "")
    if not raw:
        return _error("values is required (comma-separated wealth series)")
    try:
        if isinstance(raw, str):
            values = [float(v.strip()) for v in raw.split(",")]
        elif isinstance(raw, list):
            values = [float(v) for v in raw]
        else:
            return _error("values must be a comma-separated string or list")
    except (TypeError, ValueError) as e:
        return _error(f"Invalid values format: {e}")

    if len(values) < 2:
        return _error("Need at least 2 values")

    peak = values[0]
    mdd = 0.0
    mdd_peak_idx = 0
    mdd_trough_idx = 0
    current_peak_idx = 0

    drawdown_series = []
    for i, w in enumerate(values):
        if w > peak:
            peak = w
            current_peak_idx = i
        dd = (w - peak) / peak if peak != 0 else 0.0
        drawdown_series.append(round(dd, 6))
        if dd < mdd:
            mdd = dd
            mdd_peak_idx = current_peak_idx
            mdd_trough_idx = i

    return _success(
        {
            "max_drawdown": round(mdd, 6),
            "max_drawdown_pct": f"{mdd * 100:.2f}%",
            "peak_value": round(values[mdd_peak_idx], 2),
            "trough_value": round(values[mdd_trough_idx], 2),
            "peak_index": mdd_peak_idx,
            "trough_index": mdd_trough_idx,
            "drawdown_series": drawdown_series,
        },
        f"Max drawdown: {mdd * 100:.2f}%",
    )


# ============================================================
# 5. Uncertainty-Adjusted Kelly
# ============================================================


def adjusted_kelly(request_data: dict) -> dict:
    """Compute the uncertainty-adjusted Kelly fraction.

    f_empirical = f_kelly * (1 - CV_edge)
    where CV_edge = sigma_edge / mu_edge

    Shrinks the Kelly fraction based on how uncertain the edge estimate is.
    High variance in edge -> more shrinkage -> smaller bet size.

    Params:
        p (float): Probability of winning (0-1).
        b (float): Net odds received on the bet.
        edge_estimates (str): Comma-separated edge estimates from historical data
                              (e.g. "0.05,0.08,0.02,0.06,0.04"). Used to compute
                              the coefficient of variation. If not provided, uses
                              a single-point estimate (no shrinkage).
    """
    params = request_data.get("params", {})
    try:
        p = float(params.get("p", 0))
        b = float(params.get("b", 0))
    except (TypeError, ValueError) as e:
        return _error(f"Invalid parameters: {e}")

    if not 0 < p < 1:
        return _error("p must be between 0 and 1 (exclusive)")
    if b <= 0:
        return _error("b must be positive")

    q = 1.0 - p
    f_kelly = (p * b - q) / b

    # Parse edge estimates
    raw = params.get("edge_estimates", "")
    if raw:
        try:
            if isinstance(raw, str):
                edges = [float(e.strip()) for e in raw.split(",")]
            elif isinstance(raw, list):
                edges = [float(e) for e in raw]
            else:
                edges = []
        except (TypeError, ValueError):
            edges = []
    else:
        edges = []

    if len(edges) >= 2:
        mu_edge = sum(edges) / len(edges)
        variance = sum((e - mu_edge) ** 2 for e in edges) / (len(edges) - 1)
        sigma_edge = math.sqrt(variance)
        cv_edge = sigma_edge / mu_edge if mu_edge != 0 else float("inf")
        shrinkage = max(0.0, 1.0 - cv_edge)
        f_adjusted = f_kelly * shrinkage
    else:
        mu_edge = p * b - q
        sigma_edge = 0.0
        cv_edge = 0.0
        shrinkage = 1.0
        f_adjusted = f_kelly

    return _success(
        {
            "kelly_fraction": round(f_kelly, 6),
            "adjusted_fraction": round(f_adjusted, 6),
            "shrinkage_factor": round(shrinkage, 6),
            "cv_edge": round(cv_edge, 6) if cv_edge != float("inf") else "inf",
            "mu_edge": round(mu_edge, 6),
            "sigma_edge": round(sigma_edge, 6),
            "p": p,
            "b": b,
            "recommendation": "bet" if f_adjusted > 0 else "no bet",
        },
        f"Adjusted Kelly: {f_adjusted:.4f} (shrinkage: {shrinkage:.4f})",
    )


# ============================================================
# All-in-one: Evaluate Bet
# ============================================================


def evaluate_bet(request_data: dict) -> dict:
    """Full bet evaluation: Kelly + Monte Carlo + Drawdown + Adjusted Kelly.

    Combines all five steps into a single analysis. Provide the bet parameters
    and historical returns, get back a complete risk profile.

    Params:
        p (float): Probability of winning (0-1).
        b (float): Net odds received on the bet.
        returns (str): Comma-separated historical returns (e.g. "0.08,-0.04,0.06").
        n_simulations (int): Monte Carlo paths (default: 10000).
        n_periods (int): Periods per path (default: length of returns).
        initial_bankroll (float): Starting bankroll (default: 1000).
        seed (int): Random seed (optional).
    """
    params = request_data.get("params", {})

    # Step 1: Kelly criterion
    kelly_result = kelly_criterion({"params": {"p": params.get("p"), "b": params.get("b")}})
    if not kelly_result["status"]:
        return kelly_result

    # Step 2-3: Monte Carlo (if returns provided)
    mc_result = None
    if params.get("returns"):
        mc_result = monte_carlo_sim({
            "params": {
                "returns": params.get("returns"),
                "n_simulations": params.get("n_simulations", 10000),
                "n_periods": params.get("n_periods"),
                "initial_bankroll": params.get("initial_bankroll", 1000),
                "seed": params.get("seed"),
            }
        })
        if not mc_result["status"]:
            return mc_result

    # Step 5: Adjusted Kelly (use returns as edge estimates if provided)
    adjusted_result = adjusted_kelly({
        "params": {
            "p": params.get("p"),
            "b": params.get("b"),
            "edge_estimates": params.get("returns", ""),
        }
    })

    data = {
        "kelly": kelly_result["data"],
        "adjusted_kelly": adjusted_result["data"],
    }
    if mc_result:
        data["monte_carlo"] = mc_result["data"]

    # Summary
    f_kelly = kelly_result["data"]["kelly_fraction"]
    f_adj = adjusted_result["data"]["adjusted_fraction"]
    edge = kelly_result["data"]["edge"]

    summary_parts = [
        f"Edge: {edge:.4f}",
        f"Kelly: {f_kelly:.4f}",
        f"Adjusted Kelly: {f_adj:.4f}",
    ]
    if mc_result:
        prob_profit = mc_result["data"]["probability_of_profit"]
        mean_mdd = mc_result["data"]["max_drawdown"]["mean"]
        summary_parts.append(f"P(profit): {prob_profit:.1%}")
        summary_parts.append(f"Mean MDD: {mean_mdd:.1%}")

    recommendation = "no bet"
    if f_adj > 0:
        if mc_result and mc_result["data"]["probability_of_profit"] > 0.5:
            recommendation = "bet"
        elif not mc_result:
            recommendation = "bet"

    data["recommendation"] = recommendation
    data["summary"] = " | ".join(summary_parts)

    return _success(data, data["summary"])

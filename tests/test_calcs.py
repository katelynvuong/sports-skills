"""Tests for Monte Carlo bet analysis calculations."""

from sports_skills.polymarket._calcs import (
    adjusted_kelly,
    evaluate_bet,
    kelly_criterion,
    max_drawdown,
    monte_carlo_sim,
)


# ============================================================
# Kelly Criterion
# ============================================================


class TestKellyCriterion:
    def test_positive_edge(self):
        result = kelly_criterion({"params": {"p": 0.6, "b": 2.0}})
        assert result["status"] is True
        assert result["data"]["kelly_fraction"] > 0
        assert result["data"]["recommendation"] == "bet"

    def test_negative_edge(self):
        result = kelly_criterion({"params": {"p": 0.3, "b": 1.0}})
        assert result["status"] is True
        assert result["data"]["kelly_fraction"] < 0
        assert result["data"]["recommendation"] == "no bet"

    def test_even_bet(self):
        # p=0.5, b=1.0 → f* = (0.5*1 - 0.5)/1 = 0
        result = kelly_criterion({"params": {"p": 0.5, "b": 1.0}})
        assert result["status"] is True
        assert result["data"]["kelly_fraction"] == 0.0

    def test_known_values(self):
        # p=0.6, b=1.0 → f* = (0.6*1 - 0.4)/1 = 0.2
        result = kelly_criterion({"params": {"p": 0.6, "b": 1.0}})
        assert result["data"]["kelly_fraction"] == 0.2

    def test_invalid_p_zero(self):
        result = kelly_criterion({"params": {"p": 0, "b": 1.0}})
        assert result["status"] is False

    def test_invalid_p_one(self):
        result = kelly_criterion({"params": {"p": 1.0, "b": 1.0}})
        assert result["status"] is False

    def test_invalid_b_negative(self):
        result = kelly_criterion({"params": {"p": 0.5, "b": -1.0}})
        assert result["status"] is False

    def test_q_complement(self):
        result = kelly_criterion({"params": {"p": 0.7, "b": 2.0}})
        assert result["data"]["q"] == 0.3


# ============================================================
# Monte Carlo Simulation
# ============================================================


class TestMonteCarloSim:
    def test_basic_simulation(self):
        result = monte_carlo_sim({
            "params": {
                "returns": "0.08,-0.04,0.06,-0.03,0.07",
                "n_simulations": 100,
                "seed": 42,
            }
        })
        assert result["status"] is True
        assert result["data"]["simulations"] == 100
        assert "final_value" in result["data"]
        assert "max_drawdown" in result["data"]
        assert "probability_of_profit" in result["data"]

    def test_deterministic_with_seed(self):
        params = {
            "returns": "0.05,-0.02,0.03",
            "n_simulations": 50,
            "seed": 123,
        }
        r1 = monte_carlo_sim({"params": params})
        r2 = monte_carlo_sim({"params": params})
        assert r1["data"]["final_value"]["mean"] == r2["data"]["final_value"]["mean"]

    def test_custom_bankroll(self):
        result = monte_carlo_sim({
            "params": {
                "returns": "0.05,-0.02",
                "n_simulations": 10,
                "initial_bankroll": 5000,
                "seed": 1,
            }
        })
        assert result["data"]["initial_bankroll"] == 5000

    def test_sample_paths_included(self):
        result = monte_carlo_sim({
            "params": {
                "returns": "0.05,-0.02,0.03",
                "n_simulations": 30,
                "seed": 42,
            }
        })
        assert len(result["data"]["sample_paths"]) == 20  # capped at 20

    def test_missing_returns(self):
        result = monte_carlo_sim({"params": {}})
        assert result["status"] is False

    def test_single_return_error(self):
        result = monte_carlo_sim({"params": {"returns": "0.05"}})
        assert result["status"] is False

    def test_list_returns(self):
        result = monte_carlo_sim({
            "params": {
                "returns": [0.05, -0.02, 0.03],
                "n_simulations": 10,
                "seed": 42,
            }
        })
        assert result["status"] is True

    def test_all_positive_returns_high_profit_prob(self):
        result = monte_carlo_sim({
            "params": {
                "returns": "0.05,0.03,0.08,0.02,0.04",
                "n_simulations": 1000,
                "seed": 42,
            }
        })
        assert result["data"]["probability_of_profit"] > 0.9

    def test_excessive_simulations_rejected(self):
        result = monte_carlo_sim({
            "params": {"returns": "0.05,-0.02", "n_simulations": 200000}
        })
        assert result["status"] is False


# ============================================================
# Maximum Drawdown
# ============================================================


class TestMaxDrawdown:
    def test_no_drawdown(self):
        result = max_drawdown({"params": {"values": "100,110,120,130"}})
        assert result["status"] is True
        assert result["data"]["max_drawdown"] == 0.0

    def test_known_drawdown(self):
        # 100 -> 120 -> 90: drawdown = (90-120)/120 = -0.25
        result = max_drawdown({"params": {"values": "100,120,90"}})
        assert result["status"] is True
        assert abs(result["data"]["max_drawdown"] - (-0.25)) < 0.001

    def test_recovery_after_drawdown(self):
        result = max_drawdown({"params": {"values": "100,120,90,150"}})
        assert result["status"] is True
        # Still -0.25 from the 120->90 drop
        assert abs(result["data"]["max_drawdown"] - (-0.25)) < 0.001

    def test_peak_and_trough_indices(self):
        result = max_drawdown({"params": {"values": "100,120,90,150"}})
        assert result["data"]["peak_index"] == 1  # 120
        assert result["data"]["trough_index"] == 2  # 90

    def test_drawdown_series_length(self):
        result = max_drawdown({"params": {"values": "100,110,105,115,108"}})
        assert len(result["data"]["drawdown_series"]) == 5

    def test_missing_values(self):
        result = max_drawdown({"params": {}})
        assert result["status"] is False

    def test_single_value(self):
        result = max_drawdown({"params": {"values": "100"}})
        assert result["status"] is False

    def test_list_input(self):
        result = max_drawdown({"params": {"values": [100, 120, 90]}})
        assert result["status"] is True
        assert abs(result["data"]["max_drawdown"] - (-0.25)) < 0.001


# ============================================================
# Adjusted Kelly
# ============================================================


class TestAdjustedKelly:
    def test_no_edge_estimates_no_shrinkage(self):
        result = adjusted_kelly({"params": {"p": 0.6, "b": 2.0}})
        assert result["status"] is True
        assert result["data"]["shrinkage_factor"] == 1.0
        assert result["data"]["adjusted_fraction"] == result["data"]["kelly_fraction"]

    def test_with_consistent_edges_low_shrinkage(self):
        # Very consistent edges → low CV → minimal shrinkage
        result = adjusted_kelly({
            "params": {"p": 0.6, "b": 2.0, "edge_estimates": "0.10,0.10,0.10,0.10"}
        })
        assert result["status"] is True
        assert result["data"]["shrinkage_factor"] > 0.9

    def test_with_noisy_edges_high_shrinkage(self):
        # Very noisy edges → high CV → more shrinkage
        result = adjusted_kelly({
            "params": {"p": 0.6, "b": 2.0, "edge_estimates": "0.01,0.20,0.02,0.18"}
        })
        assert result["status"] is True
        assert result["data"]["adjusted_fraction"] < result["data"]["kelly_fraction"]

    def test_invalid_p(self):
        result = adjusted_kelly({"params": {"p": 1.5, "b": 2.0}})
        assert result["status"] is False


# ============================================================
# Evaluate Bet (all-in-one)
# ============================================================


class TestEvaluateBet:
    def test_basic_evaluation_no_returns(self):
        result = evaluate_bet({"params": {"p": 0.6, "b": 2.0}})
        assert result["status"] is True
        assert "kelly" in result["data"]
        assert "adjusted_kelly" in result["data"]
        assert result["data"].get("monte_carlo") is None

    def test_full_evaluation_with_returns(self):
        result = evaluate_bet({
            "params": {
                "p": 0.6,
                "b": 2.0,
                "returns": "0.08,-0.04,0.06,-0.03,0.07",
                "n_simulations": 100,
                "seed": 42,
            }
        })
        assert result["status"] is True
        assert "kelly" in result["data"]
        assert "adjusted_kelly" in result["data"]
        assert "monte_carlo" in result["data"]
        assert "recommendation" in result["data"]
        assert "summary" in result["data"]

    def test_negative_edge_no_bet(self):
        result = evaluate_bet({"params": {"p": 0.3, "b": 1.0}})
        assert result["status"] is True
        assert result["data"]["recommendation"] == "no bet"

    def test_invalid_params_propagate(self):
        result = evaluate_bet({"params": {"p": 0, "b": 1.0}})
        assert result["status"] is False

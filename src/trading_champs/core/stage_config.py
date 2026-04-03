"""Stage configuration for per-strategy trading pipelines."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class StageConfig:
    """Quantitative gates and settings for a single stage.

    Each strategy progresses through stages: dry_run -> paper -> live_stage_1 -> live_stage_2.
    A strategy must pass all gates to be promoted to the next stage.
    If drawdown exceeds max_drawdown_pct, the strategy is demoted.
    """

    stage_name: str
    min_trades: int = 20
    min_win_rate: float = 0.55
    max_drawdown_pct: float = 10.0
    min_sharpe_ratio: Optional[float] = None
    days_in_stage_min: int = 7
    capital_fraction: float = 0.0  # 0.0 = dry_run, 0.1 = paper, 0.3 = live stage 1
    demotes_to: str = "dry_run"  # stage to demote to on gate failure

    def gates_met(
        self,
        total_trades: int,
        win_rate: float,
        current_drawdown_pct: float,
        days_in_stage: int,
        sharpe_ratio: Optional[float] = None,
    ) -> bool:
        """Check if all promotion gates are met.

        Args:
            total_trades: Number of completed trades in this stage.
            win_rate: Fraction of winning trades (0.0 to 1.0).
            current_drawdown_pct: Current drawdown as a percentage.
            days_in_stage: Number of days since entering this stage.
            sharpe_ratio: Optional Sharpe ratio for this stage.

        Returns:
            True if all gates are met (strategy is eligible for promotion).
        """
        if total_trades < self.min_trades:
            return False
        if win_rate < self.min_win_rate:
            return False
        if current_drawdown_pct > self.max_drawdown_pct:
            return False
        if days_in_stage < self.days_in_stage_min:
            return False
        if self.min_sharpe_ratio is not None:
            if sharpe_ratio is None or sharpe_ratio < self.min_sharpe_ratio:
                return False
        return True


# Default stage configurations
DRY_RUN = StageConfig(
    stage_name="dry_run",
    min_trades=20,
    min_win_rate=0.55,
    max_drawdown_pct=10.0,
    capital_fraction=0.0,
    demotes_to="dry_run",
)

PAPER = StageConfig(
    stage_name="paper",
    min_trades=20,
    min_win_rate=0.55,
    max_drawdown_pct=8.0,
    capital_fraction=0.1,
    demotes_to="dry_run",
)

LIVE_STAGE_1 = StageConfig(
    stage_name="live_stage_1",
    min_trades=30,
    min_win_rate=0.55,
    max_drawdown_pct=6.0,
    capital_fraction=0.3,
    demotes_to="dry_run",
)

LIVE_STAGE_2 = StageConfig(
    stage_name="live_stage_2",
    min_trades=50,
    min_win_rate=0.60,
    max_drawdown_pct=5.0,
    capital_fraction=0.6,
    demotes_to="live_stage_1",
)

STAGE_CONFIGS: dict[str, StageConfig] = {
    "dry_run": DRY_RUN,
    "paper": PAPER,
    "live_stage_1": LIVE_STAGE_1,
    "live_stage_2": LIVE_STAGE_2,
}


def get_stage_config(stage_name: str) -> StageConfig:
    """Get StageConfig for a stage name."""
    return STAGE_CONFIGS.get(stage_name, DRY_RUN)


def next_stage(current_stage: str) -> Optional[str]:
    """Get the next stage after current_stage, or None if at final stage."""
    progression = ["dry_run", "paper", "live_stage_1", "live_stage_2"]
    try:
        idx = progression.index(current_stage)
        if idx + 1 < len(progression):
            return progression[idx + 1]
        return None
    except ValueError:
        return "paper"

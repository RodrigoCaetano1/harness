"""
Configuration for the harness. All tunable parameters live here.
Model has no default — caller must provide one via --model or HARNESS_MODEL env var.
"""

import os
from dataclasses import dataclass, field


@dataclass
class Config:
    # Model — must be set explicitly; no default to avoid silent misuse
    model: str = field(default_factory=lambda: os.environ.get("HARNESS_MODEL", ""))

    # Context reset between agent calls
    context_reset: bool = True

    # Pause after spec for human approval before initializer runs
    pausa_pos_spec: bool = False

    # Iteration threshold for sprints 1-4 (fixed)
    threshold_fixo_iteracoes: int = 50

    # Meta-harness triggers
    threshold_execucoes_meta: int = 20
    threshold_reviews_meta: int = 5

    # Negotiation / spec revision limits
    max_rodadas_negociacao: int = 3
    max_rodadas_revisao_spec: int = 1

    # Weight for human-intervened sprints in IQR threshold calculation
    peso_human_intervened: float = 0.5

    # Playwright retry settings
    playwright_retries: int = 3
    playwright_backoff_s: int = 2

    # Stack hint surfaced to agents
    stack: str = "React + Vite + FastAPI + SQLite"

    def validate(self) -> None:
        """Raise if required fields are missing or invalid."""
        if not self.model:
            raise ValueError(
                "Config.model must be set. "
                "Pass --model on CLI or set HARNESS_MODEL environment variable."
            )
        if self.threshold_fixo_iteracoes < 1:
            raise ValueError("threshold_fixo_iteracoes must be >= 1")
        if self.max_rodadas_negociacao < 1:
            raise ValueError("max_rodadas_negociacao must be >= 1")
        if not (0.0 <= self.peso_human_intervened <= 1.0):
            raise ValueError("peso_human_intervened must be between 0.0 and 1.0")

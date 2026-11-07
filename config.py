from pathlib import Path
from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AUCTION_", case_sensitive=False)

    host: str = "0.0.0.0"
    port: int = Field(default=8050, ge=1, le=65535)
    database_path: Path = PROJECT_ROOT / "instance" / "auction_house.db"
    marketplace_poll_interval_ms: int = Field(default=7000, ge=1000)
    npc_simulation_enabled: bool = False
    npc_simulation_interval_seconds: int = Field(default=300, ge=1)
    max_npc_listings: int = Field(default=100, ge=0)
    max_npc_transactions_per_cycle: int = Field(default=10, ge=0)
    default_listing_expiration_days: int = Field(default=14, ge=1)
    minimum_price_multiplier: float = Field(default=0.25, gt=0)
    maximum_price_multiplier: float = Field(default=4.0, gt=0)
    max_price_change_percent: float = Field(default=10.0, gt=0, le=100)
    economy_update_interval_minutes: int = Field(default=60, ge=1)
    market_history_interval_minutes: int = Field(default=60, ge=1)
    economy_target_supply_quantity: int = Field(default=10, ge=1)
    economy_target_demand_quantity: int = Field(default=5, ge=1)
    economy_demand_window_hours: int = Field(default=168, ge=1)
    economy_smoothing_factor: Decimal = Field(default=Decimal("0.5"), ge=0, le=1)
    economy_minimum_price_gp: Decimal = Field(default=Decimal("1"), gt=0)
    economy_price_rounding_increment: Decimal = Field(default=Decimal("1"), gt=0)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_path: Path = PROJECT_ROOT / "logs" / "auction_house.log"

    @model_validator(mode="after")
    def validate_price_bounds(self) -> "Settings":
        if self.minimum_price_multiplier > self.maximum_price_multiplier:
            raise ValueError("minimum_price_multiplier cannot exceed maximum_price_multiplier")
        if self.economy_smoothing_factor < 0 or self.economy_smoothing_factor > 1:
            raise ValueError("economy_smoothing_factor must be between 0 and 1")
        return self
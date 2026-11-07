import logging

from apscheduler.schedulers.background import BackgroundScheduler
from dash import Dash, Input, Output, State, ctx, no_update
from pydantic import ValidationError
from sqlalchemy.orm import Session, sessionmaker

from config import Settings
from services.catalog_service import CatalogItem
from services.npc_simulation_service import (
    NpcSimulationSettings,
    default_npc_simulation_settings,
    load_npc_simulation_settings,
    run_npc_simulation_cycle,
    save_npc_simulation_settings,
)


logger = logging.getLogger(__name__)


def _positive_click(value: int | None) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def register_simulation_callbacks(
    app: Dash,
    session_factory: sessionmaker[Session],
    items: list[CatalogItem],
    app_settings: Settings,
    scheduler: BackgroundScheduler,
) -> None:
    @app.callback(
        Output("npc-simulation-feedback", "children"),
        Output("npc-simulation-refresh-token", "data"),
        Input("save-npc-settings", "n_clicks"),
        Input("run-npc-cycle", "n_clicks"),
        State("npc-simulation-enabled", "value"),
        State("npc-simulation-interval", "value"),
        State("npc-activity-intensity", "value"),
        State("npc-max-active-listings", "value"),
        State("npc-max-transactions", "value"),
        State("npc-max-new-listings", "value"),
        State("npc-simulation-refresh-token", "data"),
        prevent_initial_call=True,
    )
    def manage_simulation(
        save_clicks: int,
        run_clicks: int,
        enabled_values: list[str] | None,
        interval_seconds: int | float | None,
        activity_intensity: int | float | None,
        max_active_listings: int | None,
        max_transactions: int | None,
        max_new_listings: int | None,
        refresh_token: int | None,
    ):
        try:
            triggered_id = ctx.triggered_id
            if triggered_id == "save-npc-settings" and _positive_click(save_clicks):
                settings = NpcSimulationSettings(
                    enabled="enabled" in (enabled_values or []),
                    interval_seconds=interval_seconds,
                    activity_intensity=activity_intensity,
                    max_active_listings=max_active_listings,
                    max_transactions_per_cycle=max_transactions,
                    max_new_listings_per_cycle=max_new_listings,
                )
                save_npc_simulation_settings(session_factory, settings)
                if scheduler.running:
                    scheduler.reschedule_job(
                        "npc-simulation-cycle",
                        trigger="interval",
                        seconds=settings.interval_seconds,
                    )
                state = "enabled" if settings.enabled else "paused"
                return f"NPC simulation {state}; settings saved.", (refresh_token or 0) + 1

            if triggered_id == "run-npc-cycle" and _positive_click(run_clicks):
                simulation_settings = load_npc_simulation_settings(
                    session_factory,
                    default_npc_simulation_settings(app_settings),
                )
                result = run_npc_simulation_cycle(
                    session_factory,
                    items,
                    app_settings,
                    simulation_settings,
                    manual=True,
                )
                if result.skipped:
                    return "An NPC simulation cycle is already running.", no_update
                return (
                    f"Cycle complete: {result.listings_created} listings added, "
                    f"{result.transactions_completed} purchases recorded.",
                    (refresh_token or 0) + 1,
                )
        except ValidationError as exc:
            return f"Check simulation settings: {exc.errors()[0]['msg']}.", no_update
        except Exception:
            logger.exception("NPC simulation control failed")
            return "The simulation action failed. Check the application log.", no_update
        return no_update, no_update
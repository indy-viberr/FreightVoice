from __future__ import annotations

from flask import Flask, Response, jsonify, send_from_directory

from freightvoice.adapters.base import FactoringAdapter, TMSAdapter
from freightvoice.adapters.fake import FakeFactoringAdapter, FakeTMSAdapter
from freightvoice.adapters.motive import MotiveAdapter
from freightvoice.adapters.rts import RTSAdapter
from freightvoice.adapters.samsara import SamsaraAdapter
from freightvoice.config import Config
from freightvoice.logging_config import configure_logging
from freightvoice.webhooks import webhooks_bp


def create_app(config_override: dict[str, object] | None = None) -> Flask:
    configure_logging()
    freightvoice_override = {
        key: value for key, value in (config_override or {}).items() if key in Config.model_fields
    }
    config = Config.from_env(freightvoice_override)
    app = Flask(__name__)
    app.config["APP_CONFIG"] = config
    app.config["TESTING"] = bool(config_override.get("TESTING")) if config_override else False
    app.extensions["tms_adapter"] = _build_tms_adapter(config)
    app.extensions["factoring_adapter"] = _build_factoring_adapter(config)
    app.register_blueprint(webhooks_bp)

    @app.get("/dashboard")
    def dashboard() -> Response:
        return send_from_directory(app.static_folder or "static", "dashboard.html")

    @app.get("/state")
    def state() -> tuple[Response, int] | Response:
        adapter = app.extensions["tms_adapter"]
        get_state = getattr(adapter, "get_state", None)
        if get_state is None:
            return jsonify({"error": "state endpoint is only available for FakeTMSAdapter"}), 501
        return jsonify(get_state())

    @app.get("/health")
    def health() -> Response:
        return jsonify({"status": "ok"})

    return app


def _build_tms_adapter(config: Config) -> TMSAdapter:
    if config.FREIGHTVOICE_TMS == "fake":
        return FakeTMSAdapter(config.FAKETMS_URL)
    if config.FREIGHTVOICE_TMS == "samsara":
        return SamsaraAdapter()
    if config.FREIGHTVOICE_TMS == "motive":
        return MotiveAdapter()
    raise ValueError(f"Unsupported TMS adapter {config.FREIGHTVOICE_TMS}")


def _build_factoring_adapter(config: Config) -> FactoringAdapter:
    if config.FREIGHTVOICE_FACTORING == "fake":
        return FakeFactoringAdapter()
    if config.FREIGHTVOICE_FACTORING == "rts":
        return RTSAdapter()
    raise ValueError(f"Unsupported factoring adapter {config.FREIGHTVOICE_FACTORING}")


if __name__ == "__main__":
    app = create_app()
    config: Config = app.config["APP_CONFIG"]
    app.run(host="0.0.0.0", port=config.FREIGHTVOICE_PORT)

# FreightVoice — one-command demo.
.PHONY: demo install test simulate clean

VENV := .venv
PY := ./$(VENV)/bin/python

demo: ## Boot fake TMS + middleware + dashboard (Ctrl-C to stop)
	@bash run.sh

install: ## Create venv and install deps
	@python3 -m venv $(VENV)
	@$(PY) -m pip install -q --upgrade pip
	@$(PY) -m pip install -q -r requirements.txt
	@echo "installed."

test: install ## Run the full pytest suite (localhost only)
	@$(PY) -m pytest -q

simulate: ## Replay the 3 seeded loads through the live webhooks
	@$(PY) demo/simulate_call.py

clean: ## Remove venv, sqlite, caches
	@rm -rf $(VENV) faketms/faketms.sqlite .pytest_cache
	@find . -name __pycache__ -type d -prune -exec rm -rf {} +
	@echo "cleaned."

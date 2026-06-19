PYTHON ?= python3
VENV := .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
FREIGHTVOICE_PORT ?= 5000
FAKETMS_PORT ?= 5001
FAKETMS_URL ?= http://localhost:$(FAKETMS_PORT)

.PHONY: demo test clean

demo:
	@echo "Starting FreightVoice demo..."
	@$(PYTHON) -m venv $(VENV)
	@$(PIP) install -q -r requirements.txt
	FAKETMS_PORT=$(FAKETMS_PORT) FREIGHTVOICE_TMS=fake $(PY) -m faketms.app &
	sleep 1
	FAKETMS_URL=$(FAKETMS_URL) FREIGHTVOICE_PORT=$(FREIGHTVOICE_PORT) FREIGHTVOICE_TMS=fake $(PY) -m freightvoice.app &
	sleep 2
	@echo ""
	@echo "Dashboard:  http://localhost:$(FREIGHTVOICE_PORT)/dashboard"
	@echo "FakeTMS:    $(FAKETMS_URL)/state"
	@echo ""
	@echo "Run the demo: FREIGHTVOICE_URL=http://localhost:$(FREIGHTVOICE_PORT) $(PY) demo/simulate_call.py"

test:
	$(PY) -m pytest tests/ -v --tb=short

clean:
	pkill -f "python -m faketms.app" || true
	pkill -f "python -m freightvoice.app" || true

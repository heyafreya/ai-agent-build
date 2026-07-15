.PHONY: install run clean

install:
	python3 -m venv .venv
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install -r requirements.txt
	@echo ""
	@echo "Setup complete. Run:  source .venv/bin/activate"

run:
	.venv/bin/python -m 01-k8s-health-monitor.src.cli

clean:
	rm -rf .venv

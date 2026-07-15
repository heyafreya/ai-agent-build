.PHONY: install run lint fmt clean

install:
	@command -v uv >/dev/null 2>&1 || { echo "uv not found. First install? Run: curl -LsSf https://astral.sh/uv/install.sh | sh && source ~/.zshrc"; exit 1; }
	uv venv
	uv sync
	uv pip install pre-commit
	uv run pre-commit install
	uv run pre-commit install --hook-type commit-msg
	@echo ""
	@echo "Setup complete. Run:  make run"

run:
	uv run python -m 01-k8s-health-monitor.src.cli

lint:
	uv run ruff check .

fmt:
	uv run ruff format .
	uv run ruff check --fix .

clean:
	rm -rf .venv

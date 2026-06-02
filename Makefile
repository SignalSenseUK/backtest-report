.PHONY: install lint format typecheck test clean

install:
	pip install -e ".[dev,parquet]"

lint:
	ruff check src/ tests/

format:
	ruff format src/ tests/

typecheck:
	mypy src/

test:
	pytest tests/ -v --cov --cov-config=pyproject.toml

clean:
	rm -rf __pycache__
	rm -rf .pytest_cache
	rm -rf dist
	rm -rf *.egg-info
	rm -rf .coverage
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
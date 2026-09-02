.PHONY: install install-prod test lint demo deploy run clean

install:
	pip install -r requirements.txt -r requirements-dev.txt

install-prod:
	pip install -r requirements.txt

test:
	pytest tests/ -v --cov=modules

benchmark:
	python scripts/benchmark.py --offline-mock --n 20

benchmark-live:
	python scripts/benchmark.py --live --n 5

lint:
	flake8 .
	black --check .

demo:
	python pipeline.py --offline-mock

deploy:
	echo "Deployment target not implemented"

run:
	python pipeline.py

clean:
	rm -rf __pycache__ .pytest_cache
	find . -type d -name "__pycache__" -exec rm -r {} +
	find . -type f -name "*.pyc" -delete

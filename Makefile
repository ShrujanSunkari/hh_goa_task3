.PHONY: install test lint demo deploy run clean

install:
	pip install -r requirements.txt

test:
	pytest

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

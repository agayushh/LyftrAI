.PHONY: help install install-dev test format lint clean up down logs build shell

# Default target
help:
	@echo "LyftrAI Webhook Service - Available Commands"
	@echo ""
	@echo "Development:"
	@echo "  make install        Install production dependencies"
	@echo "  make install-dev    Install development dependencies"
	@echo "  make format         Format code with black and isort"
	@echo "  make lint           Run flake8 linter"
	@echo "  make test           Run test suite"
	@echo "  make clean          Remove cache and build files"
	@echo ""
	@echo "Docker:"
	@echo "  make build          Build Docker image"
	@echo "  make up             Build and run with Docker Compose"
	@echo "  make down           Stop and remove containers"
	@echo "  make logs           View container logs"
	@echo "  make shell          Open shell in running container"
	@echo ""

# Development commands
install:
	pip install -r requirements.txt

install-dev:
	pip install -r requirements.txt
	pip install pytest pytest-cov black isort flake8

format:
	black app/ tests/
	isort app/ tests/

lint:
	flake8 app/ tests/

test:
	pytest tests/ -v

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name "*.coverage" -delete
	rm -rf .pytest_cache htmlcov .coverage

# Docker commands
build:
	docker-compose build

up:
	docker-compose up -d --build

down:
	docker-compose down

logs:
	docker-compose logs -f

shell:
	docker-compose exec api /bin/sh

# Lantern shared commands (contract 2.4). Run `make help`.
# No make? Use:  python scripts/tasks.py <target>
SHELL := /bin/bash
PY ?= $(shell [ -x .venv/bin/python ] && echo .venv/bin/python || echo python3)
SCENARIO ?= wildfire_demo_01
SEEDS ?= 20
AWSP = --profile $${AWS_PROFILE:-lantern} --region $${AWS_REGION:-us-east-1}

.PHONY: help setup check lint test local-demo fixture sim features dev-features train eval api fallback dashboard build-src deploy seed destroy

help:
	@grep -E '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | awk -F':.*?## ' '{printf "  %-14s %s\n", $$1, $$2}'

setup: ## create .venv and install everything
	python3 -m venv .venv
	.venv/bin/pip install -U pip
	.venv/bin/pip install -e ".[dev]"
	@[ -f .env ] || (cp .env.example .env && echo "created .env from .env.example - set ACCOUNT_ID")
	@[ -f dashboard/package.json ] && (cd dashboard && npm ci) || echo "dashboard not scaffolded yet (M5)"

check: lint test ## lint + tests (run before every push)
	@[ -f dashboard/package.json ] && (cd dashboard && npm run lint && npm run typecheck) || true

lint: ## ruff
	$(PY) -m ruff check .

test: ## pytest
	$(PY) -m pytest

local-demo: ## naive vs Lantern at hour 9, offline
	LANTERN_MODE=local $(PY) scripts/local_demo.py

fixture: ## rebuild tests/fixtures/wildfire_demo_01 (M2)
	$(PY) -m simulator.demo_fixture

sim: ## generate one scenario into the store, e.g. make sim SCENARIO=train_flood_0003 (M2)
	$(PY) -m simulator.generator $(SCENARIO)

features: ## build clean/training/features.csv from 200 train + 60 test scenarios (M2)
	$(PY) -m simulator.features --train 200 --test 60

dev-features: ## PRACTICE data only (M3), if you just want to try training
	$(PY) -m models.make_dev_features

train: ## train forecaster from clean/training/features.csv (M3)
	$(PY) -m models.train

eval: ## proof chart files; SEEDS=3 for a quick run (M2)
	NOTIFY_ENABLED=false BEDROCK_ENABLED=false $(PY) -m eval.run_eval --seeds $(SEEDS)

api: ## FastAPI on :8000, local mode (M1)
	LANTERN_MODE=local $(PY) -m uvicorn api.app:app --reload --port 8000

fallback: ## build fallback page + plan.json locally and serve on :8080 (M4)
	LANTERN_MODE=local NOTIFY_ENABLED=true $(PY) scripts/local_demo.py >/dev/null
	cp web/fallback/index.html .localstore/s3/fallback/index.html
	@echo "open http://localhost:8080"; $(PY) -m http.server 8080 -d .localstore/s3/fallback

dashboard: ## dashboard dev server on :5173 (M5)
	@[ -f dashboard/package.json ] && (cd dashboard && npm run dev) || echo "not yet - M5 scaffolds dashboard/"

build-src: ## stage Python code + fixture for the zip Lambdas
	rm -rf .build/src && mkdir -p .build/src/tests
	cp -r lantern_core api simulator ingest baselines engine gate explain alerts .build/src/
	cp -r tests/fixtures .build/src/tests/
	cp requirements-lambda.txt .build/src/requirements.txt
	find .build/src -name __pycache__ -prune -exec rm -rf {} +

deploy: build-src ## M1 only: sam build + deploy, upload web files, invalidate CloudFront
	sam build --config-env dev --config-file infra/samconfig.toml
	sam deploy --config-env dev --config-file infra/samconfig.toml
	@WEB=$$(aws cloudformation describe-stacks --stack-name lantern-dev $(AWSP) --query "Stacks[0].Outputs[?OutputKey=='WebBucketName'].OutputValue" --output text); \
	DIST=$$(aws cloudformation describe-stacks --stack-name lantern-dev $(AWSP) --query "Stacks[0].Outputs[?OutputKey=='DistributionId'].OutputValue" --output text); \
	[ -d dashboard/dist ] && aws s3 sync dashboard/dist s3://$$WEB/ --delete --exclude "fallback/*" $(AWSP) || echo "no dashboard/dist yet"; \
	aws s3 cp web/fallback/index.html s3://$$WEB/fallback/index.html $(AWSP); \
	aws cloudfront create-invalidation --distribution-id $$DIST --paths "/*" $(AWSP) >/dev/null; \
	aws cloudformation describe-stacks --stack-name lantern-dev $(AWSP) --query "Stacks[0].Outputs" --output table

seed: ## M1: upload wildfire_demo_01 + sites table to AWS
	LANTERN_MODE=aws $(PY) scripts/seed_demo.py

destroy: ## M1 only, after judging
	sam delete --stack-name lantern-dev $(AWSP)

.PHONY: benchmark develop develop-release lint play release-prepare test test-python test-rust test-semantic-oracle test-semantic-oracle-diagnostic

PYTHON ?= .venv/bin/python
UV_CACHE_DIR ?= .uv-cache
PYTEST_ARGS ?=
STABLE_RETRO_TURBO_REPO ?= $(abspath ../env-StableRetro-turbo)
RETRO_DATA_PATH ?=
ORACLE_CANDIDATE ?= checkout
ORACLE_CANDIDATE_COMMIT ?=
ORACLE_RECEIPT ?=

develop:
	UV_CACHE_DIR=$(UV_CACHE_DIR) $(PYTHON) -m maturin develop

develop-release:
	UV_CACHE_DIR=$(UV_CACHE_DIR) $(PYTHON) -m maturin develop --release --locked

benchmark: develop-release
	$(PYTHON) -m env_breakoutatari2600_turbo_native.benchmark

play: develop-release
	$(PYTHON) -m env_breakoutatari2600_turbo_native.play

lint:
	$(PYTHON) -m ruff check .
	cargo fmt --check
	cargo clippy --locked --all-targets -- -D warnings

release-prepare:
	UV_CACHE_DIR=$(UV_CACHE_DIR) uv sync --locked --extra dev
	scripts/release.py prepare

test-rust:
	cargo test --locked --lib

test-python:
	$(PYTHON) -m pytest $(PYTEST_ARGS)

test-semantic-oracle:
	@test -n "$(RETRO_DATA_PATH)" || \
		(echo "Set RETRO_DATA_PATH to separately obtained lawful Stable Retro data" >&2; exit 2)
	@test -n "$(ORACLE_RECEIPT)" || \
		(echo "Set ORACLE_RECEIPT to an external receipt path" >&2; exit 2)
	@set -eu; \
	temporary=$$(mktemp -d "$${TMPDIR:-/tmp}/breakout-sole-oracle.XXXXXX"); \
	provider_source="$$temporary/provider"; \
	candidate_environment="$$temporary/candidate-environment"; \
	trap 'rm -rf -- "$$temporary"' EXIT; \
	RETRO_DATA_PATH="$(RETRO_DATA_PATH)" \
	$(PYTHON) scripts/compare_stable_retro_turbo.py \
		--provider-repo "$(STABLE_RETRO_TURBO_REPO)" \
		--prepare-provider "$$provider_source"; \
	UV_CACHE_DIR=$(UV_CACHE_DIR) uv venv --python "$(PYTHON)" "$$candidate_environment"; \
	candidate_python="$$candidate_environment/bin/python"; \
	candidate_commit="$(ORACLE_CANDIDATE_COMMIT)"; \
	if [ "$(ORACLE_CANDIDATE)" = checkout ]; then \
		candidate_commit=$$(git rev-parse HEAD); \
		UV_CACHE_DIR=$(UV_CACHE_DIR) $(PYTHON) -m maturin build --release --locked \
			--out "$$temporary/dist"; \
		set -- "$$temporary"/dist/*.whl; \
		test "$$#" -eq 1; \
		UV_CACHE_DIR=$(UV_CACHE_DIR) uv pip install --python "$$candidate_python" "$$1"; \
		candidate_version=$$(tr -d '[:space:]' < VERSION.txt); \
	else \
		test -n "$$candidate_commit" || \
			(echo "Set ORACLE_CANDIDATE_COMMIT for a published candidate" >&2; exit 2); \
		UV_CACHE_DIR=$(UV_CACHE_DIR) uv pip install --python "$$candidate_python" \
			"env-breakoutatari2600-turbo-native==$(ORACLE_CANDIDATE)"; \
		candidate_version="$(ORACLE_CANDIDATE)"; \
	fi; \
	UV_CACHE_DIR=$(UV_CACHE_DIR) uv pip install --python "$$candidate_python" "$$provider_source"; \
	RETRO_DATA_PATH="$(RETRO_DATA_PATH)" \
	"$$candidate_python" scripts/oracle_release_gate.py generate \
		--receipt "$(ORACLE_RECEIPT)" \
		--provider-repo "$$provider_source" \
		--data-root "$(RETRO_DATA_PATH)" \
		--candidate "$(ORACLE_CANDIDATE)" \
		--candidate-commit "$$candidate_commit"; \
	"$$candidate_python" scripts/oracle_release_gate.py verify \
		--receipt "$(ORACLE_RECEIPT)" \
		--candidate-version "$$candidate_version" \
		--candidate-commit "$$candidate_commit"

test-semantic-oracle-diagnostic:
	@echo "NON-CERTIFYING: diagnostic Turbo comparison; this cannot approve a release" >&2
	@test -n "$(RETRO_DATA_PATH)" || \
		(echo "Set RETRO_DATA_PATH to separately obtained lawful Stable Retro data" >&2; exit 2)
	@set -eu; \
	provider_source=$$(mktemp -d "$${TMPDIR:-/tmp}/breakout-stable-retro-turbo.XXXXXX"); \
	trap 'rm -rf -- "$$provider_source"' EXIT; \
	RETRO_DATA_PATH="$(RETRO_DATA_PATH)" \
	$(PYTHON) scripts/compare_stable_retro_turbo.py \
		--provider-repo "$(STABLE_RETRO_TURBO_REPO)" \
		--prepare-provider "$$provider_source"; \
	UV_CACHE_DIR=$(UV_CACHE_DIR) $(PYTHON) -m maturin develop --release --locked; \
	UV_CACHE_DIR=$(UV_CACHE_DIR) uv pip install --python "$(PYTHON)" "$$provider_source"; \
	BREAKOUT_REQUIRE_STABLE_RETRO_TURBO=1 \
	BREAKOUT_STABLE_RETRO_TURBO_REPO="$$provider_source" \
	RETRO_DATA_PATH="$(RETRO_DATA_PATH)" \
	$(PYTHON) -m pytest -m stable_retro tests/test_stable_retro_turbo_oracle.py $(PYTEST_ARGS)

test: test-rust test-python

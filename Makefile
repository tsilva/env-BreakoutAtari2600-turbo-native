.PHONY: benchmark develop develop-release lint play release-prepare test test-python test-rust test-semantic-oracle

PYTHON ?= .venv/bin/python
UV_CACHE_DIR ?= .uv-cache
PYTEST_ARGS ?=
STABLE_RETRO_TURBO_REPO ?= $(abspath ../env-StableRetro-turbo)
RETRO_DATA_PATH ?=

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

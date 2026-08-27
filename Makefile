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

test-semantic-oracle: develop-release
	@test -n "$(RETRO_DATA_PATH)" || \
		(echo "Set RETRO_DATA_PATH to separately obtained lawful Stable Retro data" >&2; exit 2)
	UV_CACHE_DIR=$(UV_CACHE_DIR) uv pip install --python "$(PYTHON)" "$(STABLE_RETRO_TURBO_REPO)"
	BREAKOUT_REQUIRE_STABLE_RETRO_TURBO=1 \
	BREAKOUT_STABLE_RETRO_TURBO_REPO="$(STABLE_RETRO_TURBO_REPO)" \
	RETRO_DATA_PATH="$(RETRO_DATA_PATH)" \
	$(PYTHON) -m pytest -m stable_retro tests/test_stable_retro_turbo_oracle.py $(PYTEST_ARGS)

test: test-rust test-python

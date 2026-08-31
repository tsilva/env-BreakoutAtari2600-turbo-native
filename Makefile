.PHONY: develop develop-release lint parity parity-release play release-prepare test test-python test-rust verify-parity

PYTHON ?= .venv/bin/python
UV_CACHE_DIR ?= .uv-cache
PYTEST_ARGS ?=
TURBOBENCH ?= $(abspath ../turbobench/.venv/bin/turbobench)
PARITY_OUTPUT ?=
PARITY_RECEIPT ?=
PARITY_WHEEL ?=

develop:
	UV_CACHE_DIR=$(UV_CACHE_DIR) $(PYTHON) -m maturin develop

develop-release:
	UV_CACHE_DIR=$(UV_CACHE_DIR) $(PYTHON) -m maturin develop --release --locked

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

parity:
	@output="$(PARITY_OUTPUT)"; \
	if [ -z "$$output" ]; then output="$$(mktemp -d)/breakout-parity"; fi; \
	$(TURBOBENCH) parity breakout/start-v2 \
		--candidate env-breakoutatari2600-turbo-native@checkout:$(CURDIR) \
		--output "$$output" --allow-dirty --quick; \
	echo "Diagnostic parity receipt: $$output"

parity-release:
	@test -f "$(PARITY_WHEEL)" || (echo "Set PARITY_WHEEL to the exact final wheel" >&2; exit 2)
	@test -n "$(PARITY_OUTPUT)" || (echo "Set PARITY_OUTPUT to an external receipt path" >&2; exit 2)
	$(TURBOBENCH) parity breakout/start-v2 \
		--candidate env-breakoutatari2600-turbo-native@artifact:$(abspath $(PARITY_WHEEL)) \
		--output "$(PARITY_OUTPUT)"
	$(TURBOBENCH) verify-parity "$(PARITY_OUTPUT)" --require-canonical \
		--require-provider env-breakoutatari2600-turbo-native

verify-parity:
	@test -n "$(PARITY_RECEIPT)" || \
		(echo "Set PARITY_RECEIPT to an external TurboBench receipt" >&2; exit 2)
	$(TURBOBENCH) verify-parity "$(PARITY_RECEIPT)" --require-canonical \
		--require-provider env-breakoutatari2600-turbo-native

test: test-rust test-python

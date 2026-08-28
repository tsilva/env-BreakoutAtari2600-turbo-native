.PHONY: develop develop-release lint play release-prepare test test-python test-rust test-semantic-oracle test-semantic-oracle-diagnostic

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
	provider_build="$$temporary/provider-build"; \
	provider_dist="$$temporary/provider-dist"; \
	candidate_dist="$$temporary/candidate-dist"; \
	candidate_environment="$$temporary/candidate-environment"; \
	trap 'rm -rf -- "$$temporary"' EXIT; \
	RETRO_DATA_PATH="$(RETRO_DATA_PATH)" \
	$(PYTHON) scripts/compare_stable_retro_turbo.py \
		--provider-repo "$(STABLE_RETRO_TURBO_REPO)" \
		--prepare-provider "$$provider_source"; \
	git clone --quiet --no-checkout --no-local "$$provider_source" "$$provider_build"; \
	git -C "$$provider_build" checkout --quiet --detach \
		$$(git -C "$$provider_source" rev-parse HEAD); \
	if [ "$$(uname -s)" = Darwin ]; then \
		MACOSX_DEPLOYMENT_TARGET=14.0 \
		UV_CACHE_DIR=$(UV_CACHE_DIR) uv build --no-config --wheel --no-build-logs \
			--python "$(PYTHON)" --default-index https://pypi.org/simple \
			--exclude-newer "7 days" --out-dir "$$provider_dist" "$$provider_build"; \
	else \
		env -u MACOSX_DEPLOYMENT_TARGET UV_CACHE_DIR=$(UV_CACHE_DIR) \
			uv build --no-config --wheel --no-build-logs \
			--python "$(PYTHON)" --default-index https://pypi.org/simple \
			--exclude-newer "7 days" --out-dir "$$provider_dist" "$$provider_build"; \
	fi; \
	set -- "$$provider_dist"/*.whl; \
	test "$$#" -eq 1; \
	test -f "$$1"; \
	provider_wheel="$$1"; \
	UV_CACHE_DIR=$(UV_CACHE_DIR) uv venv --no-config --python "$(PYTHON)" "$$candidate_environment"; \
	candidate_python="$$candidate_environment/bin/python"; \
	candidate_commit="$(ORACLE_CANDIDATE_COMMIT)"; \
	if [ "$(ORACLE_CANDIDATE)" = checkout ]; then \
		candidate_commit=$$(git rev-parse HEAD); \
		if [ "$$(uname -s)" = Darwin ]; then \
			MACOSX_DEPLOYMENT_TARGET=11.0 \
			UV_CACHE_DIR=$(UV_CACHE_DIR) $(PYTHON) -m maturin build --release --locked \
				--out "$$candidate_dist"; \
		else \
			env -u MACOSX_DEPLOYMENT_TARGET UV_CACHE_DIR=$(UV_CACHE_DIR) \
				$(PYTHON) -m maturin build --release --locked \
				--out "$$candidate_dist"; \
		fi; \
		candidate_version=$$(tr -d '[:space:]' < VERSION.txt); \
	else \
		test -n "$$candidate_commit" || \
			(echo "Set ORACLE_CANDIDATE_COMMIT for a published candidate" >&2; exit 2); \
		candidate_version="$(ORACLE_CANDIDATE)"; \
		$(PYTHON) scripts/oracle_release_gate.py download-published \
			--version "$$candidate_version" --output-dir "$$candidate_dist"; \
	fi; \
	set -- "$$candidate_dist"/*.whl; \
	test "$$#" -eq 1; \
	test -f "$$1"; \
	candidate_wheel="$$1"; \
	UV_CACHE_DIR=$(UV_CACHE_DIR) uv pip install --no-config \
		--default-index https://pypi.org/simple \
		--python "$$candidate_python" "$$candidate_wheel"; \
	UV_CACHE_DIR=$(UV_CACHE_DIR) uv pip install --no-config \
		--default-index https://pypi.org/simple \
		--python "$$candidate_python" "$$provider_wheel"; \
	RETRO_DATA_PATH="$(RETRO_DATA_PATH)" \
	"$$candidate_python" scripts/oracle_release_gate.py generate \
		--receipt "$(ORACLE_RECEIPT)" \
		--provider-repo "$$provider_source" \
		--data-root "$(RETRO_DATA_PATH)" \
		--candidate "$(ORACLE_CANDIDATE)" \
		--candidate-commit "$$candidate_commit"; \
	"$$candidate_python" scripts/oracle_release_gate.py verify-local \
		--receipt "$(ORACLE_RECEIPT)" \
		--candidate-version "$$candidate_version" \
		--candidate-commit "$$candidate_commit"

test-semantic-oracle-diagnostic:
	@echo "NON-CERTIFYING: diagnostic Turbo comparison; this cannot approve a release" >&2
	@test -n "$(RETRO_DATA_PATH)" || \
		(echo "Set RETRO_DATA_PATH to separately obtained lawful Stable Retro data" >&2; exit 2)
	@set -eu; \
	temporary=$$(mktemp -d "$${TMPDIR:-/tmp}/breakout-stable-retro-turbo.XXXXXX"); \
	provider_source="$$temporary/provider"; \
	provider_build="$$temporary/provider-build"; \
	provider_dist="$$temporary/provider-dist"; \
	trap 'rm -rf -- "$$temporary"' EXIT; \
	RETRO_DATA_PATH="$(RETRO_DATA_PATH)" \
	$(PYTHON) scripts/compare_stable_retro_turbo.py \
		--provider-repo "$(STABLE_RETRO_TURBO_REPO)" \
		--prepare-provider "$$provider_source"; \
	git clone --quiet --no-checkout --no-local "$$provider_source" "$$provider_build"; \
	git -C "$$provider_build" checkout --quiet --detach \
		$$(git -C "$$provider_source" rev-parse HEAD); \
	if [ "$$(uname -s)" = Darwin ]; then \
		MACOSX_DEPLOYMENT_TARGET=14.0 \
		UV_CACHE_DIR=$(UV_CACHE_DIR) uv build --no-config --wheel --no-build-logs \
			--python "$(PYTHON)" --default-index https://pypi.org/simple \
			--exclude-newer "7 days" --out-dir "$$provider_dist" "$$provider_build"; \
	else \
		env -u MACOSX_DEPLOYMENT_TARGET UV_CACHE_DIR=$(UV_CACHE_DIR) \
			uv build --no-config --wheel --no-build-logs \
			--python "$(PYTHON)" --default-index https://pypi.org/simple \
			--exclude-newer "7 days" --out-dir "$$provider_dist" "$$provider_build"; \
	fi; \
	set -- "$$provider_dist"/*.whl; \
	test "$$#" -eq 1; \
	test -f "$$1"; \
	UV_CACHE_DIR=$(UV_CACHE_DIR) $(PYTHON) -m maturin develop --release --locked; \
	UV_CACHE_DIR=$(UV_CACHE_DIR) uv pip install --no-config \
		--default-index https://pypi.org/simple --python "$(PYTHON)" "$$1"; \
	BREAKOUT_REQUIRE_STABLE_RETRO_TURBO=1 \
	BREAKOUT_STABLE_RETRO_TURBO_REPO="$$provider_source" \
	RETRO_DATA_PATH="$(RETRO_DATA_PATH)" \
	$(PYTHON) -m pytest -m stable_retro tests/test_stable_retro_turbo_oracle.py $(PYTEST_ARGS)

test: test-rust test-python

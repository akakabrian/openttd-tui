VENDOR := engine/openttd

.PHONY: all bootstrap venv run test test-only perf clean

all: venv

bootstrap: $(VENDOR)/.git
$(VENDOR)/.git:
	@echo "==> fetching OpenTTD source tree into engine/ (reference only, ~120 MB)"
	@mkdir -p engine
	git clone --depth=1 https://github.com/OpenTTD/OpenTTD.git $(VENDOR)
	@echo "==> bootstrap complete — source is a reference, not linked"

venv: .venv/bin/python
.venv/bin/python:
	python3 -m venv .venv
	.venv/bin/pip install -e .

run: venv
	.venv/bin/python openttd.py

test: venv
	.venv/bin/python -m tests.qa

test-only: venv
	.venv/bin/python -m tests.qa $(PAT)

test-api: venv
	.venv/bin/python -m tests.api_qa

perf: venv
	.venv/bin/python -m tests.perf

clean:
	rm -rf .venv *.egg-info openttd_tui/__pycache__ tests/__pycache__ tests/out

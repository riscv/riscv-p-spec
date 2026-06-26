SCRIPT_DIR := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
REPO_ROOT  := $(abspath $(SCRIPT_DIR)/..)
SPEC       := $(REPO_ROOT)/P-ext-intrinsics.adoc
JSON       := $(SCRIPT_DIR)/intrinsics.json
API_TEST   := $(SCRIPT_DIR)/api-test

MARCH      ?= rv64gcp
MABI       ?= lp64
JOBS       ?= $(shell nproc)

all: json c-api-test

json: $(JSON)

$(JSON): $(SPEC) $(SCRIPT_DIR)/spec2json.py
	python3 $(SCRIPT_DIR)/spec2json.py $(SPEC) $(JSON)

c-api-test: $(JSON) $(SCRIPT_DIR)/gen_api_test.py
	python3 $(SCRIPT_DIR)/gen_api_test.py --json $(JSON) --output $(API_TEST)

run-c-api-test:
ifeq ($(origin CC),default)
	$(error CC is not set. Usage: make run-c-api-test CC=/path/to/compiler)
endif
	python3 $(SCRIPT_DIR)/api_tester.py \
		--cc $(CC) \
		--spec $(SPEC) \
		--march $(MARCH) \
		--mabi $(MABI) \
		-j $(JOBS) \
		-o $(API_TEST) \
		$(EXTRA_OPTS)

clean:
	rm -rf $(JSON) $(API_TEST)

.PHONY: all json c-api-test run-c-api-test clean

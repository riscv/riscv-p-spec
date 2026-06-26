# intrinsic-utils

Tooling for parsing the P extension intrinsics spec and running
compile-only API tests against a RISC-V compiler.

## Quick start

```sh
# Generate intrinsics.json from the spec
$ make json

# Generate .c test files
$ make c-api-test

# Compile all tests (CC is required)
$ make run-c-api-test CC=riscv64-unknown-elf-gcc
$ make run-c-api-test CC=clang MARCH=rv64gcp0p21

# Or run the tester directly with extra options
$ python3 api_tester.py --cc clang --march rv64gcp0p21 --mabi lp64 -j8
```

## Makefile targets

| Target           | Description                                      |
|------------------|--------------------------------------------------|
| `all`            | Generate JSON and test files                     |
| `json`           | Parse spec into `intrinsics.json`                |
| `c-api-test`     | Generate `.c` test files under `api-test/`       |
| `run-c-api-test` | Compile tests (requires `CC=`)                   |
| `clean`          | Remove generated `intrinsics.json` and `api-test/` |

## Variables

| Variable     | Default         | Description                  |
|--------------|-----------------|------------------------------|
| `CC`         | (none)          | Compiler path (required for `run-c-api-test`) |
| `MARCH`      | `rv64gcp`       | Architecture string          |
| `MABI`       | `lp64`          | ABI string                   |
| `JOBS`       | `nproc`         | Parallel compile jobs        |
| `EXTRA_OPTS` | (none)          | Extra flags passed to `api_tester.py` |

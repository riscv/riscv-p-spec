# riscv-p-spec
This repository contains the working draft of RISC-V P Packed SIMD Extension.

The top level file is P-ext-proposal.adoc.

Simply clicking on the file to render a formatted version of the document.

## Building the Document

The document can be built as PDF or HTML using the provided Makefile. The build uses a Docker container by default.

### Prerequisites

- Docker, or locally installed [asciidoctor-pdf](https://docs.asciidoctor.org/pdf-converter/latest/install/)
- Git submodules initialized:
  ```
  git submodule update --init
  ```

### Build

```
make
```

This will generate `build/P-ext-proposal.pdf` and `build/P-ext-proposal.html`.

To build without Docker:

```
make SKIP_DOCKER=true build-docs
```

To clean build artifacts:

```
make clean
```

## Links

Currently draft version please view https://www.jhauser.us/RISCV/ext-P/

A completed version for p v018 and p v0.9.11, the v018 is based on John Hauser's draft specification, and v0.9.11 is based on this github riscv-p-spec repo old-doc:

v0.21 gcc:https://github.com/ruyisdk/riscv-gcc/tree/p-dev

v0.21 binutils: https://github.com/ruyisdk/riscv-binutils/tree/p-rebase

v0.21 qemu: https://github.com/mollybuild/qemu/tree/rvp-upstream-split

v0.9.11 gcc: https://github.com/ruyisdk/riscv-gcc/tree/15.1.0

v0.9.11 binutils:  https://github.com/ruyisdk/riscv-binutils/commit/1bcac7513f9faa4cd969f8dc7cf2491b6c22d7db

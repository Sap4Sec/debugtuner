# debugtuner

This repository contains the source code of DebugTuner, a framework for tuning compilers towards the generation of more debuggable programs with low performance overhead. The methodology behind the framework is described in the paper ``Towards Threading the Needle of Debuggable Optimized Binaries'', to appear in Proceedings of CGO 2026.

We provide the framework source code, made of the entire suite for debug information quality measurements and compiler pipeline tuning, and the scripts and configuration files to run the performance evaluation on SPEC CPU 2017. We also provide a Docker setup to reproduce our evaluation environment (software-wise).

### Dependencies

Here, we provide the set of dependencies, both software and hardware, that are required to successfully use DebugTuner. Note that software requirements are already satisfied if the docker image provided is used.

#### Software

DebugTuner mostly uses python, thus it requires `python3` (minimum tested version being `3.8`). The only external library used is `pyelftools` (minimum tested version `0.32`).

A compiler toolchain is required (both `gcc/gdb` or `clang/lldb` are currently supported). The exact compiler versions used in the evaluation are available in the provided docker image (with the `clang` patch for disabling passes included).

To run performance evaluation, the SPEC CPU 2017 test suite is required. Also, `perf` is required for AutoFDO experiments and `hyperfine` version `0.19` is required for the AutoFDO experiments targeting clang.

All the versions of the programs included in the test suite are fixed via commit id in the [build.sh](src/build-dataset/build.sh) script. 

DebugTuner should work on most linux distributions, but the docker image is set to use `ubuntu20.04`.

#### Hardware

DebugTuner must be executed on a x86_64 platform. The docker image required about `25GB` of storage. To run the full paper evaluation, at least `100GB` of additional free space is required. To run the minimal working example workload the additional space requirements are about `3GB`.

The estimated timings we provide for the example to run are computed using 20 cores, as the build and traces extraction steps are fully parallelized.

DebugTuner has no stict RAM requirements, but to run the AutoFDO large workload experiments at least `32GB` are required as those use a RAM disk of `20GB`.

The amount of cores that the framework pipeline utilizes is mostly customizable, but the SPEC CPU 2017 configuration file is constructed to be working with 20 physical cores, and the AutoFDO large workload is constructed to be working with 10 physical cores.


### Setup

Here, we provide the instruction to setup the environment to use DebugTuner.

#### Setup with Docker

To use DebugTuner with the provided docker image, the following commands are to be executed from the repository root directory:

1. Build docker image (estimated running time: ~3h):
    
    `./build.sh -j <N>` 

2. Create the docker container in detach mode:

    `./run.sh`

    If SPEC CPU 2017 is available, in order to run performance evaluation (including AutoFDO), the `run.sh` script needs to be updated to mount the SPEC directory and the `perf` binary.

    ```
    -v <spec-cpu-path>:/home/user/spec-cpu
    -v $(which perf):/usr/bin/perf
    ```

3. Attach to the container:

    `docker attach debugtuner-cont`
    or
    `docker exec -it debugtuner-cont bash`

By default, `dt-corpus-min` is initialized with the corpus used during evaluation.

#### Setup without Docker

To use DebugTuner without the provided docker image, all the installation commands from the [Dockerfile](Dockerfile) can be installed. Those are tested on `ubuntu20.04` but should be easy to adapt to arch or debian-based distributions.

### Project Description

Here, we provide a detailed description of how this repository is structured and what is included in each directory, matching the methodology description provided in the paper.

- DebugTuner ([src/](src/)):
    - DebugTuner pipeline ([debugtuner.py](src/debugtuner.py)): DebugTuner main script, it is responsible for controlling all the pipeline stages.
    - Configuration file ([config.py](src/config.py)): Configuration file, it has the list of programs supported by the dataset build system and other useful information for DebugTuner.

    - Test suite construction ([src/build-dataset](src/build-dataset)): This directory contains all the scripts used to build the fuzz targets from OSS-Fuzz, download the initial corpus and minimize it.
        - Build fuzz targets ([build.sh](src/build-dataset/build.sh)): Script for building all the 13 programs used in the evaluation of the framework. Each target is built using all compiler configurations obtained from disabling single optimization passes from standard available optimization levels (O1, O2, O3 and Og).
        - Download input corpus ([corpora.py](src/build-dataset/corpora.py)): Script for downloading the corpus for target programs from OSS-Fuzz queues.
        - Minimize corpus ([minimize.py](src/build-dataset/minimize.py)): Script for corpus minimization, selecting the minimum set of inputs that guarantees the maximum coverage.
    - Debug information quality ([src/debug-quality](src/debug-quality)): This directory contains all the scripts used to accurately measure the debug information quality of target programs.
        - LLVM AST parser ([llvm-ast-parser](src/debug-quality/llvm-ast-parser/)): This directory contains the source code of the LLVM AST parser we implemented for filtering out variables that mistakenly appear in stepped lines while not yet defined.
        - Extract traces dynamically ([traces.py](src/debug-quality/traces.py)): Script for dynamically collecting debug traces. It executes the debugger and at each stepped line extracts all the available variables.
        - Polish traces statically ([static.py](src/debug-quality/static.py)): Script for applying the static analysis pass to polish the traces, solving DWARF definition issues in unoptimized binaries (it uses [llvm-ast-parser](src/debug-quality/llvm-ast-parser/)).
        - Compute metrics ([metrics.py](src/debug-quality/metrics.py)): Script for computing debug information metrics (availability of variables and line coverage) from polished debug traces.
    - Compiler tuning ([src/compiler-tuning](src/compiler-tuning)): This directory contains all the scripts and configurations files to construct rankings of optimization passes critical towards debug information and run performance evaluation using SPEC CPU 2017.
        - Passes rankings ([rankings.py](src/compiler-tuning/rankings.py)): Script for collecting the optimization pass ranking from each program and generating the global top-10 rankings, taking passes based on their average position in per-program rankings.
        - Performance scripts builder ([performance.py](src/compiler-tuning/performance.py)): Script for constructing bash files to run SPEC CPU 2017 performance evaluation. When clang is used, it automatically handles AutoFDO experiments too.
        - SPEC CPU 2017 configuration ([debugtuner-spec.cfg](src/compiler-tuning/debugtuner-spec.cfg)): SPEC CPU 2017 configuration file to run the experiments done in the paper. It should be moved into the [spec-cpu/configs]() directory if the benchmarks are available.
        - SPEC CPU 2017 runner template for gcc ([run_spec_template_gcc.sh](src/compiler-tuning/run_spec_template_gcc.sh)): SPEC CPU 2017 bash script template for gcc.
        - SPEC CPU 2017 runner template for clang ([run_spec_template_clang.sh](src/compiler-tuning/run_spec_template_clang.sh)): SPEC CPU 2017 bash script template for clang.
        - AutoFDO large workload ([large-workload](src/compiler-tuning/large-workloads/)): This directory contains all the scripts used to run the AutoFDO experiments using clang itself as target.
    - Common utilities ([src/utils](src/utils)):
        - Logger ([log.py](src/utils/log.py)): A simple logger implementation to facilitate debug outputs.
        - Runner ([run.py](src/utils/run.py)): A simple runner implementation to easily run commands and extract the output.
        - Tracer ([tracer.py](src/utils/tracer.py)): Script with the main logic of the tracer, which currently supports `gdb` and `lldb` for debug traces extraction.
    - Post-processing scripts ([src/post-processing](src/post-processing/)): This directory contains script to prettify the results of a DebugTuner run.
        - Prettify rankings ([prettify_ranks.py](src/post-processing/prettify_ranks.py)): Script to print a table with the rankings obtained.
        - Prettify configurations debug information metrics ([prettify_configs.py](src/post-processing/prettify_configs.py)): Script to pretty print the results obtained from debug information evaluation of custom configurations.
        - Print configurations flag ([get_configs_cmd.py](src/post-processing/get_configs_flag.py)): Script to print the exact command line to test the ranking based configurations on the selected programs.
    - Miscellaneous scripts: ([src/misc](src/misc)):
        - Clang pass names converter ([clang_pass_names.py](src/misc/clang_pass_names.py)): Script to convert pass names used in JSON results to argument names for pass disabling flag.
        - Fuzz targets main ([fuzzer-main.c](src/misc/fuzzer-main.c)): Driver for fuzz targets, it executes all the input from the corpus in a single execution.
        - Disable opts patch ([disable-opts.patch](src/misc/disable-opts.patch)): LLVM patch to add `-opt-disable` flag. This is the version used for paper evaluation, if a more recent clang version is targeted, the flag may be available by default, since it has been merged (commit id: [81eb7de](https://github.com/llvm/llvm-project/commit/81eb7defa23dcf48a8e51391543eb210df232440))
        - LibSSH patch ([libssh.patch](src/misc/libssh.patch)): A small patch for building libssh in our environment.

- Evaluation dataset ([eval-dataset](eval-dataset)): This directory contains the minimized corpus to reproduce the paper results and the scripts to run the SPEC CPU 2017 evaluation.

The framework utilizes several directories to store binaries, corpus, results and logs. Here, we describe the structure of such directories:

- Source code of tested programs ([dt-projects]()): This directory contains the repository of OSS-Fuzz and all the source code of the programs in the test suite.
- Built target binaries and JSON result files ([dt-targets]()): This directory contains all the built binaries (for the selected programs) and contains all the results of the various states in JSON format.
- Minimized corpus (first stage) ([dt-corpus-cmin]()): This directory contains the minimized corpus after the first minimization step (`afl-cmin`).
- Minimized corpus (final) ([dt-corpus-min]()): This directory contains the fully minimized input corpus.
- Execution logs ([dt-log]()): This directory contains the logs for all the scripts executed by DebugTuner during a run.
- Performance scripts and results ([dt-performance]()): This directory contains the scripts generated to run the performance evaluation and will contain the results of these experiments.

All the directories names are customizable with specific flags for [debugtuner](src/debugtuner.py).

### How to Run

Here, we provide instruction to run the framework. In particular, we describe how to run a minimal working example for testing DebugTuner functionalities.

Instead of testing the full set of (13) programs, it only uses a subset made of 2 programs (`wasm3` and `zydis`), selected to reduce the high execution time time of larger programs (days). Running the framework over the full test suite is only a matter of removing a flag (`--minimal`). 

#### DebugTuner Execution

To run the minimal working example, there are two options available, depending on whether the provided dataset is used or a new one is generated.

> The following commands should be executed from the `/home/user/debugtuner` directory, and should be executed twice, once from `gcc` and once for `clang`.

1. If the provided dataset is used, then all the stages related to corpus construction and minimization can be skipped, reducing by a lot the execution time (since the minimization step is the most time consuming). The estimated running time is ~2h on 20 cores (sum of both compilers timings).

    `python3 debugtuner.py --minimal --proc N --stages build traces static metrics rankings performance --compiler <gcc/clang>`

2. If the dataset is to be constructed from currently available OSS-Fuzz input queues, then all the stages can be safely executed. The estimated running time is ~30m.

    `python3 debugtuner.py --minimal --proc N --all-stages --compiler <gcc/clang>`

> *Notes for reviewers*: we suggest to use the provided dataset, since the minimization stage is very time consuming.

#### Performance Evaluation

If the DebugTuner pipeline has run successfully (performance stage included), then in the [dt-performance]() directory there will the the scripts to be run to perform the performance evaluation.

> Note for reviewers: we do not request the evaluation of the performance experiments. But for those who have access to SPEC CPU 2017 and want to try to replicate the results, the config file is set to use 20 physical cores.

The SPEC CPU 2017 needs to be available in order to do so and the [config file](src/compiler-tuning/debugtuner-spec.cfg) needs to be placed in the configs directory. If the requirements are satisfied, the bash script generated will run automatically run the entire set of performance benchmarks as done in the paper evaluation.

The following command can be used to run the experiments.

```
cd dt-performance
./run_spec_{gcc/clang}.sh
```

When using clang as compiler, the AutoFDO results are computed too. In fact, in the SPEC CPU 2017 reports, the `base` configuration will refer to performance results of the configurations used to build directly and the `peak` configuration will refer to performance results obtained using our AutoFDO setup.

#### AutoFDO Large Workload Experiments

If the DebugTuner pipeline has run successfully (performance stage included), then in the [dt-performance/large-workloads]() directory there will the scripts to be run to perform the performance evaluation of AutoFDO using clang itself as target. The setup is the exact same described in the paper.

The following commands can be used to run the experiments:

```
cd dt-performance/large-workloads
./run_clang.sh
```

#### Feedback Loop

In the paper, we describe how the framework (in particular the debug information quality component) is re-used to evaluate the constructed custom configurations. The following command produces the command line to run debugtuner again using the configurations obtained from rankings.

`python3 post-processing/get_configs_cmd.py --targets dt-targets --compiler <gcc/clang> [--minimal]`

Running the output command will run DebugTuner again, obtaining debug information metrics for the custom configurations.

#### Post-processing 

All the results from the execution can be parsed using the scripts provided in [src/post-processing](src/post-processing).

`python3 post-processing/prettify_ranks.py --targets dt-targets --compiler <gcc/clang>`

This script is responsible for printing a table with all the constructed rankings, showing both the disabled pass and the average debug information quality percentage improvement measured. If the full test suite is tested, using the provided evaluation dataset, this script should replicate Table V and VI in the paper.

`python3 post-processing/prettify_configs.py --targets dt-targets --compiler <gcc/clang>`

This script has to be run after the feedback loop is executed, it prints a table with the debug information availability computed on the custom configurations.

### Reusability

Here, we describe what steps should be taken to extend the test suite used in the evaluation of DebugTuner.

#### Update Build Script

The first step is to update the [build.sh](src/build-dataset/build.sh) script, to include a new function that has the build commands for the project to be added.

For example, this is the function for building `wasm3`:

```
function wasm3() {
    BASE=$PROJECTS_DIR/wasm3

    # prerequisites
    sudo apt-get install -y make

    # clone the repo
    cd $PROJECTS_DIR
    rm -rf wasm3
    git clone https://github.com/wasm3/wasm3

    cd $BASE && git checkout 772f8f4648fcba75f77f894a6050db121e7651a2

    for config_name in "${!opt_configs[@]}"; do
        CFLAGS="-g ${opt_configs[$config_name]}"

        mkdir_out "wasm3" $config_name

        rm -rf build
        mkdir build && cd build
        CXX=$CXX CXXFLAGS=$CXXFLAGS CC=$CC CFLAGS=$CFLAGS cmake -DCMAKE_BUILD_TYPE= -DBUILD_WASI=none $BASE
        make -j $NPROC
        $CC $CFLAGS -c $BASE/platforms/app_fuzz/fuzzer.c -o fuzzer.o -I$BASE/source
        $CC $CFLAGS -c $FUZZER_SRC -o $FUZZER_OBJ
        $CXX $CXXFLAGS -o $OUT/fuzzer fuzzer.o $FUZZER_OBJ $BASE/build/source/libm3.a
        
        cd $BASE
    done
}
```

> Note, if OSS-Fuzz targets are to be added, most of the build code can be found in the OSS-Fuzz repository.

#### Update Config File

Then, the [config.py](src/config.py) files need to be updated as well, listing what fuzzing harnesses are to be used and describe, when necessary, additional compile arguments required by the LLVM AST parser.

For example, these are the config entries for `wasm3`:

`_projects["wasm3"] = ["fuzzer"]`

`ast_config["wasm3"] = CompilerConfig([], ["M3_COMPILE_OPCODES"])`

The compilation flags, if not explicited in the build script, should be extracted from the build configurations in the repository of the selected program. At the moment, our parser requires this manual step to work correctly since it compiles the single C file to be analyzed and pre-processing variables provided via command line can change the shape of the parser AST.

### Results Reproduction: Dataset Availability

To reproduce the results obtained in the paper regarding both debug information quality and performance, we provide both the [minimized corpus](eval-dataset/dt-corpus-min.tar.gz) used and the exact [performance testing scripts](eval-dataset/perf-scripts) used for the paper evaluation.

### Troubleshooting

We are aware of an issues sometimes occurring while building the docker image. Due to the large size of the gcc and LLVM repositories, it may hang if connection is unstable. Restarting the build process upon error should solve the issue.
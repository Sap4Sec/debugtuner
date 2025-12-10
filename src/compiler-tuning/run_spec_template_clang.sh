#!/bin/bash

SPEC_DIRECTORY=/home/user/spec-cpu

# NOTE: update this path accordingly
LLVM_SOURCES_BASE=/usr/local
GCC_SOURCES_BASE=/usr/local
AUTOFD_SOURCES_BASE=/usr/bin

BASE=$SPEC_DIRECTORY/experimental-results
RESULTS_BAG=PERFORMANCE_DIR_TEMPLATE/results-gcc

RESULTS_BASE=$BASE/spec-results
LOGS_BASE=$BASE/spec-logs
PROFILES_BASE=$BASE/spec-profiles

while getopts "f" opt; do
    case $opt in
        f)
            RUN_FAKE=1
        ;;
        \?)
            echo "Invalid option: -$OPTARG" >&2
            exit 1
        ;;
    esac
done

declare -A EVAL_CONFIGURATIONS=(
CONFIGURATIONS_TEMPLATE
)

function run() {
    echo "[$(date)] Running SPEC CPU 2017 - $2"

    RESULTS_DIR=$RESULTS_BASE/$2
    LOGS_DIR=$LOGS_BASE/$2
    PROFILES_DIR=$PROFILES_BASE/$2
    rm -rf RESULTS_DIR && mkdir -p $RESULTS_DIR
    rm -rf LOGS_DIR && mkdir -p $LOGS_DIR
    rm -rf PROFILES_DIR && mkdir -p $PROFILES_DIR

    export SPEC_CONFIGURATION="$3"
    export SPEC_PROFILES_DIR=$PROFILES_DIR

    export SPEC_CC_DIRECTORY=$LLVM_SOURCES_BASE
    export SPEC_CC=clang
    export SPEC_CXX=clang++

    if [ -z "$4" ]; then
        export SPEC_TUNE="base,peak"
    else
        export SPEC_TUNE=$4
    fi

    export SPEC_AUTOFDO_VERSION=$AUTOFDO_SOURCES_BASE/autofdo/build
    export SPEC_LABEL="$1"
    export SPEC_RUN_AUTOFDO=1

    # 1. cleanup spec directories
    ./bin/runcpu --action scrub --config=debugtuner-spec > $LOGS_DIR/runcpu-scrub.log
    rm -rf result/*

    # 2. run spec with given configuration
    if [ -z $RUN_FAKE ]; then
        ./bin/runcpu --config=debugtuner-spec > $LOGS_DIR/runcpu-run.log
    else
        ./bin/runcpu --fake --config=debugtuner-spec > $LOGS_DIR/runcpu-run.log
    fi

    # 3. save results
    mv result/* $RESULTS_DIR/.
    rmdir result

    unset SPEC_RUN_AUTOFDO
    unset SPEC_RUN_SOURCE_INST
}

function run_clang() {
    run clang clang-O0-standard "${EVAL_CONFIGURATIONS[O0-std]}"
    run clang clang-O1-standard "${EVAL_CONFIGURATIONS[O1-std]}"
    run clang clang-O2-standard "${EVAL_CONFIGURATIONS[O2-std]}"
    run clang clang-O3-standard "${EVAL_CONFIGURATIONS[O3-std]}"

    mkdir -p $RESULTS_BAG
    mv $BASE $RESULTS_BAG/experimental-results-std
}

function run_clang_Ox_d3() {
    run clang clang-O1-d3 "${EVAL_CONFIGURATIONS[O1-d3]}"
    run clang clang-O2-d3 "${EVAL_CONFIGURATIONS[O2-d3]}"
    run clang clang-O3-d3 "${EVAL_CONFIGURATIONS[O3-d3]}"

    mkdir -p $RESULTS_BAG
    mv $BASE $RESULTS_BAG/experimental-results-d3
}
function run_clang_Ox_d5() {
    run clang clang-O1-d5 "${EVAL_CONFIGURATIONS[O1-d5]}"
    run clang clang-O2-d5 "${EVAL_CONFIGURATIONS[O2-d5]}"
    run clang clang-O3-d5 "${EVAL_CONFIGURATIONS[O3-d5]}"

    mkdir -p $RESULTS_BAG
    mv $BASE $RESULTS_BAG/experimental-results-d5
}
function run_clang_Ox_d7() {
    run clang clang-O1-d7 "${EVAL_CONFIGURATIONS[O1-d7]}"
    run clang clang-O2-d7 "${EVAL_CONFIGURATIONS[O2-d7]}"
    run clang clang-O3-d7 "${EVAL_CONFIGURATIONS[O3-d7]}"

    mkdir -p $RESULTS_BAG
    mv $BASE $RESULTS_BAG/experimental-results-d7
}
function run_clang_Ox_d9() {
    run clang clang-O1-d9 "${EVAL_CONFIGURATIONS[O1-d9]}"
    run clang clang-O2-d9 "${EVAL_CONFIGURATIONS[O2-d9]}"
    run clang clang-O3-d9 "${EVAL_CONFIGURATIONS[O3-d9]}"

    mkdir -p $RESULTS_BAG
    mv $BASE $RESULTS_BAG/experimental-results-d9
}

mkdir -p $RESULTS_BAG
pushd $SPEC_DIRECTORY

run_clang
run_clang_Ox_d3
run_clang_Ox_d5
run_clang_Ox_d7
run_clang_Ox_d9

popd

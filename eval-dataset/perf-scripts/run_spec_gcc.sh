#!/bin/bash

SPEC_DIRECTORY=/home/user/spec-cpu

LLVM_SOURCES_BASE=/usr/local
GCC_SOURCES_BASE=/usr/local
AUTOFD_SOURCES_BASE=/home/user/autofdo

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
["O1-std"]="-O1"
["O1-d3"]="-O1 -fno-toplevel-reorder -fno-thread-jumps -fno-inline-functions-called-once"
["O1-d5"]="-O1 -fno-toplevel-reorder -fno-thread-jumps -fno-inline-functions-called-once -fno-tree-sink -fno-tree-dominator-opts"
["O1-d7"]="-O1 -fno-toplevel-reorder -fno-thread-jumps -fno-inline-functions-called-once -fno-tree-sink -fno-tree-dominator-opts -fno-tree-loop-optimize -fno-tree-ter"
["O1-d9"]="-O1 -fno-toplevel-reorder -fno-thread-jumps -fno-inline-functions-called-once -fno-tree-sink -fno-tree-dominator-opts -fno-tree-loop-optimize -fno-tree-ter -fno-tree-ch -fno-reorder-blocks"
["O2-std"]="-O2"
["O2-d3"]="-O2 -fno-schedule-insns2 -fno-inline-small-functions -fno-toplevel-reorder"
["O2-d5"]="-O2 -fno-schedule-insns2 -fno-inline-small-functions -fno-toplevel-reorder -fno-thread-jumps -fno-crossjumping"
["O2-d7"]="-O2 -fno-schedule-insns2 -fno-inline-small-functions -fno-toplevel-reorder -fno-thread-jumps -fno-crossjumping -fno-inline-functions -fno-tree-loop-optimize"
["O2-d9"]="-O2 -fno-schedule-insns2 -fno-inline-small-functions -fno-toplevel-reorder -fno-thread-jumps -fno-crossjumping -fno-inline-functions -fno-tree-loop-optimize -fno-expensive-optimizations -fno-if-conversion"
["O3-std"]="-O3"
["O3-d3"]="-O3 -fno-schedule-insns2 -fno-inline-small-functions -fno-thread-jumps"
["O3-d5"]="-O3 -fno-schedule-insns2 -fno-inline-small-functions -fno-thread-jumps -fno-tree-loop-optimize -fno-crossjumping"
["O3-d7"]="-O3 -fno-schedule-insns2 -fno-inline-small-functions -fno-thread-jumps -fno-tree-loop-optimize -fno-crossjumping -fno-expensive-optimizations -fno-inline-functions"
["O3-d9"]="-O3 -fno-schedule-insns2 -fno-inline-small-functions -fno-thread-jumps -fno-tree-loop-optimize -fno-crossjumping -fno-expensive-optimizations -fno-inline-functions -fno-tree-slp-vectorize -fno-toplevel-reorder"
["Og-std"]="-Og"
["Og-d3"]="-Og -fno-thread-jumps -fno-reorder-blocks -fno-tree-coalesce-vars"
["Og-d5"]="-Og -fno-thread-jumps -fno-reorder-blocks -fno-tree-coalesce-vars -fno-tree-forwprop -fno-tree-fre"
["Og-d7"]="-Og -fno-thread-jumps -fno-reorder-blocks -fno-tree-coalesce-vars -fno-tree-forwprop -fno-tree-fre -fno-dce -fno-guess-branch-probability"
["Og-d9"]="-Og -fno-thread-jumps -fno-reorder-blocks -fno-tree-coalesce-vars -fno-tree-forwprop -fno-tree-fre -fno-dce -fno-guess-branch-probability -fno-shrink-wrap -fno-ipa-pure-const"
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

    export SPEC_CC_DIRECTORY=$GCC_SOURCES_BASE
    export SPEC_CC=gcc
    export SPEC_CXX=g++
    export SPEC_TUNE="base"
    export SPEC_IS=1

    export SPEC_AUTOFDO_VERSION=$LLVM_SOURCES_BASE/autofdo-$AUTOFDO_VERSION/build
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
    unset SPEC_IS
}

function run_gcc() {
    run gcc gcc-O0-standard "${EVAL_CONFIGURATIONS[O0-std]}"
    run gcc gcc-O1-standard "${EVAL_CONFIGURATIONS[O1-std]}"
    run gcc gcc-O2-standard "${EVAL_CONFIGURATIONS[O2-std]}"
    run gcc gcc-O3-standard "${EVAL_CONFIGURATIONS[O3-std]}"
    run gcc gcc-Og-standard "${EVAL_CONFIGURATIONS[Og-std]}"

    mkdir -p $RESULTS_BAG
    mv $BASE $RESULTS_BAG/experimental-results-std
}

function run_gcc_Ox_d3() {
    run gcc gcc-O1-d3 "${EVAL_CONFIGURATIONS[O1-d3]}"
    run gcc gcc-O2-d3 "${EVAL_CONFIGURATIONS[O2-d3]}"
    run gcc gcc-O3-d3 "${EVAL_CONFIGURATIONS[O3-d3]}"
    run gcc gcc-Og-d3 "${EVAL_CONFIGURATIONS[Og-d3]}"

    mkdir -p $RESULTS_BAG
    mv $BASE $RESULTS_BAG/experimental-results-d3
}
function run_gcc_Ox_d5() {
    run gcc gcc-O1-d5 "${EVAL_CONFIGURATIONS[O1-d5]}"
    run gcc gcc-O2-d5 "${EVAL_CONFIGURATIONS[O2-d5]}"
    run gcc gcc-O3-d5 "${EVAL_CONFIGURATIONS[O3-d5]}"
    run gcc gcc-Og-d5 "${EVAL_CONFIGURATIONS[Og-d5]}"

    mkdir -p $RESULTS_BAG
    mv $BASE $RESULTS_BAG/experimental-results-d5
}
function run_gcc_Ox_d7() {
    run gcc gcc-O1-d7 "${EVAL_CONFIGURATIONS[O1-d7]}"
    run gcc gcc-O2-d7 "${EVAL_CONFIGURATIONS[O2-d7]}"
    run gcc gcc-O3-d7 "${EVAL_CONFIGURATIONS[O3-d7]}"
    run gcc gcc-Og-d7 "${EVAL_CONFIGURATIONS[Og-d7]}"

    mkdir -p $RESULTS_BAG
    mv $BASE $RESULTS_BAG/experimental-results-d7
}
function run_gcc_Ox_d9() {
    run gcc gcc-O1-d3 "${EVAL_CONFIGURATIONS[O1-d9]}"
    run gcc gcc-O2-d3 "${EVAL_CONFIGURATIONS[O2-d9]}"
    run gcc gcc-O3-d3 "${EVAL_CONFIGURATIONS[O3-d9]}"
    run gcc gcc-Og-d3 "${EVAL_CONFIGURATIONS[Og-d9]}"

    mkdir -p $RESULTS_BAG
    mv $BASE $RESULTS_BAG/experimental-results-d9
}

mkdir -p $RESULTS_BAG
pushd $SPEC_DIRECTORY

run_gcc
run_gcc_Ox_d3
run_gcc_Ox_d5
run_gcc_Ox_d7
run_gcc_Ox_d9

popd
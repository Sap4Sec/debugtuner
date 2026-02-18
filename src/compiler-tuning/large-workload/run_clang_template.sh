#!/bin/bash

source ./vars.sh

RUNS=1
EXISTING=""
STANDARD=false

declare -A EVAL_CONFIGURATIONS=(
CONFIGURATIONS_TEMPLATE
)

# Parse command line arguments
while getopts "r:eo" opt; do
    case $opt in
        r)
            RUNS=$OPTARG
        ;;
        o)
            STANDARD=true
        ;;
        e)
            EXISTING="-e"
        ;;
        \?)
            echo "Invalid option: -$OPTARG" >&2
            exit 1
        ;;
    esac
done

for name in "${!EVAL_CONFIGURATIONS[@]}"; do
        config="${EVAL_CONFIGURATIONS[$name]}"

        for ((run=1; run<=$RUNS; run++)); do
                if [ $run = 1 ]; then
                        FLAG="-p"
                else
                        FLAG=""
                fi

                if [ $STANDARD = false ]; then
                        echo "***** [$run] ***** $name ***** Experiment with Baseline compiling clang with AutoFDO ($EXISTING) ***** $(date) *****"
                        bash -e $BASE/autofdo_run.sh -c "$config" -n $name $FLAG $EXISTING # &> /dev/null
                else
                        echo "***** [$run] ***** $name ***** Experiment with Baseline compiling clang ($EXISTING) ***** $(date) *****"
                        bash -e $BASE/standard_run.sh -c "$config" -n $name $FLAG $EXISTING # &> /dev/null
                fi

                RUNDIR=$BASE/run-$run
                rm -rf $RUNDIR && mkdir -p $RUNDIR
                mv $BASE/results $RUNDIR
        done

        EXPDIR=$BASE/experiments-$name
        rm -rf $EXPDIR && mkdir -p $EXPDIR
        mv -f $BASE/run-* $EXPDIR || true
        mv -f $BASE/profiles $EXPDIR || true
        mv -f $BASE/binaries $EXPDIR || true
        mv -f $BASE/logs $EXPDIR || true
done

mkdir -p $PATH_TO_BAG/clang
mv $BASE/experiments-* $PATH_TO_BAG/clang/.

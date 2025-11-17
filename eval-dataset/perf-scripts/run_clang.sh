#!/bin/bash

source ./vars.sh

RUNS=1
EXISTING=""
STANDARD=false

EVAL_CONFIGURATIONS=(
"O3-std:-O3"
"O3-d3:-O3 -mllvm -opt-disable=Machine_code_sinking,JumpThreadingPass,Loop_Strength_Reduction"
"O3-d5:-O3 -mllvm -opt-disable=Machine_code_sinking,JumpThreadingPass,Loop_Strength_Reduction,SimplifyCFGPass,Branch_Probability_Basic_Block_Placement"
"O3-d7:-O3 -mllvm -opt-disable=Machine_code_sinking,JumpThreadingPass,Loop_Strength_Reduction,SimplifyCFGPass,Branch_Probability_Basic_Block_Placement,DSEPass,LoopUnrollPass"
"O3-d9:-O3 -mllvm -opt-disable=Machine_code_sinking,JumpThreadingPass,Loop_Strength_Reduction,SimplifyCFGPass,Branch_Probability_Basic_Block_Placement,DSEPass,LoopUnrollPass,Control_Flow_Optimizer,SROAPass"
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

for entry in "${EVAL_CONFIGURATIONS[@]}" ; do
        name="${entry%%:*}"
        config="${entry##*:}"

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

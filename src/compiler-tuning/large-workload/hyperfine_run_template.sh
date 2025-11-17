#!/bin/bash

NUM_CORES=10
CORE_SET="0-9"

taskset -c $CORE_SET parallel -j $NUM_CORES < commands_raw.txt

#!/bin/bash

# create debugtuner directories
mkdir -p dt-targets dt-log dt-performance dt-corpus-cmin

# extract evaluation dataset
tar -xzf eval-dataset/dt-corpus-min.tar.gz

# run container mounting directories
docker run --name debugtuner-cont \
    -w /home/user/debugtuner \
    -v ${PWD}/dt-targets:/home/user/debugtuner/dt-targets \
    -v ${PWD}/dt-log:/home/user/debugtuner/dt-log \
    -v ${PWD}/dt-performance:/home/user/debugtuner/dt-performance \
    -v ${PWD}/dt-corpus-min:/home/user/debugtuner/dt-corpus-min \
    -v ${PWD}/dt-corpus-cmin:/home/user/debugtuner/dt-corpus-cmin \
    -it -d debugtuner-image

# NOTE: to also run performance evaluation (including AutoFDO)
# the spec-cpu directory and the perf binary needs to be mounted as well

# -v <spec-cpu-path>:/home/user/spec-cpu
# -v $(which perf):/usr/bin/perf

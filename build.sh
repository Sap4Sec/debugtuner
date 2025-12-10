#!/bin/bash

NCORES=1

while getopts ":j:" opt; do
    case $opt in
        j)
            NCORES=$OPTARG
        ;;
        \?)
            echo "Invalid option: -$OPTARG" >&2
            exit 1
        ;;
    esac
done

# build the docker image
docker build --build-arg cpu_cores=$NCORES -t cristianassaiante/debugtuner:cgo26-ae .

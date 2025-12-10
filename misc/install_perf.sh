#!/bin/bash

LINUX_VERSION=6.8

while getopts ":v:" opt; do
    case $opt in
        v)
            LINUX_VERSION=$OPTARG
        ;;
        \?)
            echo "Invalid option: -$OPTARG" >&2
            exit 1
        ;;
    esac
done

apt-get update
apt-get install -y --no-install-recommends \
    libelf-dev libdw-dev libaudit-dev libbabeltrace-dev \
    libunwind-dev libslang2-dev libnuma-dev libcap-dev \
    zlib1g-dev libzstd-dev libpfm4-dev perl \
    libperl-dev systemtap-sdt-dev bison flex

wget https://mirrors.edge.kernel.org/pub/linux/kernel/v6.x/linux-$LINUX_VERSION.tar.gz
tar -xzf linux-$LINUX_VERSION.tar.gz && rm linux-$LINUX_VERSION.tar.gz

export NO_LIBTRACEEVENT=1

make -C linux-$LINUX_VERSION/tools/perf
cp linux-$LINUX_VERSION/tools/perf/perf /usr/local/bin/perf

rm -r linux-$LINUX_VERSION

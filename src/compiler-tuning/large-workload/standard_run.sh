#!/bin/bash

source ./vars.sh

PROFILES=false
HYPERFINE=false
EXISTING=false
VERSION=trunk
TARGET=20
CONFIGURATION_NAME=fake

# Parse command line arguments
while getopts "c:n:pe" opt; do
    case $opt in
        c)
            CONFIGURATION=$OPTARG
        ;;
        n)
            CONFIGURATION_NAME=$OPTARG
        ;;
        p)
            PROFILES=true
        ;;
        e)
            EXISTING=true
        ;;
        \?)
            echo "Invalid option: -$OPTARG" >&2
            exit 1
        ;;
    esac
done

NAME=llvm-$CONFIGURATION_NAME

if [ $PROFILES = true ] && [ $EXISTING = false ]; then
        LLVM_PATH=$PATH_TO_SOURCES/llvm-project/build
        mkdir -p $PATH_TO_LLVM_BUILDS && cd $PATH_TO_LLVM_BUILDS
        mkdir -p symlinks && cd symlinks
        ln -sf $LLVM_PATH/bin/clang clang
        ln -sf $LLVM_PATH/bin/clang clang++

        # Build llvm with baseline LLVM

        rm -rf $PATH_TO_LLVM_BUILDS/$NAME
        mkdir -p $PATH_TO_LLVM_BUILDS/$NAME && cd $PATH_TO_LLVM_BUILDS/$NAME
        cmake -G Ninja "${COMMON_CMAKE_FLAGS[@]}" \
            "${CMAKE_COMPILER[@]}" \
            "${COMMON_LD_FLAGS[@]}" \
            -DCMAKE_C_FLAGS="$CONFIGURATION -fdebug-info-for-profiling -funique-internal-linkage-names" \
            -DCMAKE_CXX_FLAGS="$CONFIGURATION -fdebug-info-for-profiling -funique-internal-linkage-names" \
            ${PATH_TO_SOURCES}/llvm-project/llvm
        ninja -j 20 clang

        mkdir -p $PATH_TO_BINARIES/$NAME
        cp bin/clang ${PATH_TO_BINARIES}/$NAME/.
fi

mkdir -p $PATH_TO_RESULTS

# --- Mount RAM filesystem ---
RAMFS_PATH=/dev/shm/llvm-bench
mkdir -p $RAMFS_PATH
mount -t tmpfs -o size=20G tmpfs $RAMFS_PATH

# Copy LLVM source tree into RAM
cp -r $PATH_TO_SOURCES/llvm-project $RAMFS_PATH/llvm-project
RAM_SRC=$RAMFS_PATH/llvm-project

# --- Build benchmark LLVM in RAM ---
rm -rf $RAMFS_PATH/build
mkdir -p $RAMFS_PATH/build && cd $RAMFS_PATH/build
mkdir -p symlinks && cd symlinks

ln -sf $PATH_TO_LLVM_BUILDS/$NAME/bin/clang clang
ln -sf $PATH_TO_LLVM_BUILDS/$NAME/bin/clang clang++

cd $RAMFS_PATH/build
cmake -G Ninja "${COMMON_BENCH_CMAKE_FLAGS[@]}" \
    -DCMAKE_C_COMPILER=$RAMFS_PATH/build/symlinks/clang \
    -DCMAKE_CXX_COMPILER=$RAMFS_PATH/build/symlinks/clang++ \
    ${RAM_SRC}/llvm

ninja -j 20 clang

# --- Generate raw commands ---
ninja -C $RAMFS_PATH/build -t commands clang \
    | grep "$RAMFS_PATH/build/symlinks/clang" \
    | grep -E '\.(c|cpp)( |$)' \
    | sed -E "s@-o [^ ]+@-o /dev/null@" \
    > commands_raw.txt

# --- Generate 20 hyperfine scripts ---
sed "s@^@    taskset -c 0 @" commands_raw.txt \
    | sed '/PLACEHOLDER/ {
        r /dev/stdin
        d
    }' "$BASE/hyperfine_run_template.sh" > "hyperfine_run_core_0.sh"
chmod +x "hyperfine_run_core_0.sh"

# --- Run hyperfine scripts in parallel ---
mkdir -p $PATH_TO_RESULTS
hyperfine --runs 5 "./hyperfine_run_core_0.sh" \
    --show-output \
    --export-json "$PATH_TO_RESULTS/hyperfine_${NAME}_core_0.json"

wait

# avoid resource busy when umount
cd $BASE

# --- Clean up RAM filesystem ---
umount -l $RAMFS_PATH
rm -rf $RAMFS_PATH

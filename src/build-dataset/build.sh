#!/bin/bash
REPO=$(dirname $(realpath $0))/..
PROJECTS_DIR="$REPO/dt-projects"
mkdir -p $PROJECTS_DIR
TARGETS="$REPO/dt-targets"
FUZZER_SRC="$REPO/misc/fuzzer-main.c"
FUZZER_OBJ="fuzzer-main.o"
NPROC=1
CXXFLAGS=
PROJECT=
CUSTOM_OPT_CONFIG=

OPT_LIST=(0 1 2 3 g) # default config which is overwritten by -o cli param

set -ux

function build_configs() {
    # opt_configs is an associative array (dict in bash) that will contain all the configurations in the form {"name": "-Ox -f... -fno..."}
    local -a opt_list

    COMPILER_NAME=$(basename $CC | awk -F"-" '{print $1}')

    for i in "${OPT_LIST[@]}"; do

        # this is used to build -all for O0 and disabling opts
        if [ $COMPILER_NAME == "gcc" ]; then
            # manage particular cases where some opt cannot be disabled
            aux=$($CC -Q -O$i --help=optimizers | grep '\[enabled\]' | cut -d ' ' -f3 | sed 's/^-f/-fno-/g; s/stack-protector-strong/stack-protector/g; s/-fno-unroll-completely-grow-size//g;')
            opt_list=($(echo $aux | tr -s '\n' ' '))
        fi

        if [ $COMPILER_NAME == "clang" ]; then
            aux=$(clang -O$i -mllvm -opt-bisect-limit=-1 $FUZZER_SRC -o /dev/null |& grep -v "LCSSAPass" | grep -v "LoopSimplifyPass" | grep -v "Instruction Selection" | awk -F') ' '{print $2}' | awk -F' on ' '{print $1}' | tr -s '\n' ':' | sed s/\ /_/g | sed s/\</_/g | sed s/\>/_/g | sed 's/\//_/g' | sed s/\(/_/g | sed s/\)/_/g | sed s/-/_/g )
            IFS=: opt_list=($aux)
            IFS=' '
        fi

        if [ $COMPILER_NAME != "afl-clang-fast" ] && [ "$i" == 0 ]; then
            opt_configs[$i-standard]="-O$i" # -O0-standard
        elif [ -z "$CUSTOM_OPT_CONFIG" ]; then
            # If one or more custom config are not specified, at other levels build -standard and also disabling one opt per time, otherwise build only with custom opts
            opt_configs[$i-standard]="-O$i" # -Ox-standard
            for disabled_opt in "${opt_list[@]}"; do
                if [ $COMPILER_NAME == "clang" ]; then
                    disabled_opt="-mllvm -opt-disable=$disabled_opt"
                fi
                key="$i$(echo $disabled_opt | sed 's/ //g')"; opt_configs[$key]="-O$i $disabled_opt" # single opt disabled
            done
        else
            case $i in
                0|1|2|3|g|s|z)
                    key="$i-standard" # append -standard to directory name if needed
                ;;
                *)
                    key="$(echo $i | sed 's/ //g')"
                ;;
            esac
            opt_configs[$key]="-O$i" # custom config
        fi
    done
}

function mkdir_out() {
    local project_name="$1"
    local config_name="$2"
    MATCHED=false

    COMPILER_NAME=$(basename $CC | awk -F"-" '{print $1}')
    if [ $COMPILER_NAME == "afl-clang-fast" ] && [ $COMPILER_NAME == "afl-clang-fast++" ]; then
        OUT=$TARGETS/$project_name/$(basename $CC) # for minimization
    else
        # pass name are in camel case and extra flags are not important in dir name
        # remove extra flags and lower everything
        if [[ $config_name == *"-mllvm"* ]]; then
            config_name=$(echo $config_name | sed s/"-mllvm"//g | sed s/"-opt-disable="/-no-/g | sed s/,/-/g | awk '{print tolower($0)}')
        fi

        directory_name="$project_name-O$config_name"
        if [ "${#directory_name}" -gt 255 ]; then
            id=$RANDOM
            directory_name="$project_name-O${config_name:0:1}-custom-$id"
            echo "[CONFIGURATION ID] $project_name-O$config_name MATCHED WITH $directory_name"
            MATCHED=true
        fi
        OUT=$TARGETS/$project_name/$(basename $CC)/$directory_name # for traces
    fi
    mkdir -p $OUT
    if [ $MATCHED = true ]; then
        echo "-o$config_name" > $OUT/config
    fi
}

function bzip2() {
    BASE="$PROJECTS_DIR/bzip2"
    BZIP2_OSS_FUZZ=$PROJECTS_DIR/oss-fuzz/projects/bzip2

    # clone the repo
    cd $PROJECTS_DIR
    rm -rf bzip2
    git clone git://sourceware.org/git/bzip2.git
    cd $BASE && git checkout fbc4b11da543753b3b803e5546f56e26ec90c2a7

    # copy fuzz targets
    mkdir fuzz
    cp $BZIP2_OSS_FUZZ/*.c fuzz/.

    for config_name in "${!opt_configs[@]}"; do
        CFLAGS="-g ${opt_configs[$config_name]}"

        SRCL=(blocksort.o huffman.o crctable.o randtable.o compress.o decompress.o bzlib.o)

        for source in ${SRCL[@]}; do
            name=$(basename $source .o)
            $CC $CFLAGS -c ${name}.c
        done
        rm -f libbz2.a
        ar cq libbz2.a ${SRCL[@]} && ranlib libbz2.a

        # compile fuzz targets
        $CC $CFLAGS -c $FUZZER_SRC -o $FUZZER_OBJ
        export LIB_FUZZING_ENGINE=$FUZZER_OBJ
        mkdir_out "bzip2" $config_name

        shopt -s globstar
        for file in fuzz/*.c;
        do
            name=$(basename $file .c)
            $CC $CFLAGS -c -I . fuzz/${name}.c -o $OUT/${name}.o
            $CXX $CXXFLAGS -o $OUT/${name} $OUT/${name}.o $LIB_FUZZING_ENGINE \
            libbz2.a
            rm -f $OUT/${name}.o
        done
        
        cd $BASE
    done
}

function libdwarf() {
    BASE=$PROJECTS_DIR/libdwarf

    # prerequisites
    sudo apt-get install -qq -y cmake make zlib1g-dev

    cd $PROJECTS_DIR
    rm -rf libdwarf
    git clone https://github.com/davea42/libdwarf-code libdwarf
    cd $BASE && git checkout f717ac1 # v0.8.0 from github

    for config_name in "${!opt_configs[@]}"; do
        CFLAGS="-g ${opt_configs[$config_name]}"
        mkdir_out "libdwarf" $config_name

        rm -rf build && mkdir build && cd build

        CXX=$CXX CXXFLAGS=$CXXFLAGS CC=$CC CFLAGS=$CFLAGS cmake ..
        make -j $NPROC

        # build fuzz targets
        $CC $CFLAGS -c $FUZZER_SRC -o $FUZZER_OBJ
        for fuzzFile in $BASE/fuzz/fuzz*.c; do
            fuzzName=$(basename "$fuzzFile" '.c')
            $CC $CFLAGS $FUZZER_OBJ -I../src/lib/libdwarf/ \
            "$BASE/fuzz/${fuzzName}.c" -o "$OUT/${fuzzName}" ./src/lib/libdwarf/libdwarf.a -lz
        done
        
        cd $BASE
    done
}

function libexif() {
    BASE="$PROJECTS_DIR/libexif"
    LIBEXIF_OSS_FUZZ=$PROJECTS_DIR/oss-fuzz/projects/libexif

    # clone the repo
    cd $PROJECTS_DIR
    rm -rf libexif
    git clone https://github.com/libexif/libexif
    cd $BASE && git checkout 2f69eacf194dbf3efc805de4ace31df2b76245a2

    # copy fuzz targets
    mkdir fuzz
    cp $LIBEXIF_OSS_FUZZ/*.cc fuzz/.

    for config_name in "${!opt_configs[@]}"; do
        CFLAGS="-g ${opt_configs[$config_name]}"

        make clean || true
        autoreconf -fiv
        CXX=$CXX CXXFLAGS=$CXXFLAGS CC=$CC CFLAGS=$CFLAGS ./configure --disable-docs --enable-shared=no --prefix=$BASE
        CXX=$CXX CXXFLAGS=$CXXFLAGS CC=$CC CFLAGS=$CFLAGS make -j $NPROC
        make install

        # compile fuzz targets
        $CC $CFLAGS -c $FUZZER_SRC -o $FUZZER_OBJ
        export LIB_FUZZING_ENGINE=$FUZZER_OBJ
        mkdir_out "libexif" $config_name

        shopt -s globstar
        for file in fuzz/*.cc;
        do
            fuzzer_basename=$(basename -s .cc $file)
            $CXX $CXXFLAGS \
                -std=c++11 \
                -I"$BASE/include" \
                $file \
                -o $OUT/$fuzzer_basename \
                $LIB_FUZZING_ENGINE \
                "$BASE/lib/libexif.a"
        done

        cd $BASE
    done
}

function liblouis() {
    BASE=$PROJECTS_DIR/liblouis

    # prerequisites
    sudo apt-get install -y make autoconf automake libtool pkg-config zlib1g-dev libpci-dev

    cd $PROJECTS_DIR
    rm -rf liblouis
    git clone https://github.com/liblouis/liblouis
    cd $BASE && git checkout e09c11b35b78fdf1a5c378180699e107b47c19d2

    for config_name in "${!opt_configs[@]}"; do
        CFLAGS="-g ${opt_configs[$config_name]}"

        mkdir_out "liblouis" $config_name

        make clean || true
        CXX=$CXX CXXFLAGS=$CXXFLAGS CC=$CC CFLAGS=$CFLAGS ./autogen.sh
        CXX=$CXX CXXFLAGS=$CXXFLAGS CC=$CC CFLAGS=$CFLAGS ./configure
        make -j $NPROC

        cd tests/fuzzing
        $CC $CFLAGS -c $FUZZER_SRC -o $FUZZER_OBJ
        find ../.. -name "*.o" -exec ar rcs fuzz_lib.a {} \;
        # CXXFLAGS=$CFLAGS
        # $CXX $CXXFLAGS -c table_fuzzer.cc -I/src/liblouis -o table_fuzzer.o
        # CXXFLAGS=
        # $CXX $CXXFLAGS $FUZZER_OBJ table_fuzzer.o -o $OUT/table_fuzzer fuzz_lib.a

        $CC $CFLAGS -c fuzz_translate_generic.c -o fuzz_translate_generic.o \
        -I$BASE/liblouis -I$BASE/liblouis/liblouis
        $CXX $CXXFLAGS $FUZZER_OBJ fuzz_translate_generic.o \
        -o $OUT/fuzz_translate_generic fuzz_lib.a

        $CC $CFLAGS -c fuzz_backtranslate.c -o fuzz_backtranslate.o \
        -I$BASE/liblouis -I$BASE/liblouis/liblouis
        $CXX $CXXFLAGS $FUZZER_OBJ fuzz_backtranslate.o \
        -o $OUT/fuzz_backtranslate fuzz_lib.a
        
        cd $BASE
    done
}

function libmpeg2() {
    BASE="$PROJECTS_DIR/libmpeg2"
    LIBMPEG2_OSS_FUZZ=$PROJECTS_DIR/oss-fuzz/projects/libmpeg2

    # clone the repo
    cd $PROJECTS_DIR
    rm -rf libmpeg2
    git clone https://github.com/ittiam-systems/libmpeg2.git
    cd $BASE && git checkout c8de54c9d18322dad5fe816c36f8500ec93f527d

    for config_name in "${!opt_configs[@]}"; do
        CFLAGS="-g ${opt_configs[$config_name]}"

        # compile fuzz targets
        rm -rf build
        mkdir build && cd build
        $CC $CFLAGS -c $FUZZER_SRC -o $FUZZER_OBJ
        export LIB_FUZZING_ENGINE=$FUZZER_OBJ
        mkdir_out "libmpeg2" $config_name

        CXX=$CXX CXXFLAGS=$CXXFLAGS CC=$CC CFLAGS=$CFLAGS cmake $BASE
        CXX=$CXX CXXFLAGS=$CXXFLAGS CC=$CC CFLAGS=$CFLAGS make -j $NPROC VERBOSE=1

        $CXX $CFLAGS -std=c++11 -I.  -I../  -I../common \
            -I../decoder -Wl,--start-group ../fuzzer/mpeg2_dec_fuzzer.cpp \
            -o $OUT/mpeg2_dec_fuzzer ./libmpeg2dec.a $LIB_FUZZING_ENGINE -Wl,--end-group \
            -lpthread
            
        cd $BASE
    done
}

function libpcap() {
    BASE=$PROJECTS_DIR/libpcap

    # prerequisites
    sudo apt-get install -y make cmake flex bison

    cd $PROJECTS_DIR
    rm -rf libpcap
    git clone https://github.com/the-tcpdump-group/libpcap.git libpcap
    cd $BASE && git checkout 9de890f43c722af79848d532c1a38b035f578e2d

    for config_name in "${!opt_configs[@]}"; do
        CFLAGS="-g ${opt_configs[$config_name]}"
        mkdir_out "libpcap" $config_name

        rm -rf build && mkdir build && cd build

        CXX=$CXX CXXFLAGS=$CXXFLAGS CC=$CC CFLAGS=$CFLAGS cmake ..
        make -j $NPROC

        # build fuzz targets
        $CC $CFLAGS -c $FUZZER_SRC -o $FUZZER_OBJ
        for target in pcap filter both
        do
            $CC $CFLAGS -I.. -c ../testprogs/fuzz/fuzz_$target.c -o fuzz_$target.o
            $CXX $CXXFLAGS $FUZZER_OBJ fuzz_$target.o -o $OUT/fuzz_$target libpcap.a -ldbus-1
        done
        
        cd $BASE
    done
}

function libpng() {
    BASE="$PROJECTS_DIR/libpng"

    # prerequisites
    sudo apt-get install -y make autoconf automake libtool zlib1g-dev

    # clone the repo
    cd $PROJECTS_DIR
    rm -rf libpng
    git clone https://github.com/pnggroup/libpng.git

    # the next lines are taken from libpng/contrib/oss-fuzz/build.sh
    cd $BASE && git checkout f8e5fa92b0e37ab597616f554bee254157998227

    # Disable logging via library build configuration control.
    cat scripts/pnglibconf.dfa |
    sed -e "s/option STDIO/option STDIO disabled/" \
    -e "s/option WARNING /option WARNING disabled/" \
    -e "s/option WRITE enables WRITE_INT_FUNCTIONS/option WRITE disabled/" \
    >scripts/pnglibconf.dfa.temp
    mv scripts/pnglibconf.dfa.temp scripts/pnglibconf.dfa

    for config_name in "${!opt_configs[@]}"; do
        CFLAGS="-g ${opt_configs[$config_name]}"

        # build the libpng library.
        make clean || true
        autoreconf -f -i
        CXX=$CXX CXXFLAGS=$CXXFLAGS CC=$CC CFLAGS=$CFLAGS ./configure
        make -j $NPROC libpng16.la

        # build libpng_read_fuzzer.
        mkdir_out "libpng" $config_name
        $CC $CFLAGS -c $FUZZER_SRC -o $FUZZER_OBJ
        $CXX $CXXFLAGS -std=c++11 $FUZZER_OBJ -I. \
        $BASE/contrib/oss-fuzz/libpng_read_fuzzer.cc \
        -o $OUT/libpng_read_fuzzer \
        .libs/libpng16.a -lz
        
        cd $BASE
    done
}

function libssh() {
    BASE="$PROJECTS_DIR/libssh"
    LIBSSH_OSS_FUZZ=$PROJECTS_DIR/oss-fuzz/projects/libssh

    # clone the repo
    cd $PROJECTS_DIR
    rm -rf libssh
    git clone https://git.libssh.org/projects/libssh.git libssh
    cd $BASE && git checkout 48d474f78c5f68471bf412a7dbf508ef52f7766
    cp $REPO/misc/libssh.patch .
    git apply libssh.patch

    for config_name in "${!opt_configs[@]}"; do
        CFLAGS="-g ${opt_configs[$config_name]} -lpthread"

        rm -rf build
        mkdir build && cd build
        cmake -DCMAKE_C_COMPILER="$CC" -DCMAKE_CXX_COMPILER="$CXX" \
            -DCMAKE_C_FLAGS="$CFLAGS" -DCMAKE_CXX_FLAGS="$CXXFLAGS" \
            -DBUILD_SHARED_LIBS=OFF -DWITH_INSECURE_NONE=ON -DWITH_EXEC=OFF \
            $BASE
        make -j $NPROC

        # compile fuzz targets
        $CC $CFLAGS -c $FUZZER_SRC -o $FUZZER_OBJ
        export LIB_FUZZING_ENGINE=$FUZZER_OBJ
        mkdir_out "libssh" $config_name

        shopt -s globstar
        for file in $BASE/tests/fuzz/*_fuzzer.c;
        do
            fuzzerName=$(basename $file .c)

            $CC $CFLAGS -I$BASE/include/ -I$BASE/src/ -I./ -I./include/ -c $file

            $CXX $CFLAGS $CXXFLAGS $fuzzerName.o \
                -o "$OUT/$fuzzerName" \
                $LIB_FUZZING_ENGINE ./src/libssh.a -Wl,-Bstatic -lcrypto -lz -Wl,-Bdynamic -ldl
        done
        
        cd $BASE
    done
}

function libyaml() {
    BASE=$PROJECTS_DIR/libyaml

    # prerequisites
    sudo apt-get install -y make autoconf automake libtool

    # clone the repo
    cd $PROJECTS_DIR
    rm -rf libyaml
    git clone https://github.com/yaml/libyaml

    cd $BASE && git checkout f8f760f7387d2cc56a2fc7b1be313a3bf3f7f58c
    cp $PROJECTS_DIR/oss-fuzz/projects/libyaml/*.h $PROJECTS_DIR/oss-fuzz/projects/libyaml/*_fuzzer.c $BASE

    for config_name in "${!opt_configs[@]}"; do
        CFLAGS="-g ${opt_configs[$config_name]}"

        make clean || true
        CXX=$CXX CXXFLAGS=$CXXFLAGS CC=$CC CFLAGS=$CFLAGS ./bootstrap
        CXX=$CXX CXXFLAGS=$CXXFLAGS CC=$CC CFLAGS=$CFLAGS ./configure
        make -j $NPROC

        mkdir_out "libyaml" $config_name
        $CC $CFLAGS -c $FUZZER_SRC -o $FUZZER_OBJ
        for fuzzer in $BASE/*_fuzzer.c; do
            fuzzer_basename=$(basename -s .c $fuzzer)
            $CC $CFLAGS \
            -I $BASE -Iinclude \
            -c $fuzzer -o $fuzzer_basename.o

            $CXX $CXXFLAGS \
            -std=c++11 \
            $fuzzer_basename.o \
            $FUZZER_OBJ \
            -o $OUT/$fuzzer_basename \
            src/.libs/libyaml.a
        done
        
        cd $BASE
    done
}

function lighttpd() {
    BASE="$PROJECTS_DIR/lighttpd"
    LIGHTTPD_OSS_FUZZ=$PROJECTS_DIR/oss-fuzz/projects/lighttpd

    # clone the repo
    cd $PROJECTS_DIR
    rm -rf lighttpd
    git clone https://github.com/lighttpd/lighttpd1.4 lighttpd
    cd $BASE && git checkout b41e5220f7bc9ce558d8436dabccf0f86d3a6034

    # copy fuzz targets
    cp $LIGHTTPD_OSS_FUZZ/fuzz_* .

    for config_name in "${!opt_configs[@]}"; do
        CFLAGS="-g ${opt_configs[$config_name]}"

        make clean || true
        CXX=$CXX CXXFLAGS=$CXXFLAGS CC=$CC CFLAGS=$CFLAGS ./autogen.sh
        CXX=$CXX CXXFLAGS=$CXXFLAGS CC=$CC CFLAGS=$CFLAGS ./configure --without-pcre --enable-static
        CXX=$CXX CXXFLAGS=$CXXFLAGS CC=$CC CFLAGS=$CFLAGS make -j $NPROC

        # compile fuzz targets
        $CC $CFLAGS -c $FUZZER_SRC -o $FUZZER_OBJ
        export LIB_FUZZING_ENGINE=$FUZZER_OBJ
        mkdir_out "lighttpd" $config_name

        $CC $CFLAGS -c fuzz_burl.c -Isrc/ -I.
        $CXX $CXXFLAGS $LIB_FUZZING_ENGINE fuzz_burl.o src/lighttpd-burl.o \
            src/lighttpd-buffer.o src/lighttpd-base64.o src/lighttpd-ck.o \
            -o $OUT/fuzz_burl
            
        cd $BASE
    done
}

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

function zydis() {
    BASE=$PROJECTS_DIR/zydis

    # prerequisites
    sudo apt-get install -y make

    cd $PROJECTS_DIR
    rm -rf zydis
    git clone --recursive https://github.com/zyantific/zydis.git

    cd $BASE && git checkout a6d0c713b71b5009634868389f0ff551871273d6

    for config_name in "${!opt_configs[@]}"; do
        CFLAGS="-g ${opt_configs[$config_name]}"
        mkdir_out "zydis" $config_name

        rm -rf build
        mkdir build && cd build

        cmake                                     \
        -DZYAN_FORCE_ASSERTS=ON                \
        -DZYDIS_BUILD_EXAMPLES=OFF             \
        -DZYDIS_BUILD_TOOLS=OFF                \
        -DCMAKE_BUILD_TYPE=                    \
        "-DCMAKE_C_COMPILER=${CC}"             \
        "-DCMAKE_CXX_COMPILER=${CXX}"          \
        "-DCMAKE_C_FLAGS=${CFLAGS}"            \
        "-DCMAKE_CXX_FLAGS=${CXXFLAGS}"        \
        $BASE
        make -j $NPROC VERBOSE=1

        $CC $CFLAGS -c $FUZZER_SRC -o $FUZZER_OBJ
        for fuzzer in ZydisFuzzDecoder.c ZydisFuzzEncoder.c ZydisFuzzReEncoding.c; do
            fuzzer_basename=$(basename -s .c $fuzzer)

            $CC                                    \
            $CFLAGS                             \
            -c                                  \
            "../tools/${fuzzer}"                \
            ../tools/ZydisFuzzShared.c          \
            -DZYDIS_LIBFUZZER                   \
            -I .                                \
            -I ./zycore                         \
            -I ../include                       \
            -I ../dependencies/zycore/include

            $CXX                                   \
            $CXXFLAGS                           \
            "$fuzzer_basename.o"                \
            ZydisFuzzShared.o                   \
            $FUZZER_OBJ                         \
            -o "${OUT}/${fuzzer_basename}"      \
            ./libZydis.a
        done
        
        cd $BASE
    done
}

function zlib() {
    BASE="$PROJECTS_DIR/zlib"
    ZLIB_OSS_FUZZ=$PROJECTS_DIR/oss-fuzz/projects/zlib

    # prerequisites
    sudo apt-get install -y make autoconf automake libtool

    # clone the repo
    cd $PROJECTS_DIR
    rm -rf zlib
    git clone https://github.com/madler/zlib.git zlib
    cd $BASE && git checkout 09155ea # 1.3 from github

    # copy fuzz-targets source code in repo
    shopt -s globstar
    for f in $ZLIB_OSS_FUZZ/*_fuzzer.cc; do
        cp $f $BASE
    done
    for f in $ZLIB_OSS_FUZZ/*_fuzzer.c; do
        cp $f $BASE
    done

    for config_name in "${!opt_configs[@]}"; do
        CFLAGS="-g ${opt_configs[$config_name]}"
        CXX=$CXX CXXFLAGS=$CXXFLAGS CC=$CC CFLAGS=$CFLAGS ./configure
        make -j $NPROC clean
        make -j $NPROC all
        make -j $NPROC check

        mkdir_out "zlib" $config_name

        # compile fuzzers
        $CC $CFLAGS -c $FUZZER_SRC -o $FUZZER_OBJ
        export LIB_FUZZING_ENGINE=$FUZZER_OBJ
        shopt -s globstar
        for f in ./*_fuzzer.cc; do
            b=$(basename -s .cc $f)
            $CXX $CXXFLAGS -std=c++11 -I. $f -o $OUT/$b $LIB_FUZZING_ENGINE ./libz.a
        done

        for f in ./*_fuzzer.c; do
            b=$(basename -s .c $f)
            $CC $CFLAGS -I. $f -c -o /tmp/$b.o
            $CXX $CXXFLAGS -o $OUT/$b /tmp/$b.o $LIB_FUZZING_ENGINE ./libz.a
            rm -f /tmp/$b.o
        done
        
        cd $BASE
    done
}

function display_usage() {
    echo "Usage: CC=cc CXX=cxx $0 -p <project> [-j <nproc>]"
    echo "Available projects:"
    # Loop over all defined functions excluding compile_project and display_usage
    for func in $(declare -F | cut -d ' ' -f 3); do
        if [[ "$func" != "compile_project" && "$func" != "display_usage" ]]; then
            echo "- $func"
        fi
    done
    echo "Default value for -j is $NPROC"
}

function compile_project() {
    local project_function=$1

    # Check if the function exists
    if declare -f "$project_function" >/dev/null; then
        echo "Building project: $project_function"
        # sudo apt-get update   # not needed since we are in docker and the update is done upon build
        declare -A opt_configs
        build_configs "$project_function"
        "$project_function"
    else
        # we put _ in front of projects with used names (like git)
        if declare -f "_$project_function" >/dev/null; then
            echo "Building project: $project_function"
            # sudo apt-get update   # not needed since we are in docker and the update is done upon build
            declare -A opt_configs
            build_configs "$project_function"
            "_$project_function"
        else
            echo "Error: Function $project_function not found."
            exit 1
        fi
    fi
}

# Parse command line arguments
while getopts "t:p:j:o:ch" opt; do
    case $opt in
        p)
            PROJECT=$OPTARG
        ;;
        t)
            TARGETS=$OPTARG
        ;;
        j)
            NPROC=$OPTARG
        ;;
        o)
            IFS=: OPT_LIST=($OPTARG)
            IFS=' '
        ;;
        c)
            CUSTOM_OPT_CONFIG=true
        ;;
        h)
            display_usage
            exit 0
        ;;
        \?)
            echo "Invalid option: -$OPTARG" >&2
            display_usage
            exit 1
        ;;
    esac
done

# Ensure project name is provided
if [ -z "$PROJECT" ]; then
    display_usage
    exit 1
fi

# Ensure compilers are provided via env vars
if [ -z "$CC" ] || [ -z "$CXX" ]; then
    display_usage
    exit 1
fi

compile_project $PROJECT

exit 0

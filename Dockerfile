FROM ubuntu:20.04

ARG cpu_cores

ENV DEBIAN_FRONTEND=noninteractive
RUN chmod 1777 /tmp

RUN apt-get update && \
    apt-get install -y \
    swig libedit-dev liblzma-dev libgmp-dev \
    libmpfr-dev libmpc-dev flex sudo \
    git wget zip gdb \
    afl++ afl++-clang python3-dev python3-pip \
    cargo ninja-build m4 tree \
    neovim protobuf-compiler libprotobuf-dev \
    libelf-dev libssl-dev && \
    apt-get clean && rm -rf /var/lib/apt/lists/* && \
    pip install --upgrade pip && pip install pyelftools

# create a user
RUN groupadd -r user && useradd -m -r -g user user && \
    echo 'user:password' | chpasswd && \
    usermod -aG sudo user && \
    echo "user ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers

WORKDIR /home/user

COPY --chown=user:user misc/ /home/user/misc
RUN find /home/user/misc -name '*.sh' -exec chmod +x {} \;

# setup git
RUN git config --global http.postBuffer 524288000 && \
    git config --global http.maxRequestBuffer 100M && \
    git config --global core.compression 0

# install gcc
ARG lastcommit_gcc=2ee5e4300186a92ad73f1a1a64cb918dc76c8d67
RUN git init gcc && \
    cd gcc && \
    git remote add origin https://github.com/gcc-mirror/gcc.git && \
    git fetch -v --progress origin $lastcommit_gcc && \
    git checkout FETCH_HEAD && \
    ./configure --disable-bootstrap --enable-shared=libgcc,libstdc++ \
    --disable-multilib --enable-languages=c,c++ && \
    make -j $cpu_cores && \
    make install && \
    cp /home/user/gcc/x86_64-pc-linux-gnu/libstdc++-v3/src/.libs/libstdc++.so.6 \
    /usr/lib/x86_64-linux-gnu/libstdc++.so.6 && \
    cd .. && rm -rf gcc

# install gdb
ENV CC=/usr/local/bin/gcc
RUN wget --no-check-certificate http://ftp.gnu.org/gnu/gdb/gdb-13.2.tar.xz && \
    xz -d gdb-13.2.tar.xz && tar -xvf gdb-13.2.tar && \
    cd gdb-13.2 && ./configure && make -j $cpu_cores && make install && \
    cd .. && rm gdb-13.2.tar && rm -rf gdb-13.2

# update cmake
RUN apt-get remove -y cmake && \
    wget https://github.com/Kitware/CMake/releases/download/v3.27.0/cmake-3.27.0-linux-x86_64.sh && \
    mkdir /opt/cmake && chmod +x cmake-3.27.0-linux-x86_64.sh && \
    ./cmake-3.27.0-linux-x86_64.sh --skip-license --prefix=/opt/cmake && \
    ln -s /opt/cmake/bin/cmake /usr/local/bin/cmake && \
    rm cmake-3.27.0-linux-x86_64.sh

# install llvm
ARG lastcommit_llvm=0e240b08c6ff4f891bf3741d25aca17057d6992f
RUN git init llvm-project && \
    cd llvm-project && \
    git remote add origin https://github.com/llvm/llvm-project.git && \
    git fetch -v --progress origin $lastcommit_llvm && \
    git checkout FETCH_HEAD && git apply /home/user/misc/disable-opts.patch && \
    cmake -S llvm -B build -G Ninja -DLLVM_ENABLE_PROJECTS="clang;lldb;llvm" \
    -DLLDB_ENABLE_PYTHON=1 -DCMAKE_BUILD_TYPE=Release -DLLVM_TARGETS_TO_BUILD=X86 && \
    ninja -j $cpu_cores -C build install && \
    cd .. && rm -rf llvm-project

# install autofdo
ARG lastcommit_afdo=8f9ab68921f364a6433086245ca3f19befacfeb1
RUN git init autofdo && \
    cd autofdo && \
    git remote add origin https://github.com/google/autofdo.git && \
    git fetch -v --progress origin $lastcommit_afdo && \
    git checkout FETCH_HEAD && git submodule update --init --recursive && \
    cmake -G Ninja -B build -DCMAKE_INSTALL_PREFIX="." \
                        -DENABLE_TOOL=LLVM \
                        -DCMAKE_C_COMPILER="$(which clang)" \
                        -DCMAKE_CXX_COMPILER="$(which clang++)" \
                        -DCMAKE_BUILD_WITH_INSTALL_RPATH=ON \
                        -DCMAKE_BUILD_TYPE=Release . && \
    ninja -C build -j $cpu_cores && \
    cp build/create_llvm_prof /usr/bin/create_llvm_prof && \
    cd .. && rm -rf autofdo

# install hyperfine
RUN wget https://github.com/sharkdp/hyperfine/releases/download/v1.19.0/hyperfine_1.19.0_amd64.deb && \
    dpkg -i hyperfine_1.19.0_amd64.deb && rm hyperfine_1.19.0_amd64.deb

# copy framework source code
COPY --chown=user:user src/ /home/user/debugtuner
RUN find /home/user/debugtuner -name '*.sh' -exec chmod +x {} \;

# clone the ossfuzz repo
ARG lastcommit_ossfuzz=a08163443c357a0b0a78b04d7bf2fcb31c0b7f82
RUN mkdir /home/user/debugtuner/dt-projects && \
    git clone https://github.com/google/oss-fuzz.git /home/user/debugtuner/dt-projects/oss-fuzz && \
    cd /home/user/debugtuner/dt-projects/oss-fuzz && git checkout $lastcommit_ossfuzz

ENTRYPOINT ["/bin/bash"]

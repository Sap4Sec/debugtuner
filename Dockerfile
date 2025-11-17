FROM ubuntu:20.04

ARG cpu_cores

ENV DEBIAN_FRONTEND=noninteractive
RUN chmod 1777 /tmp

RUN apt-get update
RUN apt-get install -y swig libedit-dev liblzma-dev libgmp-dev libmpfr-dev libmpc-dev flex sudo git wget zip gdb afl++ afl++-clang python3-dev python3-pip cargo ninja-build m4 tree neovim protobuf-compiler libprotobuf-dev libelf-dev libssl-dev

# create a user
RUN groupadd -r user && useradd -m -r -g user user
RUN echo 'user:password' | chpasswd
RUN usermod -aG sudo user
RUN echo "user ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers

WORKDIR /home/user

# setup git
RUN git config --global http.postBuffer 524288000
RUN git config --global http.maxRequestBuffer 100M
RUN git config --global core.compression 0

# install gcc
ARG lastcommit_gcc=2ee5e4300186a92ad73f1a1a64cb918dc76c8d67
RUN git clone --progress --verbose https://github.com/gcc-mirror/gcc.git
RUN cd gcc && git checkout $lastcommit_gcc
RUN cd gcc && ./configure --enable-shared=libgcc,libstdc++ --disable-multilib --enable-languages=c,c++ && make -j $cpu_cores
RUN cd gcc && make install

# install gdb
RUN wget --no-check-certificate http://ftp.gnu.org/gnu/gdb/gdb-13.2.tar.xz && xz -d gdb-13.2.tar.xz && tar -xvf gdb-13.2.tar
ENV CC=/usr/local/bin/gcc
RUN cd gdb-13.2 && ./configure && make -j $cpu_cores && make install
RUN rm gdb-13.2.tar
RUN cp /home/user/gcc/x86_64-pc-linux-gnu/libstdc++-v3/src/.libs/libstdc++.so.6 /usr/lib/x86_64-linux-gnu/libstdc++.so.6

# update cmake
RUN apt-get remove -y cmake && \
    wget https://github.com/Kitware/CMake/releases/download/v3.27.0/cmake-3.27.0-linux-x86_64.sh && \
    mkdir /opt/cmake && chmod +x cmake-3.27.0-linux-x86_64.sh && \
    ./cmake-3.27.0-linux-x86_64.sh --skip-license --prefix=/opt/cmake && \
    ln -s /opt/cmake/bin/cmake /usr/local/bin/cmake && \
    rm cmake-3.27.0-linux-x86_64.sh

# install llvm
ARG lastcommit_llvm=0e240b08c6ff4f891bf3741d25aca17057d6992f
RUN git clone --progress --verbose https://github.com/llvm/llvm-project.git

# copy the framework directory as late as we can
COPY --chown=user:user src/ /home/user/debugtuner

RUN cd llvm-project && git checkout $lastcommit_llvm && git apply /home/user/debugtuner/misc/disable-opts.patch
RUN cd llvm-project && cmake -S llvm -B build -G Ninja -DLLVM_ENABLE_PROJECTS="clang;lldb;llvm" -DLLVM_PARALLEL_LINK_JOBS=1 -DLLDB_ENABLE_PYTHON=1 -DCMAKE_BUILD_TYPE=Release -DLLVM_TARGETS_TO_BUILD=X86
RUN cd llvm-project && ninja -j $cpu_cores -C build install

ARG lastcommit_afdo=8f9ab68921f364a6433086245ca3f19befacfeb1
RUN git clone --recursive https://github.com/google/autofdo.git
RUN cd autofdo && cmake -G Ninja -B build -DCMAKE_INSTALL_PREFIX="." \
                        -DENABLE_TOOL=LLVM \
                        -DCMAKE_C_COMPILER="$(which clang)" \
                        -DCMAKE_CXX_COMPILER="$(which clang++)" \
                        -DCMAKE_BUILD_WITH_INSTALL_RPATH=ON \
                        -DCMAKE_BUILD_TYPE=Release .
RUN cd autofdo && ninja -C build -j $cpu_cores

# clone the ossfuzz repo, install python requirements
ARG lastcommit_ossfuzz=a08163443c357a0b0a78b04d7bf2fcb31c0b7f82
RUN cd /home/user/debugtuner/ && mkdir dt-projects
RUN git clone https://github.com/google/oss-fuzz.git /home/user/debugtuner/dt-projects/oss-fuzz
RUN cd /home/user/debugtuner/dt-projects/oss-fuzz && git checkout $lastcommit_ossfuzz
RUN pip install --upgrade pip && pip install pyelftools

# install hyperfine
RUN wget https://github.com/sharkdp/hyperfine/releases/download/v1.19.0/hyperfine_1.19.0_amd64.deb && dpkg -i hyperfine_1.19.0_amd64.deb && rm hyperfine_1.19.0_amd64.deb

ENTRYPOINT ["/bin/bash"]

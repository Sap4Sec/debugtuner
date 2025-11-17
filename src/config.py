from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

TIMEOUT = 4000

# dict with programs supported and list of fuzz targets to test
_projects = {}

_projects["bzip2"] = [
    "bzip2_compress_target",
    "bzip2_decompress_target",
    "bzip2_fd",
    "bzip2_filename",
]

_projects["libdwarf"] = [
    "fuzz_aranges",
    "fuzz_debug_addr_access",
    "fuzz_debug_str",
    "fuzz_debuglink",
    "fuzz_die_cu",
    "fuzz_die_cu_attrs",
    "fuzz_die_cu_attrs_loclist",
    "fuzz_die_cu_info1",
    "fuzz_die_cu_offset",
    "fuzz_die_cu_print",
    "fuzz_dnames",
    "fuzz_findfuncbypc",
    "fuzz_gdbindex",
    "fuzz_globals",
    "fuzz_gnu_index",
    "fuzz_init_b",
    "fuzz_init_binary",
    "fuzz_init_path",
    "fuzz_macro_dwarf4",
    "fuzz_macro_dwarf5",
    "fuzz_rng",
    "fuzz_showsectgrp",
    "fuzz_simplereader_tu",
    "fuzz_srcfiles",
    "fuzz_stack_frame_access",
    "fuzz_str_offsets",
    "fuzz_tie",
    "fuzz_xuindex",
]

_projects["libexif"] = ["exif_from_data_fuzzer", "exif_loader_fuzzer"]

_projects["liblouis"] = ["fuzz_translate_generic", "fuzz_backtranslate"]

_projects["libmpeg2"] = ["mpeg2_dec_fuzzer"]

_projects["libpcap"] = ["fuzz_both"]

_projects["libpng"] = ["libpng_read_fuzzer"]

_projects["libssh"] = [
    "ssh_client_fuzzer",
    "ssh_known_hosts_fuzzer",
    "ssh_privkey_fuzzer",
    "ssh_pubkey_fuzzer",
]

_projects["lighttpd"] = ["fuzz_burl"]

_projects["libyaml"] = [
    "libyaml_emitter_fuzzer",
    "libyaml_parser_fuzzer",
    "libyaml_scanner_fuzzer",
    "libyaml_deconstructor_alt_fuzzer",
    "libyaml_dumper_fuzzer",
    "libyaml_loader_fuzzer",
    "libyaml_deconstructor_fuzzer",
    "libyaml_reformatter_fuzzer",
    "libyaml_reformatter_alt_fuzzer",
]

_projects["wasm3"] = ["fuzzer"]

_projects["zlib"] = [
    "checksum_fuzzer",
    "compress_fuzzer",
    "example_dict_fuzzer",
    "example_flush_fuzzer",
    "example_large_fuzzer",
    "example_small_fuzzer",
    "minigzip_fuzzer",
    "zlib_uncompress2_fuzzer",
    "zlib_uncompress_fuzzer",
]

_projects["zydis"] = ["ZydisFuzzDecoder", "ZydisFuzzEncoder", "ZydisFuzzReEncoding"]

projects = {}
projects_minimal = {}

projects["gcc"] = _projects.copy()
projects["clang"] = _projects.copy()

projects["clang"].pop("liblouis")
projects["clang"].pop("libpcap")
projects["clang"].pop("libmpeg2")

projects_minimal["gcc"] = {k: v for k, v in _projects.items() if k in ["wasm3", "zydis"]}
projects_minimal["clang"] = {k: v for k, v in _projects.items() if k in ["wasm3", "zydis"]}


@dataclass
class CompilerConfig:
    include: List[Path]
    preproc: List[str]


# dict with include paths and preprocessor variables to be defined for ast parsing
ast_config: Dict[str, CompilerConfig] = {}
ast_config["bzip2"] = CompilerConfig([], [])
ast_config["libdwarf"] = CompilerConfig([], [])
ast_config["libexif"] = CompilerConfig(
    [],
    [
        'GETTEXT_PACKAGE="placeholder"',
        'LOCALEDIR="placeholder"',
    ],
)
ast_config["liblouis"] = CompilerConfig([], ['TABLESDIR="placeholder"'])
ast_config["libmpeg2"] = CompilerConfig([], [])
ast_config["libpcap"] = CompilerConfig([], ['PACKAGE_VERSION="placeholder"'])
ast_config["libpng"] = CompilerConfig([], [])
ast_config["libssh"] = CompilerConfig(
    [],
    [
        "WITH_INSECURE_NONE",
        "HAVE_LIBCRYPTO",
        "HAVE_STRTOULL",
        "HAVE_COMPILER__FUNC__",
    ],
)
ast_config["libyaml"] = CompilerConfig(
    [],
    [
        'YAML_VERSION_STRING="placeholder"',
        "YAML_VERSION_MAJOR=0",
        "YAML_VERSION_MINOR=0",
        "YAML_VERSION_PATCH=0",
    ],
)
ast_config["lighttpd"] = CompilerConfig([], ["HAVE_STDINT_H", "HAVE_TIMEGM"])
ast_config["wasm3"] = CompilerConfig([], ["M3_COMPILE_OPCODES"])
ast_config["zlib"] = CompilerConfig([], [])
ast_config["zydis"] = CompilerConfig([], ["ZYDIS_LIBFUZZER"])


# function to blacklist files that are making our static analyzer crash
def blacklisted(source_name, project_dir):
    if "liblouis" in project_dir:
        if "free.c" in source_name:
            return True
    elif "libdwarf" in project_dir:
        if ".h" in source_name:
            return True
    elif "libpcap" in project_dir:
        if "grammar.c" in source_name:
            return True
        if ".l" in source_name:
            return True
    return False

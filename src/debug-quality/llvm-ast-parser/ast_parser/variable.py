from __future__ import annotations

import ast_parser.statement as statement


class Variable:
    def __init__(self, id: int, parent: statement.Statement) -> None:
        super().__init__()

        self.id = id
        self.parent = parent

        self.name: str = None
        self.type: str = None

        self.decl_loc: int = None
        self.init_loc: int = None

        self.is_pointer: bool = False
        self.is_init: bool = False
        self.is_param: bool = False

    @staticmethod
    def parse(parent: statement.Statement, node, decl_loc: int) -> Variable:
        node_id = int(node["id"], 16)
        variable = Variable(node_id, parent)

        variable.is_param = node["kind"] == "ParmVarDecl"
        variable.decl_loc = decl_loc

        if "inner" in node or variable.is_param:
            variable.is_init = True
            variable.init_loc = decl_loc

        if "type" in node:
            type_tag = "qualType"
            if "desugaredType" in node["type"]:
                type_tag = "desugaredType"
            variable.type = node["type"][type_tag]

            if "*" in variable.type or "[" in variable.type:
                variable.is_pointer = True

        if "name" in node:
            variable.name = node["name"]

        return variable

    def __str__(self) -> str:
        kind = ["Variable", "Param"][self.is_param]
        out = f"{kind} {hex(self.id)} {{\n"

        init_str = ["uninit", self.init_loc][self.is_init]
        ptr_str = ["", "pointer"][self.is_pointer]
        out += f"\tdecl: {self.decl_loc}, init: {init_str}, {ptr_str}\n"

        if self.name is not None:
            out += f"\t'{self.type} {self.name}'\n"
        out += "}"

        return out

    def __hash__(self) -> int:
        return hash(self.id)

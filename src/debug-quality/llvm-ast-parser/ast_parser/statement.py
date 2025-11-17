from __future__ import annotations
from dataclasses import dataclass
from typing import List, Set

from ast_parser.variable import Variable


@dataclass
class StatementLocation:
    start_loc: int
    end_loc: int


class Statement:

    def __init__(self, id: int, kind: str, parent: Statement) -> None:
        self.id = id
        self.kind = kind
        self.parent = parent

        self.name: str = None
        self.type: str = None
        self.loc: StatementLocation = None

        self.body: List[Statement] = []
        self.variables: List[Variable] = []
        self.references: Set[int] = set()

        # only for function actually defined in the file under analysis
        self.is_function: bool = False

        self.node = None

    @staticmethod
    def __parse_loc(node) -> StatementLocation:
        start_loc, end_loc = None, None

        if "loc" in node:
            if "line" in node["loc"]:
                start_loc = node["loc"]["line"]
            elif "expansionLoc" in node["loc"] and "line" in node["loc"]["expansionLoc"]:
                start_loc = node["loc"]["expansionLoc"]["line"]

        if "range" in node:
            if start_loc is None:
                if "line" in node["range"]["begin"]:
                    start_loc = node["range"]["begin"]["line"]

                if start_loc is None:
                    if "expansionLoc" in node["range"]["begin"]:
                        if "line" in node["range"]["begin"]["expansionLoc"]:
                            start_loc = node["range"]["begin"]["expansionLoc"]["line"]

            if "line" in node["range"]["end"]:
                end_loc = node["range"]["end"]["line"]

            if end_loc is None:
                if "expansionLoc" in node["range"]["end"]:
                    if "line" in node["range"]["end"]["expansionLoc"]:
                        end_loc = node["range"]["end"]["expansionLoc"]["line"]

        return StatementLocation(start_loc, end_loc)

    def find_referenced_var(self) -> Set[Variable]:
        out = set()
        for ref in self.references:
            var = self.find_var_by_id(ref)
            if var is not None:
                out.add(var)

        for child in self.body:
            out.update(child.find_referenced_var())
        return out

    def find_var_by_id(self, var_id) -> Statement:
        for var in self.variables:
            if var.id == var_id:
                return var

        if self.parent is None:
            return None
        return self.parent.find_var_by_id(var_id)

    def __find(self, admitted: List[str]) -> List[Statement]:
        out = []
        if self.kind in admitted:
            out.append(self)

        for child in self.body:
            out += child.__find(admitted)
        return out

    def find_conditionals(self) -> List[Statement]:
        return self.__find(["IfStmt", "SwitchStmt"])

    def find_calls(self, check_func: bool = True) -> List[Statement]:
        return self.__find(["CallExpr"])

    def find_loops(self, check_func: bool = True) -> List[Statement]:
        return self.__find(["WhileStmt", "DoStmt", "ForStmt"])

    def __find_statement_at_exact(self, line: int) -> Statement:
        for child in self.body:
            stmt = child.__find_statement_at_exact(line)

            if stmt is not None and stmt.loc.start_loc == line:
                return stmt

        if self.loc.start_loc == line:
            return self
        return None

    def __find_statement_at_inrange(self, line: int) -> Statement:
        for child in self.body:
            good_to_go = child.loc.start_loc and child.loc.end_loc

            if good_to_go and child.loc.start_loc <= line <= child.loc.end_loc:
                return child.__find_statement_at_inrange(line)

        good_to_go = self.loc.start_loc and self.loc.end_loc
        if good_to_go and self.loc.start_loc <= line <= self.loc.end_loc:
            return self
        return None

    def find_statement_at(self, line: int) -> Statement:
        stmt = self.__find_statement_at_exact(line)
        if stmt is not None:
            return stmt
        return self.__find_statement_at_inrange(line)

    def find_valid_loc(self) -> StatementLocation:
        if self.parent is None:
            return None
        if self.loc is None or self.loc.start_loc is None:
            return self.parent.find_valid_loc()
        return self.loc

    def parse_globals(self) -> List[Variable]:
        out = []
        for stmt in self.body:
            if stmt.kind == "VarDecl":
                loc = Statement.__parse_loc(stmt.node).start_loc
                out.append(Variable.parse(None, stmt.node, loc))
        return out

    @staticmethod
    def parse(parent: Statement, node) -> Statement:
        # skip empty nodes
        if not "kind" in node:
            return None

        stmt_id = int(node["id"], 16)
        stmt = Statement(stmt_id, node["kind"], parent)
        stmt.node = node

        # NOTE: this can be shit
        if stmt.kind == "FunctionDecl":
            if not "includedFrom" in stmt.node["loc"]:
                stmt.is_function = True

                if "expansionLoc" in node["loc"]:
                    if not "line" in node["loc"]["expansionLoc"]:
                        stmt.is_function = False
                    if "includedFrom" in node["loc"]["expansionLoc"]:
                        stmt.is_function = False

                if "storageClass" in stmt.node:
                    if stmt.node["storageClass"] == "extern":
                        stmt.is_function = False
            else:
                stmt.is_function = False

        if "name" in node:
            stmt.name = node["name"]

        if "type" in node:
            type_tag = "qualType"
            if "desugaredType" in node["type"]:
                type_tag = "desugaredType"
            stmt.type = node["type"][type_tag]

        stmt.loc = Statement.__parse_loc(node)

        # NOTE: drop those functions that have no correct location
        if stmt.kind == "FunctionDecl":
            if stmt.is_function:
                if stmt.loc is None or stmt.loc.start_loc is None or stmt.loc.end_loc is None:
                    stmt.is_function = False

        if not "inner" in node:
            return stmt

        for elem in node["inner"]:
            if "kind" in elem:
                if elem["kind"] == "DeclStmt":
                    for inner_node in elem["inner"]:
                        if inner_node["kind"] != "VarDecl":
                            continue
                        loc = Statement.__parse_loc(elem).start_loc

                        # NOTE: if loc is none, meaning that we are at the same line as parent
                        # thus we can extract from it the location
                        current = stmt
                        while loc is None or current is None:
                            if current.loc is not None:
                                loc = current.loc.start_loc
                            current = stmt.parent

                        stmt.variables.append(Variable.parse(parent, inner_node, loc))

                elif elem["kind"] == "DeclRefExpr":
                    ref_id = int(elem["referencedDecl"]["id"], 16)
                    stmt.references.add(ref_id)

                    # NOTE: we assume that the code is correct as in, no usage of
                    # uninitialized var but initialization
                    # thus if a var is not initialized, we initialize it
                    var = stmt.find_var_by_id(ref_id)
                    if var is not None and not var.is_init:
                        loc = stmt.find_valid_loc()
                        if loc is not None:
                            var.is_init = True
                            var.init_loc = loc.start_loc

                # NOTE: when parameters defined at the same line, only the first
                # will have the location defined. But sometimes it is not defined
                # so we will take it from the function
                elif elem["kind"] == "ParmVarDecl":
                    loc = Statement.__parse_loc(elem).start_loc
                    if stmt.is_function and loc is None:
                        if len(stmt.variables) > 0:
                            loc = stmt.variables[-1].decl_loc
                        else:
                            loc = stmt.loc.start_loc
                    stmt.variables.append(Variable.parse(parent, elem, loc))

            child_stmt = Statement.parse(stmt, elem)
            if child_stmt is not None:
                stmt.body.append(child_stmt)

        return stmt

    def __str__(self) -> str:
        references = ""
        for var_id in self.references:
            found = self.find_var_by_id(var_id)
            if found is None:
                continue
            references += "Referenced " + found.__str__() + "\n"
        references = "\n\t".join(references.split("\n"))

        variables = ""
        for var in self.variables:
            variables += var.__str__() + "\n"
        variables = "\n\t".join(variables.split("\n"))

        body = ""
        for stmt in self.body:
            body += stmt.__str__() + "\n"
        body = "\n\t".join(body.split("\n"))

        out = f"{self.kind} {hex(self.id)} {{\n"
        if self.name:
            out += f"\t{self.type} {self.name}, {self.is_function}\n"

        if self.loc and not (self.loc.start_loc is None and self.loc.end_loc is None):
            out += f"\t{self.loc.start_loc,self.loc.end_loc}\n"
        if variables:
            out += f"\t{variables}\n"
        if references:
            out += f"\t{references}\n"
        if body:
            out += f"\t{body}\n"
        out += "}"

        return out

    def __hash__(self) -> int:
        return hash(self.id)

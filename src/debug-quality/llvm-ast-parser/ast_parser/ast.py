from __future__ import annotations
from dataclasses import dataclass
import json
import pickle
from typing import List, Set

from ast_parser.statement import Statement
from ast_parser.dumpable import Dumpable
from ast_parser.variable import Variable


@dataclass
class ASTResult:
    statement: Statement
    variables: Set[Variable]


class AST(Dumpable):
    def __init__(self, ast) -> None:
        super().__init__()
        # self.ast: Statement = Statement.parse(None, json.loads(ast))

        json_ast = json.loads(ast)
        ast = Statement.parse(None, json_ast)

        self.globals: List[Variable] = ast.parse_globals()

        self.functions: List[Statement] = []
        for stmt in ast.body:
            if stmt.is_function:
                self.functions.append(stmt)

    def find_live_vars_at(self, line: int) -> Set[Variable]:
        out = set()

        func = self.find_function_at(line)
        if func is None:
            return None

        stmt = func.find_statement_at(line)
        if stmt is None:
            return None

        current = stmt
        while current is not None:
            for var in current.variables:
                if var.is_init and var.init_loc < line:
                    out.add(var)
            current = current.parent

        return out

    def find_used_vars_at(self, line: int) -> Set[Variable]:
        func = self.find_function_at(line)
        if func is None:
            return None

        stmt = func.find_statement_at(line)
        if stmt is None:
            return None

        # NOTE: find outer node
        current = stmt
        while current is not None:
            if current.parent.loc.start_loc != line:
                break
            current = current.parent

        return current.find_referenced_var()

    def find_conditionals(self) -> List[ASTResult]:
        results = []
        for func in self:
            for stmt in func.find_conditionals():
                results.append(ASTResult(stmt, stmt.body[0].find_referenced_var()))
        return results

    def find_calls(self) -> List[ASTResult]:
        results = []
        for func in self:
            for stmt in func.find_calls():
                results.append(ASTResult(stmt, stmt.find_referenced_var()))
        return results

    def find_loops(self) -> List[ASTResult]:
        results = []
        for func in self:
            for stmt in func.find_loops():
                # NOTE: the condition is the first body entry
                if stmt.kind == "WhileStmt":
                    results.append(ASTResult(stmt, stmt.body[0].find_referenced_var()))
                # NOTE: init;cond;update at the beginning of body
                elif stmt.kind == "ForStmt":
                    variables = set()
                    for child in stmt.body:
                        # NOTE: when we reach compound it means we are in the for body
                        if child.kind == "CompoundStmt":
                            break
                        variables.update(child.find_referenced_var())
                    results.append(ASTResult(stmt, variables))
                # NOTE: the condition is the last body entry
                elif stmt.kind == "DoStmt":
                    results.append(ASTResult(stmt, stmt.body[-1].find_referenced_var()))
        return results

    def find_global_updates(self) -> List[ASTResult]:
        results = []
        for func in self:
            queue = func.body

            while len(queue) > 0:
                stmt = queue.pop(0)

                if len(stmt.body) > 1 and stmt.body[0].kind == "DeclRefExpr":
                    for ref in stmt.references:
                        glob = self.find_global_by_id(ref)
                        if glob is not None:
                            break
                    if glob is not None:
                        results.append(ASTResult(stmt, stmt.find_referenced_var()))
                queue += stmt.body
        return results

    def find_function_at(self, line: int) -> Statement:
        for func in self.functions:
            if func.loc.start_loc <= line <= func.loc.end_loc:
                return func
        return None

    def find_global_by_id(self, var_id) -> Variable:
        for var in self.globals:
            if var.id == var_id:
                return var
        return None

    def __iter__(self):
        return iter(self.functions)

    def __next__(self):
        return next(self.functions)

    def __str__(self) -> str:
        out = ""
        for func in self.functions:
            out += f"{func.__str__()}\n"
        return out

    @staticmethod
    def load(fin: str) -> AST:
        with open(fin, "rb") as f:
            return pickle.load(f)

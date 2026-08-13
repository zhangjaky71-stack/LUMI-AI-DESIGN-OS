from __future__ import annotations

import ast
from typing import Any

from .errors import RecipeExpressionError

_ALLOWED_ROOTS = frozenset({"inputs", "project", "steps", "run"})
_ALLOWED_COMPARE = (
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.In,
    ast.NotIn,
    ast.Is,
    ast.IsNot,
)


def validate_expression(expression: str) -> str:
    if not expression or len(expression) > 1000 or "\x00" in expression:
        raise RecipeExpressionError("RECIPE_EXPRESSION_INVALID")
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise RecipeExpressionError("RECIPE_EXPRESSION_SYNTAX_INVALID") from exc
    _validate_node(tree.body)
    return expression


def evaluate_expression(expression: str, context: dict[str, Any]) -> bool:
    validate_expression(expression)
    tree = ast.parse(expression, mode="eval")
    value = _evaluate(tree.body, context)
    if not isinstance(value, bool):
        raise RecipeExpressionError("RECIPE_EXPRESSION_MUST_RETURN_BOOL")
    return value


def _validate_node(node: ast.AST) -> None:
    if isinstance(node, ast.Name):
        if node.id not in _ALLOWED_ROOTS:
            raise RecipeExpressionError(f"RECIPE_EXPRESSION_ROOT_FORBIDDEN:{node.id}")
        return
    if isinstance(node, ast.Attribute):
        if node.attr.startswith("_"):
            raise RecipeExpressionError("RECIPE_EXPRESSION_PRIVATE_ATTRIBUTE_FORBIDDEN")
        _validate_node(node.value)
        return
    if isinstance(node, ast.Constant):
        if not isinstance(node.value, (str, int, float, bool, type(None))):
            raise RecipeExpressionError("RECIPE_EXPRESSION_CONSTANT_FORBIDDEN")
        return
    if isinstance(node, ast.BoolOp):
        if not isinstance(node.op, (ast.And, ast.Or)):
            raise RecipeExpressionError("RECIPE_EXPRESSION_BOOL_OP_FORBIDDEN")
        for value in node.values:
            _validate_node(value)
        return
    if isinstance(node, ast.UnaryOp):
        if not isinstance(node.op, ast.Not):
            raise RecipeExpressionError("RECIPE_EXPRESSION_UNARY_OP_FORBIDDEN")
        _validate_node(node.operand)
        return
    if isinstance(node, ast.Compare):
        _validate_node(node.left)
        if not all(isinstance(op, _ALLOWED_COMPARE) for op in node.ops):
            raise RecipeExpressionError("RECIPE_EXPRESSION_COMPARE_FORBIDDEN")
        for comparator in node.comparators:
            _validate_node(comparator)
        return
    if isinstance(node, (ast.List, ast.Tuple)):
        for item in node.elts:
            _validate_node(item)
        return
    raise RecipeExpressionError(
        f"RECIPE_EXPRESSION_NODE_FORBIDDEN:{type(node).__name__}"
    )


def _evaluate(node: ast.AST, context: dict[str, Any]) -> Any:
    if isinstance(node, ast.Name):
        try:
            return context[node.id]
        except KeyError as exc:
            raise RecipeExpressionError(
                f"RECIPE_EXPRESSION_CONTEXT_MISSING:{node.id}"
            ) from exc
    if isinstance(node, ast.Attribute):
        parent = _evaluate(node.value, context)
        if not isinstance(parent, dict) or node.attr not in parent:
            raise RecipeExpressionError(
                f"RECIPE_EXPRESSION_PATH_MISSING:{node.attr}"
            )
        return parent[node.attr]
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.List):
        return [_evaluate(item, context) for item in node.elts]
    if isinstance(node, ast.Tuple):
        return tuple(_evaluate(item, context) for item in node.elts)
    if isinstance(node, ast.BoolOp):
        values = [_evaluate(item, context) for item in node.values]
        if not all(isinstance(item, bool) for item in values):
            raise RecipeExpressionError("RECIPE_EXPRESSION_BOOL_VALUE_REQUIRED")
        return all(values) if isinstance(node.op, ast.And) else any(values)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        value = _evaluate(node.operand, context)
        if not isinstance(value, bool):
            raise RecipeExpressionError("RECIPE_EXPRESSION_BOOL_VALUE_REQUIRED")
        return not value
    if isinstance(node, ast.Compare):
        left = _evaluate(node.left, context)
        for operator, comparator_node in zip(node.ops, node.comparators, strict=True):
            right = _evaluate(comparator_node, context)
            if not _compare(operator, left, right):
                return False
            left = right
        return True
    raise RecipeExpressionError("RECIPE_EXPRESSION_EVALUATION_FORBIDDEN")


def _compare(operator: ast.cmpop, left: Any, right: Any) -> bool:
    try:
        if isinstance(operator, ast.Eq):
            return left == right
        if isinstance(operator, ast.NotEq):
            return left != right
        if isinstance(operator, ast.Lt):
            return left < right
        if isinstance(operator, ast.LtE):
            return left <= right
        if isinstance(operator, ast.Gt):
            return left > right
        if isinstance(operator, ast.GtE):
            return left >= right
        if isinstance(operator, ast.In):
            return left in right
        if isinstance(operator, ast.NotIn):
            return left not in right
        if isinstance(operator, ast.Is):
            return left is right
        if isinstance(operator, ast.IsNot):
            return left is not right
    except (TypeError, ValueError) as exc:
        raise RecipeExpressionError("RECIPE_EXPRESSION_COMPARE_TYPE_INVALID") from exc
    raise RecipeExpressionError("RECIPE_EXPRESSION_COMPARE_FORBIDDEN")

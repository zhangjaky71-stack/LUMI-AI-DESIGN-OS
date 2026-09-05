class RecipeEngineError(RuntimeError):
    pass


class RecipeDefinitionInvalidError(RecipeEngineError):
    pass


class RecipeNotFoundError(RecipeEngineError):
    pass


class RecipeReleaseError(RecipeEngineError):
    pass


class RecipeVersionResolutionError(RecipeEngineError):
    pass


class RecipeDependencyError(RecipeEngineError):
    pass


class RecipeCycleError(RecipeDependencyError):
    pass


class RecipeReferenceError(RecipeEngineError):
    pass


class RecipeExpressionError(RecipeEngineError):
    pass


class RecipeSecurityError(RecipeEngineError):
    pass


class RecipeCompileError(RecipeEngineError):
    pass


class RecipeBudgetError(RecipeCompileError):
    pass

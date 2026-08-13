class DesignIRError(ValueError):
    """Base Design IR contract failure."""


class StructuralValidationError(DesignIRError):
    """Document shape or graph invariants are invalid."""


class ResourceReferenceError(DesignIRError):
    """A node references a resource that is absent from the document registry."""


class DocumentVersionConflict(DesignIRError):
    """An operation targets a stale document version."""


class OperationError(DesignIRError):
    """A structured design operation cannot be applied."""

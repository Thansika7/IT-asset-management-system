from fastapi import HTTPException, status

class AppBaseException(HTTPException):
    def __init__(self, status_code: int, detail: str):
        super().__init__(status_code=status_code, detail=detail)

class ResourceNotFoundError(AppBaseException):
    def __init__(self, resource: str, identifier: str):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"The requested {resource} with ID '{identifier}' could not be located in our records."
        )

class InsufficientStockError(AppBaseException):
    def __init__(self, asset_name: str, available: int):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unable to process allocation for '{asset_name}'. Only {available} units are currently available."
        )

class UnauthorizedActionError(AppBaseException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have the necessary permissions to perform this security-restricted action."
        )

class InvalidStateError(AppBaseException):
    def __init__(self, message: str):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message
        )

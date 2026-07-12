from fastapi import status

class SinpesError(Exception):
    """Base class for all application-specific exceptions."""
    def __init__(self, message: str, status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)

class ValidationError(SinpesError):
    def __init__(self, message: str = "Validation failed"):
        super().__init__(message, status.HTTP_422_UNPROCESSABLE_ENTITY)

class NotFoundError(SinpesError):
    def __init__(self, message: str = "Resource not found"):
        super().__init__(message, status.HTTP_404_NOT_FOUND)

class DuplicateFontError(SinpesError):
    def __init__(self, message: str = "Font already exists"):
        super().__init__(message, status.HTTP_409_CONFLICT)

class IngestionError(SinpesError):
    def __init__(self, message: str = "Ingestion process failed"):
        super().__init__(message, status.HTTP_500_INTERNAL_SERVER_ERROR)

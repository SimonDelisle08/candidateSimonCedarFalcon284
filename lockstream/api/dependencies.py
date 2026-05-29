from fastapi import Request

from ..application.service import LockStreamService


# hand back the single service create_app 
def get_service(request: Request) -> LockStreamService:
    return request.app.state.service

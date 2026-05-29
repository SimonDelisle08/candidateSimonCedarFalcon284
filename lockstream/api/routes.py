from fastapi import APIRouter, Depends, HTTPException, Response, status

from ..application.service import IngestOutcome, LockStreamService
from ..domain.errors import DomainRuleViolation, PayloadValidationError
from .dependencies import get_service
from .schemas import CompartmentStatusOut, EventIn, LockerSummaryOut, ReservationStatusOut

router = APIRouter()


# the only place domain errors turn into HTTP status codes
@router.post("/events")
def ingest_event(event: EventIn, service: LockStreamService = Depends(get_service)) -> Response:
    try:
        outcome = service.ingest(event.to_record())
    except PayloadValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    except DomainRuleViolation as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    code = status.HTTP_200_OK if outcome is IngestOutcome.DUPLICATE else status.HTTP_202_ACCEPTED
    return Response(status_code=code)


@router.get("/lockers/{locker_id}", response_model=LockerSummaryOut)
def get_locker(locker_id: str, service: LockStreamService = Depends(get_service)) -> LockerSummaryOut:
    summary = service.locker_summary(locker_id)
    if summary is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"unknown locker {locker_id}")
    return LockerSummaryOut(**summary)


@router.get(
    "/lockers/{locker_id}/compartments/{compartment_id}",
    response_model=CompartmentStatusOut,
)
def get_compartment(
    locker_id: str,
    compartment_id: str,
    service: LockStreamService = Depends(get_service),
) -> CompartmentStatusOut:
    view = service.compartment_status(locker_id, compartment_id)
    if view is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"unknown compartment {compartment_id}")
    return CompartmentStatusOut(**view)


@router.get("/reservations/{reservation_id}", response_model=ReservationStatusOut)
def get_reservation(
    reservation_id: str,
    service: LockStreamService = Depends(get_service),
) -> ReservationStatusOut:
    view = service.reservation_status(reservation_id)
    if view is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"unknown reservation {reservation_id}")
    return ReservationStatusOut(**view)

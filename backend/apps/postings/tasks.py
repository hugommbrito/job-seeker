"""Background work on captured postings."""

from __future__ import annotations

from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from apps.accounts.models import User
from apps.llm.models import CallOutcome
from apps.llm.service import TaskResult, run_task
from apps.operations.runs import recorded
from apps.postings.extraction import CAPTURE_EXTRACTION, CaptureExtraction, model_input, verify
from apps.postings.models import ExtractionStatus, UserPosting
from apps.tenancy.context import tenant_context

# A capture still being read after this long was never picked up (the broker or the worker was
# down). It is handed back to the user to fill in, instead of waiting forever.
STALLED_AFTER = timedelta(minutes=15)


@shared_task(name="postings.extract_capture")
def extract_capture(user_id: int, capture_id: int) -> None:
    with tenant_context(user_id):
        capture = UserPosting.objects.filter(
            pk=capture_id, extraction_status=ExtractionStatus.PENDING
        ).first()
        if capture is None:
            return
        text, url = capture.description_text, capture.url

    # The model call happens here, outside any tenant context: that is an open transaction.
    result: TaskResult[CaptureExtraction] = run_task(
        user_id=user_id,
        task=CAPTURE_EXTRACTION,
        entity=("user_posting", capture_id),
        content=model_input(text, url),
    )

    with tenant_context(user_id):
        capture = UserPosting.objects.filter(pk=capture_id).first()
        if capture is None:  # discarded while it was being read
            return
        if result.outcome == CallOutcome.OK and result.output is not None:
            capture.extraction = verify(result.output, text)
            capture.extraction_status = ExtractionStatus.EXTRACTED
            capture.extraction_error = ""
        else:
            capture.extraction_status = ExtractionStatus.NOT_EVALUATED
            capture.extraction_error = result.outcome
        capture.save(update_fields=["extraction", "extraction_status", "extraction_error"])


@shared_task(name="postings.sweep_stalled_captures")
def sweep_stalled_captures() -> None:
    cutoff = timezone.now() - STALLED_AFTER
    with recorded("postings.sweep_stalled_captures") as counts:
        counts["stalled"] = 0
        for user_id in User.objects.values_list("pk", flat=True):
            with tenant_context(user_id):
                counts["stalled"] += UserPosting.objects.filter(
                    extraction_status=ExtractionStatus.PENDING, updated_at__lt=cutoff
                ).update(
                    extraction_status=ExtractionStatus.NOT_EVALUATED,
                    extraction_error="stalled",
                    updated_at=timezone.now(),
                )

from fastapi import HTTPException, Request


async def require_workflow(request: Request):
    """Keep unfinished prototype mutations out of executed business records."""
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "WORKFLOW_UNAVAILABLE",
                "message": (
                    "This workflow is awaiting trusted verification, authorization, "
                    "and guarded payment processing. No work or payment was created."
                ),
            },
        )

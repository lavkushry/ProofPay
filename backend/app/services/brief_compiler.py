"""Compatibility facade for the provider-neutral compiler service."""

from backend.app.services.compiler import CompileResult, compile_revision, validate_proposal

class BriefCompilerService:
    """Expose the asynchronous compiler while keeping the historic import path."""

    compile_revision = staticmethod(compile_revision)
    validate_proposal = staticmethod(validate_proposal)

"""Explicit host composition for retained context artifacts.

An external artifact is retained context, never a C21 scientific receipt. Each
provider owns its durable bytes and an idempotent retention journal. Prepared
pins are conservative even if the application transaction never commits; this
interface deliberately provides no release or execution authority.
"""
from abc import ABC, abstractmethod

from orchestration.investigations import InvestigationService


class RetainedArtifactProvider(ABC):
    def __init__(self, *, investigations):
        if not isinstance(investigations, InvestigationService):
            raise ValueError('Explicit independent investigation service required')
        self.investigations = investigations
        self.site_id = investigations.site_id
        self.session_factory = investigations.session_factory

    @abstractmethod
    def authorize_owner(self, session, user):
        """Acquire current owner fences before the shared site/target locks."""

    @abstractmethod
    def resolve(self, session, user, reference):
        """Return an authorized RetainedArtifactBinding, None only if unknown."""

    @abstractmethod
    def prepare_context(self, session, operation, candidate, reference, user):
        """Durably pin exact bytes before the context preparation can commit."""

    @abstractmethod
    def activate_context(self, session, operation, candidate, reference, user):
        """Idempotently commit the same pin; ambiguity must retain protection."""

    @abstractmethod
    def verify_context(self, session, revision_id, reference, expected_sha256, user):
        """Verify current authorization and a committed immutable context pin."""


class SessionAttachmentResolver:
    """Use the caller's transaction, including its site advisory lock.

    Opening a second C22 transaction while C17 holds its site lock deadlocks on
    PostgreSQL. The normal callable form remains available outside transactions.
    """
    def __init__(self, evidence):
        self.evidence = evidence

    def __call__(self, user, reference):
        return self.evidence.resolve_attachment(user, reference)

    def authorize_in_session(self, session, user):
        self.evidence.authorize_attachment_owner(session, user)

    def resolve_in_session(self, session, user, reference):
        return self.evidence.resolve_attachment_in_session(session, user, reference)

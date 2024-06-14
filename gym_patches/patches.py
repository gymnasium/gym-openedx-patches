import logging
from common.djangoapps.course_modes.models import CourseMode
from django.conf import settings

logger = logging.getLogger(__name__)

def custom_is_eligible_for_certificate(cls, mode_slug, status=None):
    """
    Custom version of the method without excluding AUDIT mode.
    """
    logger.info(f"Custom is_eligible_for_certificate called with mode_slug: {mode_slug}")
    ineligible_modes = []

    if settings.FEATURES.get('DISABLE_HONOR_CERTIFICATES', False):
        from lms.djangoapps.certificates.data import CertificateStatuses
        if mode_slug == cls.HONOR and status != CertificateStatuses.downloadable:
            ineligible_modes.append(cls.HONOR)

    return mode_slug not in ineligible_modes

def apply_monkey_patch():
    logger.info("Applying monkey patch for CourseMode.is_eligible_for_certificate")
    CourseMode.is_eligible_for_certificate = classmethod(custom_is_eligible_for_certificate)

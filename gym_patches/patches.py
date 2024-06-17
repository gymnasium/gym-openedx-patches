import logging
from common.djangoapps.course_modes.models import CourseMode
from django.conf import settings
from openedx.core.djangoapps.user_authn.views.register import _track_user_registration as original_track_user_registration

logger = logging.getLogger(__name__)

def custom_track_user_registration(user, profile, params, third_party_provider, registration, is_marketable):
    """ Track the user's registration with custom market field. """
    if hasattr(settings, 'LMS_SEGMENT_KEY') and settings.LMS_SEGMENT_KEY:
        try:
            extrainfo_dict = user.extrainfo.__dict__
            del extrainfo_dict['user_id']
            del extrainfo_dict['_user_cache']
            del extrainfo_dict['_state']
            del extrainfo_dict['id']
            extrainfo = json.dumps(extrainfo_dict)
        except Exception:
            log.exception("Exception in extrainfo_dict: {}".format(e))
            extrainfo = ''

        traits = {
            'email': user.email,
            'username': user.username,
            'name': profile.name,
            'age': profile.age or -1,
            'yearOfBirth': profile.year_of_birth or datetime.datetime.now(UTC).year,
            'education': profile.level_of_education_display,
            'address': profile.mailing_address,
            'gender': profile.gender_display,
            'country': str(profile.country),
            'is_marketable': is_marketable,
            'extrainfo': extrainfo  # Add the market field to the traits
        }

        if settings.MARKETING_EMAILS_OPT_IN and params.get('marketing_emails_opt_in'):
            email_subscribe = 'subscribed' if is_marketable else 'unsubscribed'
            traits['email_subscribe'] = email_subscribe

        segment.identify(user.id, traits)
        properties = {
            'category': 'conversion',
            'email': user.email,
            'label': params.get('course_id'),
            'provider': third_party_provider.name if third_party_provider else None,
            'is_gender_selected': bool(profile.gender_display),
            'is_year_of_birth_selected': bool(profile.year_of_birth),
            'is_education_selected': bool(profile.level_of_education_display),
            'is_goal_set': bool(profile.goals),
            'total_registration_time': round(float(params.get('totalRegistrationTime', '0'))),
            'activation_key': registration.activation_key if registration else None,
            'host': params.get('host', ''),
            'utm_campaign': params.get('utm_campaign', ''),
        }

        if params.get('marketing_emails_opt_in') and settings.MARKETING_EMAILS_OPT_IN:
            properties['marketing_emails_opt_in'] = is_marketable

        segment_traits = dict(properties)
        segment_traits['user_id'] = user.id
        segment_traits['joined_date'] = user.date_joined.strftime("%Y-%m-%d")
        segment.track(
            user.id,
            "edx.bi.user.account.registered",
            properties=properties,
            traits=segment_traits,
        )

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
    # Apply monkey patch for is_eligible_for_certificate
    logger.info("Applying monkey patch for CourseMode.is_eligible_for_certificate")
    CourseMode.is_eligible_for_certificate = classmethod(custom_is_eligible_for_certificate)
    
    # Apply the patch for _track_user_registration
    from openedx.core.djangoapps.user_authn.views import register
    register._track_user_registration = custom_track_user_registration

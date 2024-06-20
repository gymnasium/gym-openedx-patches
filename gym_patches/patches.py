import logging
from django.http import HttpResponse, HttpResponseBadRequest
from django.db import transaction
from django.views.decorators.http import require_POST
from opaque_keys.edx.keys import CourseKey
from openedx.core.lib.courses import get_course_by_id
from lms.djangoapps.certificates import api as certs_api
from lms.djangoapps.courseware.views.views import is_course_passed
from lms.djangoapps.certificates.exceptions import CertificateGenerationNotAllowed
from openedx.core.djangoapps.site_configuration import helpers as configuration_helpers
from openedx.core.djangoapps.user_authn.views.register import _track_user_registration as original_track_user_registration

logger = logging.getLogger(__name__)

def custom_generate_user_cert(request, course_id):
    """
    Request that a course certificate be generated for the user.

    In addition to requesting generation, this method also checks for and returns the certificate status.
    Note that because generation is an asynchronous process, the certificate may not have been generated when
    its status is retrieved.

    Args:
        request (HttpRequest): The POST request to this view.
        course_id (unicode): The identifier for the course.
    Returns:
        HttpResponse: 200 on success, 400 if a new certificate cannot be generated.
    """
    if not request.user.is_authenticated:
        logger.info("Anon user trying to generate certificate for %s", course_id)
        return HttpResponseBadRequest(
            _('You must be signed in to {platform_name} to create a certificate.').format(
                platform_name=configuration_helpers.get_value('PLATFORM_NAME', settings.PLATFORM_NAME)
            )
        )

    student = request.user
    course_key = CourseKey.from_string(course_id)
    course = get_course(course_id)

    if not course:
        return HttpResponseBadRequest(_("Course is not valid"))

    logger.info(f'Attempt will be made to generate a course certificate for {student.id} : {course_key}.')

    try:
        certs_api.generate_certificate_task(student, course_key, 'self')
    except CertificateGenerationNotAllowed as e:
        logger.exception(
            "Certificate generation not allowed for user %s in course %s",
            str(student),
            course_key,
        )
        return HttpResponseBadRequest(str(e))

    if not is_course_passed(student, course):
        logger.info("User %s has not passed the course: %s", student.username, course_id)
        return HttpResponseBadRequest(_("Your certificate will be available when you pass the course."))

    certificate_status = certs_api.certificate_downloadable_status(student, course.id)

    logger.info(
        "User %s has requested for certificate in %s, current status: is_downloadable: %s, is_generating: %s",
        student.username,
        course_id,
        certificate_status["is_downloadable"],
        certificate_status["is_generating"],
    )

    # Track certificate generation request with Segment
    if hasattr(settings, 'LMS_SEGMENT_KEY') and settings.LMS_SEGMENT_KEY:
        traits = {
            'email': student.email,
            'username': student.username,
            'course_id': course_id,
            'is_downloadable': certificate_status["is_downloadable"],
            'is_generating': certificate_status["is_generating"]
        }
        segment.track(student.id, "Certificate Generation Requested", traits)

    if certificate_status["is_downloadable"]:
        return HttpResponseBadRequest(_("Certificate has already been created."))
    elif certificate_status["is_generating"]:
        return HttpResponseBadRequest(_("Certificate is being created."))

    return HttpResponse()

# Existing functions

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
        except Exception as e:
            logger.exception("Exception in extrainfo_dict: {}".format(e))
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
        logger.info("##### traits ####### {}".format(traits))

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
        logger.info("###### segment traits: {} and properties: {} ###########".format(segment_traits, properties))
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
    
    # Apply the patch for generate_user_cert
    from lms.djangoapps.courseware.views import views
    views.generate_user_cert = custom_generate_user_cert

import logging
import json
from smtplib import SMTPException

from formencode.validators import Invalid
from sqlalchemy.exc import SQLAlchemyError

from old.lib.constants import (
    JSONDecodeErrorResponse
)
from old.lib.schemata import (
    LoginSchema,
    PasswordResetSchema
)
import old.lib.helpers as h
from old.models import (
    User,
    Page
)


LOGGER = logging.getLogger(__name__)


NOT_AUTHENTICATED_MSG = 'The username and password provided are not valid.'


def login(request):
    LOGGER.info('Attempting to login')
    schema = LoginSchema()
    try:
        values = json.loads(request.body.decode(request.charset))
    except ValueError:
        request.response.status_int = 400
        LOGGER.warning(JSONDecodeErrorResponse)
        return JSONDecodeErrorResponse
    try:
        result = schema.to_python(values)
    except Invalid as error:
        request.response.status_int = 400
        errors = error.unpack_errors()
        LOGGER.warning(errors)
        return {'errors': errors}
    username = result.get('username')
    password = result.get('password')
    LOGGER.info('Attempting to login with username "%s".', username)
    if username is None or password is None:
        LOGGER.warning(NOT_AUTHENTICATED_MSG)
        return not_authenticated(request)
    user = request.dbsession.query(User)\
        .filter(User.username == username).first()
    if user is None:
        LOGGER.warning(NOT_AUTHENTICATED_MSG)
        return not_authenticated(request)
    # TODO: when using SQLite, the salt in the database is already bytes, but
    # when using MySQL it's str. Why?
    salt = user.salt
    if isinstance(salt, str):
        salt = salt.encode('utf8')
    password = h.encrypt_password(password, salt)
    user = request.dbsession.query(User)\
        .filter(User.username == username)\
        .filter(User.password == password).first()
    if user is None:
        LOGGER.warning(NOT_AUTHENTICATED_MSG)
        return not_authenticated(request)
    # request.response.headerlist.extend(remember(request, user.id))
    request.session['user'] = user.get_dict()
    # request.session.save()
    home_page = request.dbsession.query(Page).filter(
        Page.name == 'home').first()
    LOGGER.info('Successful login with username "%s".', username)
    return {
        'authenticated': True,
        'user': user,
        'homepage': home_page
    }


def not_authenticated(request):
    request.response.status_int = 401
    return {'error': NOT_AUTHENTICATED_MSG}


def logout(request):
    request.session.delete()
    LOGGER.info('Successful logout.')
    return {'authenticated': False}


def email_reset_password(request):
    """Reset the user's password and email them a new one.

    - URL: ``POST /login/email_reset_password``
    - request body: a JSON object with a ``"username"`` attribute.

    :returns: a dictionary with ``'valid_username'`` and ``'password_reset'``
              keys whose values are booleans.
    """
    LOGGER.info('Request for a password reset.')
    schema = PasswordResetSchema()
    try:
        values = json.loads(request.body.decode(request.charset))
    except ValueError:
        request.response.status_int = 400
        LOGGER.warning(JSONDecodeErrorResponse)
        return JSONDecodeErrorResponse
    try:
        result = schema.to_python(values)
    except Invalid as error:
        request.response.status_int = 400
        errors = error.unpack_errors()
        LOGGER.warning(errors)
        return {'errors': errors}
    username = result.get('username')
    user = request.dbsession.query(User).filter(
        User.username == username).first()
    if username is not None and user is not None:
        new_password = h.generate_password()
        app_url = request.route_url('info', old_name=request.registry.settings['old_name'])
        salt = user.salt
        if isinstance(salt, str):
            salt = salt.encode('utf8')
        user.password = str(h.encrypt_password(new_password, salt))
        try:
            request.dbsession.add(user)
        except SQLAlchemyError:
            request.dbsession.rollback()
            request.response.status_int = 400
            msg = 'Failed to set the new password in the database.'
            LOGGER.warning(msg)
            return {'error': msg}
        else:
            try:
                h.send_password_reset_email_to(
                    user, new_password, request.registry.settings, app_url)
            except (h.OLDSendEmailError, KeyError, SMTPException,
                    ConnectionRefusedError) as exc:
                request.dbsession.rollback()
                request.response.status_int = 400
                LOGGER.warning(exc)
                return {'error': 'The server is unable to send email.'}
            else:
                if request.registry.settings.get('testing', '0') == '1':
                    return {'valid_username': True, 'password_reset': True,
                            'new_password': new_password}
                return {'valid_username': True, 'password_reset': True}
    else:
        request.response.status_int = 400
        LOGGER.warning('The username provided is not valid.')
        return {'error': 'The username provided is not valid.'}

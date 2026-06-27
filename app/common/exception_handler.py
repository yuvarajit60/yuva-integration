import functools
import json
import logging
import os
from datetime import datetime
from distutils import util

import azure.functions as func
from marshmallow.exceptions import \
    ValidationError as MarshmallowValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.common.helpers.common_data_access import log_auto_pairing_failure_event

from .constants import ContentType, GeneralConstant, ResponseCode
from .email import Email
from .exceptions import ScalarException, AutoPairingException
from .models import Response
from .helpers.common_services import generate_common_multi_error_report



def global_exception_handler(function):
    @functools.wraps(function)
    def global_exception_handler_wrapper(*args, **kwargs):
        try:
            app_name = function.__module__
            logger = logging.getLogger(app_name)
            return function(*args, **kwargs)
        except ScalarException as se:
            message = se.message
            display_message = message if se.display_reqd else None
            error_list = se.error_list
            logger.error(se, exc_info=True)
            response_code = ResponseCode.INTERNAL_ERROR if se.response_code is None else se.response_code
            return __send_response(message=message, response_code=response_code, error_list=error_list, 
                                    display_message=display_message, kwargs=kwargs)
        except AutoPairingException as ape:
            logger.error(ape, exc_info=True)
            message = ape.message
            db = ape.db
            event_log = ape.event_log
            log_auto_pairing_failure_event(db=db, message=message, event_log=event_log)
            response = Response(status=False, message=message)
            return func.HttpResponse(
                json.dumps(response.getResponse()),
                status_code=ResponseCode.INTERNAL_ERROR,
                mimetype=ContentType.APPLICATION_JSON)
        except SQLAlchemyError as sae:
            message = GeneralConstant.DB_EXCP_MESSAGE
            logger.error(sae, exc_info=True)
            return __send_response(message=message, kwargs=kwargs)
        except MarshmallowValidationError as mve:
            message = str(mve)
            logger.error(message, exc_info=True)
            return __send_response(message=message, response_code=ResponseCode.BAD_REQUEST, kwargs=kwargs)
        except Exception as e:
            message = str(e)
            logger.error(message, exc_info=True)
            return __send_response(message=message, kwargs=kwargs)


    def __send_response(message: str, kwargs, response_code=ResponseCode.INTERNAL_ERROR, error_list=list(), subject=None, display_message=None):
        error_mail_allowed = os.environ.get("SC_API_ERROR_EMAIL_ALLOWED", "False")
        if bool(util.strtobool(error_mail_allowed)) is True:
            __send_email(message=message, response_code=response_code, subject=subject, error_list=error_list, kwargs=kwargs)
        message = message[:500]
        response = Response(status=False, message=message, display_message=display_message)
        return func.HttpResponse(
            json.dumps(response.getResponse()),
            status_code=response_code,
            mimetype=ContentType.APPLICATION_JSON)


    def __send_email(message: str, response_code: str, subject, error_list, kwargs):
        req = kwargs["req"]
        method = req.method
        url = req.url
        json_body = None
        if len(req.get_body()) > 0:
            try:
                json_body = req.get_json()
            except ValueError as e:
                try:
                    json_body = req.get_body().decode('utf-8')
                except Exception as e:
                    json_body = str(req.get_body())

        email = Email()
        environment = None
        receivers = os.environ["SC_API_ERROR_EMAIL_RECIPIENTS"].split(",")
        subject = "Scalar API Error" if subject is None else subject
        if os.environ['SCALAR_ENV'] == "DEV":
            subject += ' - DEV'
            environment = 'DEV'
        else:
            environment = 'PROD'
        template_name = "common_error_email.html"
        params = {
            "api_exectution_time": datetime.now(),
            "api_error_message": message,
            "api_url": url,
            "api_http_method":method,
            "api_request_payload":json_body,
            'environment': environment
            }
        attachment, file_name = None, None
        if len(error_list)>0:
            error_report = generate_common_multi_error_report(error_list)
            error_report.seek(0)
            attachment = error_report.read()
            file_name = "error_report.xlsx"
        email.send_email(receivers=receivers, subject=subject, template_name=template_name,
                        params=params, attachment=attachment, filename=file_name)

    return global_exception_handler_wrapper




import base64
import os
from string import Template
import logging
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import (
    Mail, Attachment, FileContent, FileName, FileType, Disposition
)


class Email:

    logger = logging.getLogger("Email")

    def __init__(self):
        self.api_key  = os.environ["SENDGRID_API_KEY"]
        self.fc_email = os.environ["FC_EMAIL_ID"]

    def send_email(self, receivers: list, subject: str, template_name: str,
                   params: dict = {}, attachment=None, filename=None):
        template_content = self.__get_template_content(template_name)
        html_body = template_content.substitute(params)

        message = Mail(
            from_email=self.fc_email,
            to_emails=receivers,
            subject=subject,
            html_content=html_body,
        )

        if attachment is not None:
            encoded = base64.b64encode(attachment).decode()
            att = Attachment(
                FileContent(encoded),
                FileName(filename),
                FileType("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
                Disposition("attachment"),
            )
            message.attachment = att

        sg = SendGridAPIClient(self.api_key)
        response = sg.send(message)

        if response.status_code in (200, 202):
            self.logger.info("mail sent successfully")
        else:
            self.logger.error(
                f"mail sending failed — status: {response.status_code}, body: {response.body}"
            )
            raise Exception(
                f"SendGrid sendMail failed ({response.status_code}): {response.body}"
            )

    def __get_template_content(self, template_name):
        template_path = "app/resources/email_templates/" + template_name
        with open(template_path, mode="r") as f:
            return Template(f.read())

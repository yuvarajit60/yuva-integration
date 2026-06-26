import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from string import Template
import logging
from email.mime.application import MIMEApplication
from email import encoders


class Email:

    logger = logging.getLogger("Email")

    def __init__(self):
        self.smtp_server_name = os.environ['SMTP_SERVER']
        self.smtp_server_port = os.environ['SMTP_PORT']
        self.fc_pwd = os.environ['FC_EMAIL_PWD']
        self.fc_email = os.environ['FC_EMAIL_ID']


    def send_email(self, receivers: list, subject: str, template_name: str, params={}, attachment=None,
                   filename=None):
        with smtplib.SMTP(host=self.smtp_server_name, port=self.smtp_server_port) as server:
            server.starttls()
            server.login(self.fc_email, self.fc_pwd)
            msg = self.__create_message(receivers=receivers, subject=subject, template_name=template_name, 
                                        params=params, attachment=attachment, filename=filename)
            server.send_message(msg)
            # server.quit()
            self.logger.info(f"mail was sent successfully")
    

    def __create_message(self, receivers: list, subject, template_name, params: dict, attachment, filename):
        template_content = self.__get_template_content(template_name)
        message = template_content.substitute(params)
        message_body = MIMEText(message, 'html')

        msg = MIMEMultipart()
        msg['Subject'] = subject
        msg['From'] = self.fc_email
        msg['To'] = ",".join(receivers)
        msg.attach(message_body)

        if attachment is not None:
            part = MIMEApplication(attachment)
            encoders.encode_base64(part)
            filename = filename if filename is not None else "attachment"
            part.add_header(
                "Content-Disposition",
                f"attachment; filename= {filename}")
            msg.attach(part)

        return msg


    def __get_template_content(self, template_name):
        template_path = "app/resources/email_templates/" + template_name
        with open(template_path, mode='r') as template_file:
            template_file_content = template_file.read()
        return Template(template_file_content)

import base64
import os
from string import Template
import logging
from msal import ConfidentialClientApplication
import requests


class Email:

    logger = logging.getLogger("Email")

    def __init__(self):
        tenant_id = os.environ['TENANT_ID']
        client_id = os.environ['CLIENT_ID']
        client_secret = os.environ['CLIENT_SECRET']
        authority = f"https://login.microsoftonline.com/{tenant_id}"
        app = ConfidentialClientApplication(client_id=client_id, authority=authority, client_credential=client_secret)
        token = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
        
        self.access_token = token["access_token"]
        self.fc_email = os.environ['FC_EMAIL_ID']


    def send_email(self, receivers: list, subject: str, template_name: str, params={}, attachment=None,
                   filename=None):
        headers = {
            "Authorization":f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        msg = self.__create_message(receivers=receivers, subject=subject, template_name=template_name, 
                                        params=params, attachment=attachment, filename=filename)
        url = f"https://graph.microsoft.com/v1.0/users/{self.fc_email}/sendMail"
        response = requests.post(url=url,headers=headers,json=msg)
        if response.status_code in (200, 202):
            self.logger.info(f"mail was sent successfully")
        else:
            self.logger.info(f"mail sending failed")
    
    

    def __create_message(self, receivers: list, subject, template_name, params: dict, attachment, filename):
        template_content = self.__get_template_content(template_name)
        message = template_content.substitute(params)
    
        msg = {
            "message":{
                "subject":subject,
                "body": {"contentType": "HTML","content":message},
                "toRecipients": [{"emailAddress":{"address":email}} for email in receivers ]
            },
            "saveToSentItems":"True"
        }

        if attachment is not None:
            part = base64.b64encode(attachment).decode("utf-8")
            msg["message"]["attachments"] = [
                    {
                        "@odata.type":"#microsoft.graph.fileAttachment",
                        "name":filename,
                        "contentType": "application/vnd.openxmlformats-officedocument.spreadsheet.sheet",
                        "contentBytes": part
                    }
                ]

        return msg


    def __get_template_content(self, template_name):
        template_path = "app/resources/email_templates/" + template_name
        with open(template_path, mode='r') as template_file:
            template_file_content = template_file.read()
        return Template(template_file_content)

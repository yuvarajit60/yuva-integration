from datetime import datetime
import azure.functions as func
import os,json,base64

from app.common.email import Email

migration_activities_bp = func.Blueprint()

@migration_activities_bp.activity_trigger(input_name="input")
def test_activity(input: dict):
    env = os.environ['SCALAR_ENV']
    email=Email()
    receivers=["Bhowmik.Arijit@tip-group.com"]
    subject=f"Scalar - Data Sync Error: User sync report - " + env
    
    template_name='error_user_email.html'
    error_params={"environment": env, 
    "execution_time": datetime.now(),
    "error_message": "test msg",
    }
    email.send_email(receivers=receivers, subject=subject, template_name=template_name,params=error_params)
    return {"env":env}

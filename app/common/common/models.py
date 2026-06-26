import json

class Response:
    def __init__(self, status, message, display_message=None):
        super().__init__()
        self.response = dict()
        self.response["status"] = status
        self.response["message"] = message
        self.response["displayMessage"] = display_message

    def getResponse(self):
        return self.response
    
    def getJsonResponse(self):
        return json.dumps(self.response)

class Role:
    def __init__(self, roleId, roleName):
        super().__init__()
        self.roleId = roleId
        self.roleName = roleName


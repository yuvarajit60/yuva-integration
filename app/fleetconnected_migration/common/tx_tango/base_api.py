import os
from zeep import Client, xsd
from datetime import datetime
from zeep.helpers import serialize_object
from zeep.transports import Transport

class TxTangoApi:
    wsdl = os.environ["WSDL"]
    transport = Transport()
    transport.session.verify = bool(os.environ["SSL_VERIFICATION"])
    client = Client(wsdl=wsdl, transport=transport)
    factory = client.type_factory('ns0')
    def __init__(self, dispatcher, integrator, system_nr, password, version):
        super().__init__()
        self.login = self.factory.Login(Dispatcher=dispatcher, Password=password, SystemNr=system_nr, Integrator=integrator, Language='EN', DateTime=datetime.now(), Version=version) 

    def skip_value(self):
        return xsd.SkipValue

    def _get_serialized_response(self, response):
        return serialize_object(response, target_cls=dict)

from app.fleetconnected_migration.common.tx_tango.base_api import TxTangoApi


class UserApi(TxTangoApi):

    def __init__(self, dispatcher, integrator, system_nr, password, version):
        super().__init__(dispatcher=dispatcher, integrator=integrator, system_nr=system_nr, password=password, version=version)

    def get_users(self):
        user_selection = self.factory.UserSelection(IncludeInactive='false')

        response = self._get_serialized_response(self.client.service.Get_Users(Login=self.login, UserSelection=user_selection))
        return response

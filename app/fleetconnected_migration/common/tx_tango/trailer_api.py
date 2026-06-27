from datetime import datetime

from app.common.constants import TrailerIdentifier
from app.fleetconnected_migration.common.tx_tango.base_api import TxTangoApi


class TrailerApi(TxTangoApi):
    def __init__(self, dispatcher, integrator, system_nr, password, version):
        super().__init__(dispatcher=dispatcher, integrator=integrator, system_nr=system_nr, password=password, version=version)
    

    def get_subcontacted_vehicles(self, transics_id: int, company_id, trailer_identifier_type=None, start_dt=None):
        trailer_strategy = None
        if transics_id is not None:
            if trailer_identifier_type is not None:
                identifier_vehicle_type = self.factory.enumIdentifierVehicleType(value=trailer_identifier_type)
            else:
                identifier_vehicle_type = self.factory.enumIdentifierVehicleType(value=TrailerIdentifier.TRANSICS_ID)
            trailer_strategy = self.factory.TrailerStrategy(IdentifierVehicleType=identifier_vehicle_type, Id=transics_id)
        v_company_id = None
        if company_id is not None:
            v_company_id = self.factory.CompanyId(Id=company_id)
        if start_dt is not None:
            date_strategy_selection = self.factory.Period(From=start_dt, Until=datetime.now())
        else:
            date_strategy_selection = self.factory.ActualSituation()
        subcontracted_vehicle_selection = self.factory.SubcontractedVehicleSelection(
                                                            IdentifierVehicleStrategy=trailer_strategy,
                                                            CompanyStrategySelection=v_company_id,
                                                            DateStrategySelection=date_strategy_selection,
                                                            IncludeInactive=False)

        result = self.client.service.Get_SubcontractedVehicles(Login=self.login,
                                                                SubcontractedVehicleSelection=subcontracted_vehicle_selection)
        return self._get_serialized_response(result)
    
    def get_transics_array_of_vehicle_identifiers(self, trailer_identifiers: list, trailer_identifier_type: str):
        transics_vehicle_identifiers = list()
        transics_identifier_vehicle_type = self.factory.enumIdentifierVehicleType(value=trailer_identifier_type)
        
        for trailer_identifer in trailer_identifiers:
            transisc_vehicle_identifier = self.factory.IdentifierVehicle(IdentifierVehicleType=transics_identifier_vehicle_type, Id=trailer_identifer)
            transics_vehicle_identifiers.append(transisc_vehicle_identifier)

        return self.factory.ArrayOfIdentifierVehicle(IdentifierVehicle=transics_vehicle_identifiers)

    def get_trailers(self, trailer_identifiers: list, trailer_identifier_type: str) -> dict:
        transics_array_of_vehicle_identifiers = self.get_transics_array_of_vehicle_identifiers(trailer_identifiers=trailer_identifiers, trailer_identifier_type=trailer_identifier_type)
        vehicle_selection = self.factory.VehicleSelection_With_NextStop_Info_WithoutDate(IncludeNextStopInfo='false', 
                                                                                         ShowInactive='false', 
                                                                                         Identifiers=transics_array_of_vehicle_identifiers, 
                                                                                         IncludePicture='false', 
                                                                                         IncludeEngineInfo='false', 
                                                                                         IncludeTechnicalInfo='false', 
                                                                                         IncludeLoadInfo='false', 
                                                                                         IncludeComfortInfo='false', 
                                                                                         IncludePosition='false', 
                                                                                         IncludeActivity='false', 
                                                                                         IncludeDrivers='false', 
                                                                                         IncludeObcInfo='false', 
                                                                                         IncludeETAInfo='false', 
                                                                                         IncludeTemperatureInfo='false', 
                                                                                         IncludeInfoFields='false', 
                                                                                         IncludeUpdateDates='false',
                                                                                         IncludeCostInfo='false', 
                                                                                         IncludeRented='false')

        response = self._get_serialized_response(self.client.service.Get_Trailers_V6(Login=self.login, VehicleSelection=vehicle_selection))
        return response
    


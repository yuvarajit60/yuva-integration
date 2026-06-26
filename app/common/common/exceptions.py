class PreProcessingSheetException(Exception):
    def __init__(self, *args):
        if args:
            self.message = args[0]
        else:
            self.message = None
    

    def __str__(self):
        if self.message:
            return 'PreProcessingSheetException, {} '.format(self.message)
        else:
            return 'PreProcessingSheerException raised'


class ScalarException(Exception):
    def __init__(self, message, error_list=list(), response_code=None, display_reqd=False):
        self.error_list = error_list
        self.message = message
        self.response_code = response_code
        self.display_reqd = display_reqd
        super().__init__(message)

    def __str__(self):
        return self.message


class AutoPairingException(Exception):
    def __init__(self, message, db, event_log):
        self.message = message
        self.db = db
        self.event_log = event_log
        super().__init__(message)

    def __str__(self):
        return self.message
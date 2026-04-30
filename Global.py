from astropy.time import Time

class GlobalVars():
    def __init__(self):
        teste = 1
    def getBaseTime(self):
        return Time.now()
# -*- coding: utf-8 -*-
# TimeScaleViewer version 1.5 (2026)
# Autor: Fernando Rodrigues (Inmetro)

from astropy.time import Time

class GlobalVars():
    def __init__(self):
        teste = 1
    def getBaseTime(self):
        return Time.now()
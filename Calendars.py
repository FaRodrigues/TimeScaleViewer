import time

import numpy as np
from collections import deque
from astropy.time import Time


class RapidYear(Time):
    def __init__(self, refyear):
        self.rapidmjdweeklist = None
        self.monthmjddeque = None
        self.refyear = refyear
        self.STARTMJD = int(Time('{}-01-01'.format(refyear)).to_value('mjd'))
        self.STOPMJD = int(Time('{}-12-31'.format(refyear)).to_value('mjd'))
        finalofstartmjd = self.STARTMJD % 10

        if finalofstartmjd in [4, 9]:
            retroAdjust = 2
        else:
            retroAdjust = 4

        circtStartMjd = self.STARTMJD - retroAdjust;
        circtFinalMjd = self.STOPMJD + 4;

        self.mjdlist = range(circtStartMjd, circtFinalMjd, 1)
        dmjdlist = deque()
        dmjdlist.extend(self.mjdlist)
        mjddeque = deque()

        monthdmjdlist = dmjdlist
        monthmjddeque = deque()

        count = 0

        for x in range(len(self.mjdlist)):
            slice = list(dmjdlist)
            idref = 3
            idmax = (2*idref)-1
            if slice[idref] % 10 in [4, 9]:
                mjddeque.append(slice[0:idmax])
                count = count + 1
            dmjdlist.rotate(-1)

        self.setRapidWeekList(np.array(mjddeque))

        countpivot = 0

        tempdeque = deque()

        for x in range(len(self.mjdlist)):
            slice = list(monthdmjdlist)
            if slice[0] % 10 in [4, 9]:
                tempdeque.append(slice[0])
                # # print(tempdeque)
                # # time.sleep(1)
                # if countpivot % 7 == 0:
                #     monthmjddeque.append(list(tempdeque))
                #     tempdeque.clear()
                #     # print(list(monthmjddeque))

            monthdmjdlist.rotate(-1)

        self.setCirctMonthList(tempdeque)

    def setCirctMonthList(self, monthmjddeque):
        self.monthmjddeque = monthmjddeque

    def getCirctMonthList(self):
        return self.monthmjddeque

    def setRapidWeekList(self, rmjdwl):
        self.rapidmjdweeklist = rmjdwl

    def getRapidWeekList(self):
        rmwl = self.rapidmjdweeklist
        minv = min([sublist[0] for sublist in rmwl])
        maxv = max([sublist[-1] for sublist in rmwl])
        return [[minv, maxv], rmwl]

    def getRapidMjdWeekNumber(self, mjd):
        contextWeekList = self.getRapidWeekList();
        rapidmjdweeknumber = 0
        rapidmjdweekout = []
        descript = "calendário RAPID {}".format(self.refyear)
        # Registra o mjd inicial e mjd final do calendário do processo RAPID do BIPM
        minmjd = contextWeekList[0][0]
        maxmjd = contextWeekList[0][1]
        # Verifica se o mjd parâmetro está no calendário do '''ano RAPID'''
        if minmjd <= mjd <= maxmjd:
            indexweeklist = 0
            for rapidmjdweek in contextWeekList[1]:
                indexweeklist = indexweeklist + 1
                if mjd in rapidmjdweek:
                    rapidmjdweeknumber = indexweeklist
                    rapidmjdweekout = rapidmjdweek
        else:
            print("MJD não pertence ao {}".format(descript), '|',
                  "O {} começa no MJD {} e termina no MJD {}".format(descript, minmjd, maxmjd))
        return [rapidmjdweeknumber, rapidmjdweekout]

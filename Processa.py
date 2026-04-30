# -*- coding: utf-8 -*-
# TimeScaleViewer version 1.5 (2026)
# Autor: Fernando Rodrigues (Inmetro)

import os
import numpy as np
import pandas as pd
from collections import deque
# from datetime import datetime
from xml.etree import ElementTree as ET


def setUTV(utv):
    Processacggtts.uniqueTimeValues = utv


def getUTV():
    return Processacggtts.uniqueTimeValues


def getNameOfFileFromMJD(prefixo, mjd):
    return '''{0:s}{1:.3f}'''.format(prefixo, mjd / 1000)


xmlprocessingtoken = False

trypath = ".\CGGTTS"
isExist = os.path.exists(trypath)
if not isExist: os.makedirs(trypath)
baserootcggtts = trypath


class Processacggtts:
    uniqueTimeValues = None

    def __init__(self, mjdinterval, prefixodinamico):
        self.unitforREFSYS = None
        # print("prefixodinamico = {}".format(prefixodinamico))

        self.deqofmean = deque()
        self.uniqueTimeValues = None

        # Define os nomes para os campos de dados
        self.datanames = ["SAT", "CL", "MJD", "STTIME", "TRKL", "ELV", "AZTH", "REFSV", "SRSV", "REFSYS", "SRSYS",
                          "DSG", "IOE",
                          "MDTR", "SMDT", "MDIO", "SMDI", "MSIO", "SMSI", "ISG", "FR", "HC", "FRC", "CK"]

        # Define localmente o nome do diretório que será processado
        self.localdynpath = os.path.join(baserootcggtts, prefixodinamico)
        if not (os.path.exists(self.localdynpath)):
            os.makedirs(self.localdynpath)

        def setUNITforREFSYS(unitforns):
            self.unitforREFSYS = unitforns

        def getUNITforREFSYS():
            return self.unitforREFSYS

        def getMeanOfColumnSlice(data, nameOfColumn, startSlice, ni):
            nameOfColumn = nameOfColumn
            numOfItems = ni
            columnSlice = data[nameOfColumn][startSlice:(startSlice + numOfItems)]
            # Convert the slice from text to float number
            columnSliceArray = np.array(columnSlice, dtype=float)
            sliceMedian = np.mean(columnSliceArray)
            return sliceMedian

        def getSTTIMEColumnSlice(data, nameOfColumn, startSlice, ni):
            nameOfColumn = nameOfColumn
            numOfItems = ni
            columnSlice = data[nameOfColumn][startSlice:(startSlice + numOfItems)]
            # Convert the sample slice from text to float number
            columnSliceArray = np.array(columnSlice, dtype=float)
            # Calculates the median of the sample slice
            sliceMedian = np.median(columnSliceArray)
            # print(columnSliceArray);
            # Enumerate whose values from the sample slice are equal to the median
            indices = [i for i, x in enumerate(columnSliceArray) if x == sliceMedian]
            # print(indices)
            # Return the filtered slice
            return [columnSliceArray[indices], indices[-1]]

        def getMeanCalculus(slicedc):
            slicedcolumn = np.array(slicedc, dtype=float) * getUNITforREFSYS()
            # print(slicedcolumn)
            tam = len(slicedcolumn)
            soma = sum(slicedcolumn)
            minval = min(slicedcolumn)
            maxval = max(slicedcolumn)
            if tam > 2:
                deno = tam - 2
            else:
                deno = tam
            result = [tam, ((soma - minval) - maxval) / deno]
            return result

        for mjd in mjdinterval:

            # Define localmente o nome do arquivo que será processado
            self.filename = getNameOfFileFromMJD(prefixodinamico, mjd)

            # Constrói o caminho do arquivo CGGTTS
            filepathname = os.path.join(self.localdynpath, self.filename)
            # print("filepathname: {}".format(filepathname))

            if os.path.exists(filepathname):
                self.tokenexist = True
                try:

                    self.CGGTTS_header = pd.read_csv(filepathname, sep='\\s+\\,', header=None, engine="python",
                                                     skiprows=0, nrows=17)

                    # Carrega o arquivo CGGTTS pulando 16 linhas
                    self.CGGTTSUNITS = pd.read_csv(filepathname, sep="\\s+|;|:", header=None, names=self.datanames,
                                                   engine="python", skiprows=17)

                    # print(self.CGGTTSUNITS.to_string())
                    strUNITS = str(self.CGGTTSUNITS["REFSYS"][1]).split('ns')

                    setUNITforREFSYS(float(strUNITS[0]))

                    # Carrega o arquivo CGGTTS pulando 17 linhas
                    self.CGGTTS_data = pd.read_csv(filepathname, sep="\\s+|;|:", header=None, names=self.datanames,
                                                   engine="python", skiprows=18);

                    # Calcula os valores únicos (contínuos) de tempo e guarda o valor em self.uniqueTimeValues
                    self.uniqueTimeValues = sorted(np.array(list(set(self.CGGTTS_data['STTIME'][1:-1]))))

                    setUTV(self.uniqueTimeValues)

                    # Faz o split da variável filename com base no separador "."
                    contextnames = self.filename.split(".")
                    # Insere o elemento raiz do XML
                    root = ET.Element(contextnames[0])
                    # Insere o nó principal abaixo da raiz do XML
                    noderoot = ET.SubElement(root, contextnames[1])

                    for uv in self.uniqueTimeValues:
                        STColumn = self.CGGTTS_data.loc[self.CGGTTS_data['STTIME'] == uv]
                        REFColumn = STColumn['REFSYS']
                        valor = getMeanCalculus(REFColumn)
                        # Realiza o incremento de dados no deqofmean
                        self.deqofmean.append(valor)
                        if xmlprocessingtoken:
                            sroot_root = ET.Element("Processamento", MEAN=str(valor[1]), NS=str(valor[0]))
                            noderoot.append(sroot_root)

                    if xmlprocessingtoken:
                        # Cria a árvore do XML
                        tree = ET.ElementTree(root)
                        # Define o nome do arquivo XML
                        xmlpathname = os.path.join("XMLRESULTS", contextnames[1])
                        # Formata o nome do arquivo XML
                        tree.write(xmlpathname + ".xml")

                except:
                    print("Erro ao processar o MJD = {}".format(mjd))
            else:
                self.tokenexist = False

    def getResulList(self):
        # resultlist = [np.array(self.deqofmean), getTimeInterval(self.uniqueTimeValues)];
        resultlist = np.array(self.deqofmean)
        return resultlist

    class Processatwocggtts:
        def __init__(self, dynrootcggtts, mjd, prefixodinamico):
            # Define os nomes para os campos de dados
            self.unitforREFSYS = None
            self.datanames = ["SAT", "CL", "MJD", "STTIME", "TRKL", "ELV", "AZTH", "REFSV", "SRSV", "REFSYS", "SRSYS",
                              "DSG", "IOE", "MDTR", "SMDT", "MDIO", "SMDI", "MSIO", "SMSI", "ISG", "FR", "HC", "FRC",
                              "CK"]

            # Define localmente o nome do diretório que será processado
            self.localdynpath = dynrootcggtts
            # Define localmente o nome do arquivo que será processado
            self.filename = getNameOfFileFromMJD(prefixodinamico, mjd)

            if not (os.path.exists(self.localdynpath)):
                os.makedirs(self.localdynpath)

            # Constrói o caminho do arquivo CGGTTS
            filepathname = os.path.join(self.localdynpath, self.filename)
            # print("filepathname: {}".format(filepathname))

            if os.path.exists(filepathname):
                self.tokenexist = True
                try:
                    self.CGGTTS_header = pd.read_csv(filepathname, sep='\\s+\\,', header=None, engine="python",
                                                     skiprows=0, nrows=17)

                    # Carrega o arquivo CGGTTS pulando 16 linhas
                    self.CGGTTSUNITS = pd.read_csv(filepathname, sep="\\s+|;|:", header=None, names=self.datanames,
                                                   engine="python", skiprows=17)

                    self.deqofmean = deque()

                    # print(self.CGGTTSUNITS.to_string())
                    strUNITS = str(self.CGGTTSUNITS["REFSYS"][1]).split('ns')

                    def setUNITforREFSYS(unitforns):
                        self.unitforREFSYS = unitforns

                    def getUNITforREFSYS():
                        return self.unitforREFSYS

                    setUNITforREFSYS(float(strUNITS[0]))

                    # Carrega o arquivo CGGTTS pulando 17 linhas
                    self.CGGTTS_data = pd.read_csv(filepathname, sep="\\s+|;|:", header=None, names=self.datanames,
                                                   engine="python", skiprows=18)
                    # Calcula os valores únicos (contínuos) de tempo e guarda o valor em self.uniqueTimeValues
                    self.uniqueTimeValues = sorted(np.array(list(set(self.CGGTTS_data['STTIME'][1:-1]))))

                    setUTV(self.uniqueTimeValues)

                    def getMeanOfColumnSlice(data, nameOfColumn, startSlice, ni):
                        nameOfColumn = nameOfColumn
                        numOfItems = ni
                        columnSlice = data[nameOfColumn][startSlice:(startSlice + numOfItems)]
                        # Convert the slice from text to float number
                        columnSliceArray = np.array(columnSlice, dtype=float)
                        sliceMedian = np.mean(columnSliceArray)
                        return sliceMedian

                    def getSTTIMEColumnSlice(data, nameOfColumn, startSlice, ni):
                        nameOfColumn = nameOfColumn
                        numOfItems = ni
                        columnSlice = data[nameOfColumn][startSlice:(startSlice + numOfItems)]
                        # Convert the sample slice from text to float number
                        columnSliceArray = np.array(columnSlice, dtype=float)
                        # Calculates the median of the sample slice
                        sliceMedian = np.median(columnSliceArray)
                        # print(columnSliceArray);
                        # Enumerate whose values from the sample slice are equal to the median
                        indices = [i for i, x in enumerate(columnSliceArray) if x == sliceMedian]
                        # print(indices)
                        # Return the filtered slice
                        return [columnSliceArray[indices], indices[-1]]

                    def getMeanCalculus(slicedc):
                        slicedcolumn = np.array(slicedc, dtype=float) * getUNITforREFSYS()
                        # print(slicedcolumn)
                        tam = len(slicedcolumn)
                        soma = sum(slicedcolumn)
                        minval = min(slicedcolumn)
                        maxval = max(slicedcolumn)
                        result = [tam, ((soma - minval) - maxval) / (tam - 2)]
                        return result

                    # Faz o split da variável filename com base no separador "."
                    contextnames = self.filename.split(".")
                    # Insere o elemento raiz do XML
                    root = ET.Element(contextnames[0])
                    # Insere o nó principal abaixo da raiz do XML
                    noderoot = ET.SubElement(root, contextnames[1])

                    for uv in self.uniqueTimeValues:
                        STColumn = self.CGGTTS_data.loc[self.CGGTTS_data['STTIME'] == uv]
                        REFColumn = STColumn['REFSYS']
                        valor = getMeanCalculus(REFColumn)
                        self.deqofmean.append(valor)
                        sroot_root = ET.Element("Processamento", MEAN=str(valor[1]), NS=str(valor[0]))
                        noderoot.append(sroot_root)
                        # print(valor)

                    # Cria a árvore do XML
                    tree = ET.ElementTree(root)
                    # Define o nome do arquivo XML
                    xmlpathname = os.path.join("XMLRESULTS", contextnames[1])
                    # Formata o nome do arquivo XML
                    tree.write(xmlpathname + ".xml")
                except:
                    print("Erro ao processar o arquivo")
            else:
                self.tokenexist = False

        def getResulForTwoList(self):
            # resultlist = [np.array(self.deqofmean), getTimeInterval(self.uniqueTimeValues)];
            resultlist = np.array(self.deqofmean)
            return resultlist

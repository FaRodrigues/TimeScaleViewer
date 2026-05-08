# -*- coding: utf-8 -*-
# TimeScaleViewer version 1.5 (2026)
# Autor: Fernando Rodrigues (Inmetro)

import base64
import io
import itertools
import os
import statistics
import sys
import threading
import time
import time as TIME
import warnings
import xml.etree.ElementTree as ET
from collections import deque
from datetime import datetime
from ftplib import FTP
from threading import Event

import matplotlib.ticker as ticker
import numpy as np
import paramiko
import serial
from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import QDate, QThread, QFile, Qt, QRect
from PySide6.QtDesigner import QPyDesignerCustomWidgetCollection
from PySide6.QtGui import QFont
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import QMainWindow, QAbstractScrollArea, QMessageBox, QTableView, QSplitter, QCalendarWidget, \
    QGridLayout, QTabWidget, QAbstractItemView, QTextEdit, QComboBox, QPushButton, QLineEdit, \
    QLabel, QApplication, QDialogButtonBox, QSizePolicy, QLCDNumber, QDateTimeEdit
from astropy.time import Time
from matplotlib import pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from quantiphy import Quantity
from scp import SCPClient
from serial.tools import list_ports
from sklearn import linear_model

import Processa as pro
from Calendars import RapidYear
from MpsInterface import HROGWidget

trypath = ".\\CGGTTS"

isExist = os.path.exists(trypath)
if not isExist:
    os.makedirs(trypath)
baserootcggtts = trypath

if sys.executable.endswith("pythonw.exe"):
    sys.stdout = open(os.devnull, "w")
    sys.stderr = open(os.path.join(os.getenv("TEMP"), "stderr-" + os.path.basename(sys.argv[0])), "w")


def getEmbededObjet(self, tipo, nome):
    search = self.findChildren(tipo, nome)
    objeto = search[0]
    # print("objeto = {}".format(objeto))
    return objeto


def createSSHClient(server, port, user, password):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(server, port, user, password)
    return client


class ContextRootForCGGTTS:
    def __init__(self, rootcggtts, labname):
        self._dynrootCGGTTS = None
        self.prefixo = None
        self.contextxmlnode = xmlprofilesroot.find(".//profile[@labname='{}']".format(labname))
        self.setDynPrefix(self.contextxmlnode.find('prefix').text)
        self.setDynrootCGGTTS(rootcggtts)

    def getDynrootCGGTTS(self):
        return self._dynrootCGGTTS

    def setDynrootCGGTTS(self, valor1):
        self._dynrootCGGTTS = os.path.join(valor1, self.getDynPrefix())

    def getDynPrefix(self):
        return self.prefixo

    def setDynPrefix(self, pd):
        # print("prefixo = {}".format(pd))
        self.prefixo = pd

    def getContextXMLNode(self):
        return self.contextxmlnode


treeprefs = ET.parse('./xml/preferences.xml')
xmlprefsroot = treeprefs.getroot()

treehist = ET.parse('./xml/timescalehistory.xml')
xmlhistroot = treehist.getroot()

treeprofiles = ET.parse('./xml/clientprofiles.xml')
xmlprofilesroot = treeprofiles.getroot()

ultimate_freq_corr_value = 0

warnings.filterwarnings("ignore")
ser = serial.Serial()


def getDateFromMJD(MJD):
    tmjd = Time(MJD, format='mjd')
    stringdate = Time(tmjd.to_value('iso'), out_subfmt='date').iso
    return datetime.strptime(str(stringdate), "%Y-%m-%d").date()


def getFramedMessage(midmsg):
    linetext = "*" * (len(midmsg) + 4)
    intermessage = f"\n{linetext}\n{midmsg}\n{linetext}\n"
    return intermessage


steerHistoryFile = ET.parse(os.path.join('.', 'xml', 'freq_steer_history.xml'))
steerHistoryFileRoot = steerHistoryFile.getroot()


def updateScheduleConfig():
    paramDict = {}
    # carrega data atual MJD
    current_datetime = Time(datetime.now())
    paramDict['current_mjd'] = int(current_datetime.mjd)
    # Define as propriedades do processo de steering
    steerConfigFile = ET.parse(os.path.join('.', 'xml', 'steerparams.xml'))
    steerRoot = steerConfigFile.getroot()
    try:
        # Loads from XML scheduled steering params
        steerscheduled = steerRoot.find('./steerscheduled')
        # Load the configured time to apply the steer
        time_to_apply_param = steerscheduled.find('timetoapplysteer')
        paramDict['time_to_apply'] = datetime.strptime(str(time_to_apply_param.text), '%H:%M').time()
        # Load others scheduled params
        paramDict['comport_to_apply'] = steerscheduled.find('comport').text
        paramDict['hrog_mode'] = steerscheduled.find('hrogmode')
        paramDict['scheduled_offset_value'] = steerscheduled.find('scheduledoffsetvalue').text
    except BaseException as bex:
        print(bex)
    try:
        # Loads from XML applied steering params
        laststeerapplied = steerRoot.find('./laststeerapplied')
        paramDict['last_mjd_applied'] = laststeerapplied.find('mjdapplied').text
        last_time_applied = laststeerapplied.find('timeapplied').text
        paramDict['last_time_applied'] = datetime.strptime(str(last_time_applied), '%H:%M').time()
        paramDict['last_applied_offset_value'] = laststeerapplied.find('appliedoffsetvalue').text
    except BaseException as bex:
        print(bex)
    return paramDict


# Opções de alarme descritas no manual do equipamento e definidas no código na forma de um dict
optionsAlarmDict = {
    1: "External reference error",
    2: "Internal oscillator error",
    4: "PLL Lock error",
    8: "Tuning voltage error",
    16: "Invalid parameter",
    32: "Invalid command",
    64: "DC Backup Loss",
    128: "AC Power Loss"
}

chaves = list(optionsAlarmDict.keys())
valores = list(optionsAlarmDict.values())


def getNameOfFileFromMJD(prefixo, mjd):
    return '''{0:s}{1:.3f}'''.format(prefixo, mjd / 1000)


def getMjdFromNameOfButton(nameOfButton):
    return int(float(nameOfButton[6:]) * 1000)


def getMjdFromCggttsFileName(prefixo, cggttsfilename):
    return int(float(cggttsfilename[len(prefixo):]) * 1000)


def getDateFromCggttsFileName(prefixo, cggttsfilename):
    return getDateFromMJD(getMjdFromCggttsFileName(prefixo, cggttsfilename))


def getFrequencyCorrection(freq_offset_ini, Delta_t_desejada, angular_coef, delta_t_final, od, cd):
    # This function was disabled
    resultado = 0
    return resultado


class PlotCanvas(FigureCanvas):
    def __init__(self, parent=None, prefixo=None, listofmjds=None, NS=None, VM=None, VP=None, args=None,
                 width=1, height=1, dpival=1, mrefsi=None, modo=None):
        fig = Figure(figsize=(width / dpival, height / dpival), dpi=dpival)
        super(PlotCanvas, self).__init__(fig)

        slope = args['slope']
        VMfirst = VM[0]
        VMlast = VM[-1]
        # print("VMfirst = {} | VMlast = {}".format(VMfirst, VMlast))
        intercept = args['intercept']
        xx = args['eixo']
        if len(VM) > 1:
            # Desvio padrão das médias CGGTTS
            SD = np.round(statistics.stdev(VM), 3)
            # Valor da média consolidada
            Cmedia = np.round(np.mean(VM), 3)
            # Valor da mediana consolidada
            Cmedian = np.round(np.median(VM), 3)
        else:
            SD = 0
            Cmedia = np.round(VM[0], 3)
            Cmedian = np.round(VM[0], 3)

        numam = len(VM)

        # argumentosCGG = {"prefx": self.prefixo, "mjd": mjd}

        if modo == 1:
            nameOffiles = getNameOfFileFromMJD(prefixo, listofmjds[0])
            titlestring = '''Arquivo CGGTTS: {}'''.format(nameOffiles)

            subtitlestring1 = '''Mediana Consolidada = {} ns | Desvio Padrão = {} | Coeficiente Angular = {} (por 16 minutos)'''.format(
                Cmedian, SD, np.round(slope, 7))
            # Define a figura onde será exibido o resultado
            fig.suptitle(titlestring, fontsize=11, fontweight='normal', color='black', y=0.98)
        else:
            # listOfFiles = list(map(getNameOfFileFromMJD, argumentosCGG));
            listOfFiles = list(map(getNameOfFileFromMJD, itertools.repeat(prefixo, len(listofmjds)), listofmjds))
            titlestring = ''' MJDs: {} '''.format(listofmjds)
            subtitlestring1 = '''Mediana Consolidada = {} ns | Coeficiente Angular = {}'''.format(Cmedian,
                                                                                                  np.round(slope, 4))
            # Define a figura onde será exibido o resultado
            fig.suptitle(titlestring, fontsize=9, fontweight='normal', color='black', y=0.98)

        fig.subplots_adjust(hspace=0.45, wspace=0.3)
        ax = fig.add_subplot(2, 1, 1)
        ax.set_title(subtitlestring1, fontsize=10)
        ax.plot(VM, 'r.-', label='Valor da mediana')
        ax.axhline(y=Cmedian, color='green', linestyle='-')
        # Plota a reta com os valores da projeção
        ax.plot(xx, VP)
        # ax.annotate('Valor Médio', xy=(10, Cmedia), xytext=(80, Cmedia-0.5))
        if len(VM) > 1:
            listOfVerticalTicks = list(np.arange(min(VM), max(VM) + 1, (max(VM) - min(VM)) / 10))
        else:
            listOfVerticalTicks = VM
        ax.tick_params(axis='y', labelsize=7)
        ax.yaxis.set_ticks(listOfVerticalTicks)
        ax.yaxis.set_major_formatter(ticker.FormatStrFormatter('%0.2f'))
        # print("min(VM) = {} | max(VM) = {} | listOfVerticalTicks = {}".format(min(VM), max(VM)+1, listOfVerticalTicks))
        ax.grid(which='major', color='#BBBBBB', linewidth=0.8)
        ax.grid(which='minor', color='#CCCCCC', linestyle=':', linewidth=0.5)
        ax.minorticks_on()
        plt.title('Valor da mediana')

        # Gera os índices para o gráfico de barras
        ind = np.arange(len(NS))
        ax2 = fig.add_subplot(2, 1, 2)
        gapfound = False
        gapindex = []
        gapbarindex = [0]
        sttimeunique = pro.getUTV()

        if len(mrefsi) > 2:
            gapfound = True
            gapbarindex = []

            limiar = 20

            effectiveInterval = [sublist[0] for sublist in mrefsi if sublist[0] > limiar]
            gapindexlist = [sublist[1] for sublist in mrefsi if sublist[0] > limiar]

            for st in range(len(sttimeunique)):
                if sttimeunique[st] in gapindexlist:
                    gapbarindex.append(st)

            # Transforma os objetos datetime em string por meio do método .time()
            g1 = datetime.strptime(sttimeunique[0], '%H%M%S').time()
            g2 = datetime.strptime(sttimeunique[1], '%H%M%S').time()
            subtitlestring2 = '''GAPS = {mrefsi} minutos | STTIME {g1}'''.format(
                mrefsi=effectiveInterval, g1=gapindexlist)
        else:
            effectiveInterval = mrefsi
            gapbarindex = [0]
            # print(f"effectiveInterval = {effectiveInterval}")
            subtitlestring2 = '''Tempo de intervalo = {mrefsi} minutos'''.format(num=numam, mrefsi=effectiveInterval)

        labelx = '''Número Consolidado de Amostras = {num}'''.format(num=numam)
        ax2.set_title(subtitlestring2, fontsize=10)
        ax2.set_xlabel(labelx, fontsize=11)
        ax2.set_ylabel('Número de Satélites', fontsize=10)
        barlist = ax2.bar(ind, NS, label='Número de amostras')
        if gapfound:
            for ii in gapbarindex:
                barlist[ii].set_color('r')
        ax2.tick_params(axis='y', labelsize=7)
        ax2.yaxis.set_ticks(np.arange(min(NS), max(NS) + 1, 1.0))
        ax2.yaxis.set_ticks_position('right')
        ax2.grid(which='major', color='#BBBBBB', linewidth=0.8)
        ax2.grid(which='minor', color='#CCCCCC', linestyle=':', linewidth=0.5)
        ax2.minorticks_on()

        plt.title('Número de amostras')


class UserInterfaceSteer(QMainWindow, threading.Thread):
    def __init__(self, event, parent=None):
        super().__init__(parent)
        threading.Thread.__init__(self)
        self.stopped = event
        self._stop_event = threading.Event()
        self.scheduledValue = None
        self.estrategCorr = None
        self.lastVMvalue = None
        self.contextSlope = None
        self.daysinterval = None
        self.DRCGG = None
        self.lastFreqCorrCalculated = None
        self.lastFreCorrected = None
        self.dataprocesstoken = None
        self.newcorrectiontoken = False

        self.dataprocesstoken = False
        self.thread = QThread()

        self.HROGWidget = None

        loader = QUiLoader()
        guipath = os.path.abspath(os.path.join(".", "gui", "ui", "formMainWindowSteer.ui"))
        file = QFile(guipath)
        file.open(QFile.OpenModeFlag.ReadOnly)
        self.mainwindow = loader.load(file, self.window())
        file.close()
        QtCore.QCoreApplication.processEvents()
        # self.mainwindow.show()

        self.tokenfoundport = ""
        self.tab1labels = ["Deriva Diária CGGTTS", "Deriva Periódica CGGTTS"]
        self.tab2labels = ["Interface Micro Phase Stepper"]

        self.ultimate_freq_corr_value = 0
        self.lastFreqCorrectionArgs = {}

        self.menubar = self.menuBar()  # self.findChild(QMenuBar, 'menubar')
        self.statusbar = self.statusBar()
        self.statusbar.setFont(QtGui.QFont('Arial', 10, QFont.Weight.DemiBold))
        self.setWindowTitle("Inmetro - Processamento CGGTTS - Versão 1.14 (2025)")
        self.menubar.setFont(QtGui.QFont('Arial', 12, QFont.Weight.DemiBold))

        # Busca na UserInterface o objeto referente à tabela de nomes de arquivos
        self.tableView = getEmbededObjet(self, QTableView, "tableViewBase")
        # print(self.mainwidget.findChildren(QTableView, 'tableViewBase'))
        tablewidth = self.tableView.geometry().width()

        # Busca na UserInterface o objeto referente ao splitter container
        self.mastersplitter = getEmbededObjet(self, QSplitter, "splitter")
        # QSplitter.setMinimumWidth(tablewidth)
        self.mastersplitter.setMinimumWidth(tablewidth)
        self.mastersplitter.setStretchFactor(1, 1)

        # Busca na UserInterface o objeto referente ao splitter container
        self.calendarWidget = getEmbededObjet(self, QCalendarWidget, 'calendarWidget')
        # self.calendarWidget.resize(100, 100);

        self.calendarWidget.setFont(QtGui.QFont('Arial', 3, QFont.Weight.DemiBold))

        # Busca na UserInterface o objeto referente ao layout container para os gráficos
        self.localgridLayout = self.findChild(QGridLayout, 'gridLayoutRight')

        # Ajusta a proporção das janelas dentro do layout
        # self.localgridLayout.setColumnStretch(0, 1)

        # Cria o widget container para as abas
        self.tab1 = QtWidgets.QWidget()
        self.tab1.setObjectName('Day')
        # self.tab2 = QtWidgets.QWidget()
        # self.tab2.setObjectName('Period')
        self.qtabwidget = getEmbededObjet(self, QTabWidget, 'tabWidget')
        # self.qtabwidget = QtWidgets.QTabWidget()

        # Muda o 'shape' das tabs em QTabWidget
        tab_shape = QTabWidget.TabShape.Triangular
        self.qtabwidget.setTabShape(tab_shape)

        # IMPORTANTE - Adiciona os layouts das tabs
        self.tab1.layout = QtWidgets.QVBoxLayout()
        self.tab1.setLayout(self.tab1.layout)

        # self.tab2.vlayout = QtWidgets.QVBoxLayout()
        # self.tab2.setLayout(self.tab2.vlayout)

        # Adiciona as tabs
        self.qtabwidget.addTab(self.tab1, self.tab1labels[0])
        # self.qtabwidget.addTab(self.tab2, self.tab2labels[0])

        self.temp = 0
        self.comport = None

        # Loads from paramDict scheduled steering params
        current_steer_parameters = updateScheduleConfig()
        date_to_apply = getDateFromMJD(current_steer_parameters['current_mjd'])
        time_to_apply = current_steer_parameters['time_to_apply']
        scheduled_offset_value = current_steer_parameters['scheduled_offset_value']
        # Loads from paramDict last applied steering params
        last_date_applied = getDateFromMJD(int(current_steer_parameters['last_mjd_applied']))
        last_time_applied = current_steer_parameters['last_time_applied']
        last_applied_offset_value = current_steer_parameters['last_applied_offset_value']

        message = f"Agendamento realizado para Steering no dia {date_to_apply} no horário {time_to_apply}"
        print(getFramedMessage(message))

        print("Agendamento diário para aplicação da correção: {}\n".format(time_to_apply))
        # executa job no dia/horário agendado
        # schedule.every().day.at("{:02d}:{:02d}".format(time_to_apply.hour, time_to_apply.minute)).do(doHROGSteer)

        self.labelUNITFREQCORROP = getEmbededObjet(self, QLabel, "labelNumberFREQ")
        self.sevenSEGMENTSFREQCORROP = getEmbededObjet(self, QLCDNumber, "lcdNumberFREQ")

        self.labelUNITFREQCORRAG = getEmbededObjet(self, QLabel, "labelNumberFREQAG")
        self.sevenSEGMENTSFREQCORRAG = getEmbededObjet(self, QLCDNumber, "lcdNumberFREQAG")

        self.dateTimeEditOP = getEmbededObjet(self, QDateTimeEdit, "dateTimeEditOP")
        self.dateTimeEditAG = getEmbededObjet(self, QDateTimeEdit, "dateTimeEditAG")

        self.sevenSEGMENTSERRO = getEmbededObjet(self, QLCDNumber, "lcdNumberERRO")

        self.labelEquipIdent = getEmbededObjet(self, QLabel, 'labelEquipIdent')
        # self.labelEquipIdent.setText("12")

        # self.labelLabTemp = getEmbededObjet(self, QLabel, "labelLabTemp")

        self.pushButtonEst = getEmbededObjet(self, QPushButton, "pushButtonEst")
        self.pushButtonEst.setStyleSheet("background-color: rgb(128, 128, 128);")
        self.pushButtonEst.setEnabled(False)
        self.pushButtonEst.clicked.connect(self.applyLocalFreqCorr)

        listaEstrategCorr = {1: "Auto", 2: "Fixed Time", 3: "Manual"}
        self.comboBoxEst = getEmbededObjet(self, QComboBox, "comboBoxEst")
        self.comboBoxEst.addItems(listaEstrategCorr.values())
        self.comboBoxEst.activated.connect(self.defineEstrategCorr)

        # self.labelLabTemp.setText("23")
        # self.updateInfoInternalTemp()
        self.updateHROGID()

        last_applied_offset = float(last_applied_offset_value) / 10 ** 6
        scheduled_offset = float(scheduled_offset_value) / 10 ** 6

        self.atualizaSteeringDisplay(tipo='op', freqcorr=last_applied_offset,
                                     datetimeparam=datetime.combine(last_date_applied, last_time_applied))
        self.atualizaSteeringDisplay(tipo='ag', freqcorr=scheduled_offset,
                                     datetimeparam=datetime.combine(date_to_apply, time_to_apply))

        self.checkIfComPorts()

        def setDataprocesstoken(dpt):
            self.dataprocesstoken = dpt

        def getDataprocesstoken():
            return self.dataprocesstoken

        # setDataprocesstoken(False)

        def setNewCorrectionToken(nct):
            self.newcorrectiontoken = nct

        def getNewCorrectionToken():
            return self.newcorrectiontoken

        # setNewCorrectionToken(False)

        def setLastFreCorrected(lfc):
            self.lastFreCorrected = lfc

        def getLastFreCorrected():
            return self.lastFreCorrected

        def setLastFreqCorrCalculated(lfcc):
            self.lastFreqCorrCalculated = lfcc

        def getLastFreqCorrCalculated():
            return self.lastFreqCorrCalculated

        # Override the resizeEvent method
        def resizeEvent(self, event):
            self.tableView.resizeColumnsToContents()
            self.tableView.resizeRowsToContents()
            # self.tableView.setSizeAdjustPolicy(QAbstractScrollArea.)
            QMainWindow.resizeEvent(self, event)

        def setLocaldynpath(path):
            if not (os.path.exists(path)):
                os.makedirs(path)
            self.localdynpath = path

        def getContextProcess(mjdinterval, prefixo):
            self.processo = pro.Processacggtts(mjdinterval, prefixo)
            return self.processo

        def atualizaCGGTTSFiles():
            updateCGGTTSfiles(self)

        def calculateNewCorrection():
            if getDataprocesstoken():
                newfreqCorrPeriod = int(self.qtextNewPeriod.toPlainText())
                self.qtextNewCorrValue.clear()
                # print(newfreqCorrPeriod)
                deltaM = (-1) * getContextSlope()
                # print("deltaM = {}".format(deltaM))
                lastVM = getLastVMvalue()
                # print("lastVM = {}".format(lastVM))
                # Busca o intervalo de dias utilizado para cálculo da deriva
                actualDI = getDaysInterval()
                # print("actualDI = {}".format(actualDI))

                # Busca o último valor utilizado para correção de Frequência
                actualLFCV = self.lastFreqCorrectionArgs['lastvalueArg']
                # print("actualLFCV = {}".format(actualLFCV))

                nfcorr = getFrequencyCorrection(np.divide(actualLFCV, np.power(10, 6)), 0, deltaM, lastVM, actualDI,
                                                newfreqCorrPeriod)
                # print(nfcorr)
                setLastFreqCorrCalculated(nfcorr)
                self.qtextNewCorrValue.insertPlainText("{:10.5f}".format(nfcorr))
                # Altera a cor de fundo do botão de cálculo da correção de frequência
                self.calcNewFreqCorr.setStyleSheet("background-color: rgb(255, 170, 0);")
                setNewCorrectionToken(True)
                self.pushButtonAtualizaCorr.setProperty('enabled', getNewCorrectionToken())
                # perguntaSalvar()
            else:
                setNewCorrectionToken(False)
                self.calcNewFreqCorr.setStyleSheet("background-color: rgb(255, 0, 0);")
                atualizaStatusBar('Selecione uma data ou período antes de realizar o cálculo', "blue")

        def perguntaSalvar():
            if getNewCorrectionToken():
                dlg = QMessageBox(self)
                dlg.setWindowTitle("Atenção")
                dlg.setText("Deseja salvar a atual correção de frequência\ncom valor de {:3.5f} uHz?".format(
                    getLastFreqCorrCalculated()))
                dlg.setStandardButtons(QDialogButtonBox.StandardButton.Yes | QDialogButtonBox.StandardButton.No)
                dlg.setIcon(QMessageBox.Icon.Question)
                button = dlg.exec()
                if button == QMessageBox.DialogCode.Accepted:
                    print("Sim!")
                    setLastFreqCorrectionData()
                else:
                    print("Não!")
            else:
                pass

        def atualizaStatusBar(basemessage, cor):
            try:
                msg = "Status | {}".format(basemessage)
                self.statusbar.showMessage(msg)
                stylelocal = ("QStatusBar {{background-color: {}; color: white; border: 1px solid blue; "
                              "font-weight:normal}}")
                style = stylelocal.format(cor)
                self.statusbar.setStyleSheet(style)
                QtCore.QCoreApplication.processEvents()
            except BaseException as ex:
                pass

        def atualizaCalendario(mjd):
            dataconvertida = getDateFromMJD(mjd)
            # print(dataconvertida)
            self.calendarWidget.setSelectedDate(dataconvertida)

        def getIntersectMJDNames(cwlocal, se):
            # Verifica se os items da lista de MJDs em cwlocal constam da tabela
            # Obs: Quando o token se é 'True' seleciona e realça a linha da tabela
            # listref = list(map(getNameOfFileFromMJD, getCGGTTSPrefix(), cwlocal));
            contextprefix = getContextRootForCGGTTS().getDynPrefix()
            listref = list(map(getNameOfFileFromMJD, itertools.repeat(contextprefix, len(cwlocal)), cwlocal))
            # print("listref = {}".format(listref))
            intersect = deque()
            for ii in range(self.tablemodel.rowCount()):
                mjdi = getMjdFromNameOfButton(self.tablemodel.item(ii, 0).text())
                if mjdi in cwlocal:
                    intersect.append(mjdi)
                    if se:
                        self.tableView.selectRow(ii)
            return intersect

        def getLastVMvalue():
            return self.lastVMvalue

        def setLastVMvalue(vmval):
            self.lastVMvalue = vmval

        def getContextSlope():
            return self.contextSlope

        def setContextSlope(cs):
            self.contextSlope = cs

        def setDaysInterval(di):
            self.daysinterval = di

        def getDaysInterval():
            return self.daysinterval

        def loadHROGWidget(tokenadd):
            stopFlag = Event()
            # thread = MyThread(stopFlag)
            print("tokenadd = {}".format(tokenadd))
            if (tokenadd is True) or (self.HROGWidget is None):
                self.HROGWidget = HROGWidget(stopFlag)
                self.tab2.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
                self.HROGWidget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
                self.HROGWidget.setStyleSheet(StyleSheet)
                self.errcode = 0
                self.tab2.vlayout.addWidget(self.HROGWidget)
                QtCore.QCoreApplication.processEvents()
                self.HROGWidget.initiateMQTT()
                self.HROGWidget.start()
                # hrogwidget = self.mainwindow.findChild(QWidget, 'formHROGWidget')
                # hrogwidget.setGeometry(0,0,1200,600)
                # hrogwidget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            else:
                # thread = MyThread(stopFlag)
                seport = self.HROGWidget.checkIfComPorts()
                print("seport = {}".format(seport))
                self.HROGWidget.initiateMQTT()

                # self.HROGWidget.start()

                if seport[0] is True:
                    self.tokenfoundport = True
                    arm = self.HROGWidget.displayErrorCode()
                    atualizaStatusBar(arm[0], arm[1])
                    self.HROGWidget.showInterfaceValues()
                    QtCore.QCoreApplication.processEvents()
                else:
                    plaintext = QTextEdit("O instrumento HROG-10 não foi encontrado nas portas: {}".format(seport[1]))
                    plaintext.setMinimumSize(120, 50)
                    plaintext.setStyleSheet("background-color: rgb(255, 128, 128);")
                    # self.tab2.vlayout.addWidget(plaintext)
                    atualizaStatusBar("O instrumento HROG-10 não foi encontrado nas portas: {}".format(seport[1]),
                                      "red")

        # self.localgridLayout.addWidget(self.qtabwidget, 0, 0)
        atualizaStatusBar('Pronto', 'blue')

        def setContextRootForCGGTTS(labname):
            self.DRCGG = ContextRootForCGGTTS(baserootcggtts, labname)
            pathtocheck = self.DRCGG.getDynrootCGGTTS()
            if not (os.path.exists(pathtocheck)):
                os.makedirs(pathtocheck)

        # def setContextProcessForCGGTTS(labname, prefixo, mjdinterval):
        #     self.processomulti = deque()
        #     DRCGG = contextRootForCGGTTS(baserootcggtts, labname)
        #     pathtocheck = DRCGG.getDynrootCGGTTS()
        #
        #     if not (os.path.exists(pathtocheck)):
        #         os.makedirs(pathtocheck)
        #
        #     for mjd in mjdinterval:
        #         self.processomulti.append(pro.processaCGGTTS(mjd, prefixo))

        # def getContextProcessForCGGTTS():
        #     return self.processomulti

        def getContextRootForCGGTTS():
            return self.DRCGG

        def getTimeInterval(uniqueTimeValues):
            uniqueIntervalValues = []
            # print(uniqueTimeValues)
            # Cria um objeto deque dequeInterval
            dequeInterval = deque()
            # Transforma a lista de strings em uniqueTimeValues numa lista de objetos datetime
            indexoffset = 1
            for uvindex in range(0, len(uniqueTimeValues) - indexoffset):
                ''' Atenção: Os objetos datetime devem obedecer ao formato hhmmss de STTIME '''
                currentutv = uniqueTimeValues[uvindex]
                t1 = datetime.strptime(currentutv, '%H%M%S')
                t2 = datetime.strptime(uniqueTimeValues[uvindex + indexoffset], '%H%M%S')
                difftime = abs(t2 - t1)
                # print(uvindex, indext, difftime, uniqueTimeValues[indext[0]], uniqueTimeValues[indext[1]])
                current_interval = difftime.total_seconds() / 60
                dequeInterval.append([current_interval, currentutv])
                # Calcula os valores não repetidos na lista listDequeInterval
                # dictInterval = Counter(dequeInterval)
                uniqueIntervalValues = list(dequeInterval)
            return uniqueIntervalValues

        def fromCalendar(clickeddate):
            # print(clickeddate)
            self.tableView.clearSelection()
            self.tableView.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
            # QCalendarWidget.clearMask()
            self.calendarWidget.clearMask()
            # QtCore.QDate.toPython()
            data1 = Time(str(clickeddate.toPython()))
            MJD = int(data1.to_value('mjd'))
            doy = data1.to_value('yday', subfmt='date')
            yearstring = doy.rsplit(':')[0]
            # doystring = doy.rsplit(':')[1];
            rapidyear = RapidYear(int(yearstring))
            constextWeek = rapidyear.getRapidMjdWeekNumber(MJD)[1]
            prefxbase = getContextRootForCGGTTS().getDynPrefix()
            # Data clicada no calendário
            # fileOfContextDay = getNameOfFileFromMJD(prefxbase, MJD)
            # lnfi = list(np.sort(list(getIntersectFileNames(constextWeek, True))));
            mjdlistfromintersect = list(list(getIntersectMJDNames(constextWeek, True)))
            # print(f"mjdlistfromintersect em fromCalendar = {mjdlistfromintersect}")
            mjdlistfromintersect.sort()
            tokenshow = False
            # # Se a data clicada existe na semana de contexto então tokenshow = True
            # if fileOfContextDay in lnfi:
            #     tokenshow = True
            #     processaDados(self, prefxbase, lnfi, tokenshow)
            # else:
            #     processaDados(self, prefxbase, [fileOfContextDay], tokenshow)

            # Se a data clicada existe na semana de contexto então tokenshow = True
            if MJD in mjdlistfromintersect:
                tokenshow = True
                processaDados(prefxbase, mjdlistfromintersect, tokenshow)
            else:
                # Atualiza a barra de status
                basemessage = 'O arquivo relativo ao MJD = {} não foi encontrado.'.format(MJD)
                removeprocessinggraphs(self, 0)
                atualizaStatusBar(basemessage, "red")
                # processaDados(self, prefxbase, lnfi, tokenshow)

        def inicializaView():
            localprefixo = getContextRootForCGGTTS().getDynPrefix()
            path = os.path.join(baserootcggtts, localprefixo)
            pasta = os.listdir(path)
            if len(pasta) == 0:
                removeprocessinggraphs(self, 0)
                pass
            else:
                # Inicializa a exibição da tab1
                eventolista(self.tablemodel.item(0))
                self.tableView.selectRow(0)

        def eventolista(btn):
            # Recover the name defined in the command -> item = QStandardItem(str(name))
            # self.tableView.clearSelection()
            self.tableView.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
            nameOfButton = btn.model().item(btn.row()).text()  # nameOfButton
            MJD = getMjdFromNameOfButton(nameOfButton)
            atualizaCalendario(MJD)
            localprefixo = getContextRootForCGGTTS().getDynPrefix()
            # Data clicada no calendário
            # fileOfContextDay = getNameOfFileFromMJD(localprefixo, MJD)
            # processaDados(self, localprefixo, [fileOfContextDay], True)
            processaDados(localprefixo, [MJD], True)

        def processaDados(prefx, listnamesfromintersect, seplot):
            # print("listnamesfromintersect = {}".format(type(listnamesfromintersect)))
            modoexibe = 1
            if len(listnamesfromintersect) > 1:
                modoexibe = 2

            vmdeque = deque()
            nsdeque = deque()

            getLastFreqCorrectionData()
            setNewCorrectionToken(False)
            # self.pushButtonAtualizaCorr.setProperty('enabled', getNewCorrectionToken())
            # Reseta a exibição de valores do período de cálculo
            # self.qtextCalcPeriod.clear()
            # Reseta a exibição de valores de correção de frequência
            # self.qtextNewCorrValue.clear()
            # Altera a cor de fundo do botão de cálculo da correção de frequência
            # self.calcNewFreqCorr.setStyleSheet("background-color: rgb(0, 128, 255);")
            localDI = len(listnamesfromintersect)
            setDaysInterval(localDI)
            # self.qtextCalcPeriod.insertPlainText("{}".format(localDI))
            # self.qtextNewPeriod.clear()
            # self.qtextNewPeriod.insertPlainText("{}".format(2 * localDI))

            # Atualiza a barra de status
            basemessage = 'Processando os seguintes MJDs: {}'.format(listnamesfromintersect)
            atualizaStatusBar(basemessage, "green")

            # setContextProcessForCGGTTS("INXE", prefx, listnamesfromintersect)
            # XD = list(getContextProcessForCGGTTS())
            # for xd in XD:
            #     print(xd.getResulList())

            # for nameOffile in listnamesfromintersect:
            processo = getContextProcess(listnamesfromintersect, prefx)
            global medianREFSYSinterval

            if processo.tokenexist:
                listresult = processo.getResulList()
                # Quantidade de satélites
                ns = list(listresult[:, 0])
                # Valores das médias CGGTTS
                vm = list(listresult[:, 1])
                # print("vm:{}".format(vm))

                setLastVMvalue(vm[-1])

                vmdeque.extend(vm)
                nsdeque.extend(ns)
                # intersectdeque.append(mjd);
                # Cálculo do coeficiente linear do desvio de tempo
                xxuno = np.linspace(1, len(vm), num=len(vm))
                X = np.array(xxuno).reshape((-1, 1))
                reg = linear_model.LinearRegression()
                reg.fit(X, vm)

                ########################################################################################################
                proslope = reg.coef_[0]
                prointercept = reg.intercept_
                #################################################################################################

                setContextSlope(proslope)

                def regmapfunc(x):
                    return (proslope * x) + prointercept

                VProj = list(map(regmapfunc, xxuno))
                # print("VProj = {}".format(VProj[-1]))
                ##################################################################################################

                uniqueTimeValues = pro.getUTV()
                medianREFSYSinterval = getTimeInterval(uniqueTimeValues)
                # print(f"medianREFSYSinterval = {medianREFSYSinterval}")
                # print(listresult[:,1])
                # print(np.array(uniqueTimeValues, dtype=int))

                if seplot and localDI == 1:
                    gvfigwidth = self.tab1.geometry().width()
                    gvfigheight = self.tab1.geometry().height()

                    # argumentos = [("slope", proslope), ("intercept", prointercept)]
                    argumentos = {"slope": proslope, "intercept": prointercept, "eixo": xxuno}
                    # self.qtextVMlast.clear()
                    # self.qtextVPlast.clear()
                    # self.qtextVMlast.insertPlainText("{:3.3f}".format(getLastVMvalue()))
                    # self.qtextVMlast.setStyleSheet("background-color: rgb(228, 228, 255);")
                    # self.qtextVPlast.insertPlainText("{:3.3f}".format(VProj[-1]))
                    # self.lcdNumber.setProperty("value", float(VProj[-1]))
                    # Instancia um novo gráfico
                    localprefixo = getContextRootForCGGTTS().getDynPrefix()
                    newplotCanvas = PlotCanvas(self, prefixo=localprefixo, listofmjds=listnamesfromintersect, NS=ns,
                                               VM=vm, VP=VProj, args=argumentos, width=gvfigwidth, height=gvfigheight,
                                               dpival=96, mrefsi=medianREFSYSinterval, modo=1)
                    # Remove widgets existentes em localgridLayout
                    removeprocessinggraphs(self, 0)
                    # QtCore.QCoreApplication.processEvents()
                    # Adiciona o novo gráfico newplotCanvas
                    self.tab1.layout.addWidget(newplotCanvas)
                    # Atualiza o foco na janela onde o 'newplotCanvas' foi adicionado
                    self.qtabwidget.setCurrentWidget(self.qtabwidget.children()[0].findChild(QtWidgets.QWidget, "Day"))
                    self.qtabwidget.setTabText(0, self.tab1labels[0])
                    # Atualiza a barra de status
                    basemessage = "Exibindo o resultado de: {}".format(listnamesfromintersect)
                    atualizaStatusBar(basemessage, "blue")
            else:
                # Atualiza a barra de status
                basemessage = "O arquivo relativo ao MJD = {} não foi encontrado.".format(listnamesfromintersect)
                removeprocessinggraphs(self, 0)
                atualizaStatusBar(basemessage, "red")
                removeprocessinggraphs(self, 0)

            vmcw = np.array(vmdeque)
            nscw = np.array(nsdeque)
            # print("Lista:")
            # print(vmcw)

            if modoexibe == 2:
                # Cálculo do coeficiente linear do desvio de tempo
                xxcw = np.linspace(1, len(vmcw), num=len(vmcw))
                XCW = np.array(xxcw).reshape((-1, 1))
                regcw = linear_model.BayesianRidge()
                regcw.fit(XCW, vmcw)

                ########################################################################################################
                proslopecw = regcw.coef_[0]
                prointerceptcw = regcw.intercept_

                setContextSlope(proslopecw)

                def regmapfunccw(x):
                    return (proslopecw * x) + prointerceptcw

                VProjcw = list(map(regmapfunccw, xxcw))

                ########################################################################################################

                gvfigwidth = self.tab1.layout.geometry().width()
                gvfigheight = self.tab1.layout.geometry().height()

                argumentoscw = {"slope": proslopecw, "intercept": prointerceptcw, "eixo": xxcw}

                # self.qtextVMlast.clear()
                # self.qtextVPlast.clear()
                # self.qtextVMlast.insertPlainText("{:3.3f}".format(vmcw[-1]))
                # self.qtextVMlast.setStyleSheet("background-color: rgb(228, 228, 228);")
                # self.qtextVPlast.insertPlainText("{:3.3f}".format(VProjcw[-1]))
                # self.qtextVPlast.setStyleSheet("background-color: rgb(228, 228, 228);")

                # # Atualiza a barra de status
                # basemessage = 'Exibindo o resultado de: {}'.format(listnamesfromintersect);
                # atualizaStatusBar(basemessage, "blue")
                # QtCore.QCoreApplication.processEvents()

                # Instancia um novo gráfico
                localprefixo = getContextRootForCGGTTS().getDynPrefix()
                newplotCanvas = PlotCanvas(self, prefixo=localprefixo, listofmjds=listnamesfromintersect, NS=nscw,
                                           VM=vmcw, VP=VProjcw, args=argumentoscw,
                                           width=gvfigwidth, height=gvfigheight, dpival=96, mrefsi=medianREFSYSinterval,
                                           modo=2)

                # Remove widgets existentes em localgridLayout
                removeprocessinggraphs(self, 0)

                # Adiciona o novo gráfico newplotCanvas
                self.tab1.layout.addWidget(newplotCanvas)
                # print(self.qtabwidget.children()[0].findChild(QtWidgets.QWidget, "Controle").objectName())
                # print(self.qtabwidget.children()[0])
                # Atualiza o foco na janela onde o 'newplotCanvas' foi adicionado
                self.qtabwidget.setCurrentWidget(self.qtabwidget.children()[0].findChild(QtWidgets.QWidget, "Day"))
                self.qtabwidget.setTabText(0, self.tab1labels[1])
                QtCore.QCoreApplication.processEvents()

                # Atualiza a barra de status
                basemessage = "Exibindo o resultado de: {}".format(listnamesfromintersect)
                atualizaStatusBar(basemessage, "blue")

            setDataprocesstoken(True)
            # self.calcNewFreqCorr.setProperty('enabled', getDataprocesstoken())

        def removeprocessinggraphs(self, numero):
            # Remove widgets existentes em localgridLayout
            if numero == 0:
                # self.setStyleSheet("background-color: rgb(228, 228, 228)")
                if self.tab1.layout.count() > 0:
                    for i in reversed(range(self.tab1.layout.count())):
                        self.tab1.layout.itemAt(i).widget().setParent(parent)

            # if numero == 1:
            #     # self.setStyleSheet("background-color: rgb(228, 228, 228)")
            #     if self.tab2.vlayout.count() > 0:
            #         for i in reversed(range(self.tab2.vlayout.count())):
            #             self.tab2.vlayout.itemAt(i).widget().setParent(parent)

        def tabevento(tabindex):
            # tabindex identifica o índice da tab selecionada
            # print(tabindex)
            tokenadd = False
            if tabindex == 1:
                removeprocessinggraphs(self, tabindex)
                if self.tab2.vlayout.count() == 0:
                    tokenadd = True
                loadHROGWidget(tokenadd)
            else:
                atualizaStatusBar('Pronto', "blue")

        def getLastFreqCorrectionData():
            try:
                lfcd = xmlhistroot.findall("freqcorrections/freqcorrection")
                # UserInterfaceDmtic.lastFreqCorrectionDate.value = lfcd[-1].find("date").text
                lastdate = lfcd[-1].find("date").text
                self.lastFreqCorrectionDate.setDate(QDate.fromString(lastdate, "dd/MM/yyyy"))
                lastvalue = float(lfcd[-1].find("value").text)
                self.ultimateFreqCorrectionText.clear()
                self.ultimateFreqCorrectionText.setText("{}".format(lastvalue))
                # self.setUltimateFreqCorrValue(lastvalue)
                # print("lastvalue = {}".format(dir(UserInterfaceDmtic)))
                self.lastFreqCorrectionArgs = {"lastdateArg": lastdate, "lastvalueArg": lastvalue}
            except Exception as ex:
                lfcd = ""

        def setLastFreqCorrectionData():
            # print("setLastFreqCorrectionData")
            try:
                lfcdi = xmlhistroot.find("freqcorrections")
                ET.dump(lfcdi)
                freqC = ET.SubElement(lfcdi, "freqcorrection")
                data = ET.SubElement(freqC, "date")
                data.text = "hoje"
                valor = ET.SubElement(freqC, "value")
                valor.text = getLastFreqCorrCalculated()
                ET.dump(xmlhistroot)
            except:
                pass

        def getDecodedPass(sina, cluster):
            sina_string = ""
            for x in range(cluster):
                base64_bytes = sina[::-1].encode("utf-8")
                sina_string_bytes = base64.b64decode(base64_bytes)
                sina_string = sina_string_bytes.decode("utf-8")
                sina = sina_string
            return sina_string

        def updateCGGTTSfiles(self):
            # Define a data partir da qual refazer o download
            datetodownload = QDate.currentDate().addDays(-7)
            message = "ATENÇÃO: Os arquivos locais a partir da data '{}' serão sobrescritos".format(
                datetodownload.toPython().strftime("%d/%m/%Y"))
            atualizaStatusBar(message, "red")
            TIME.sleep(3)
            listOfRemotefiles = []
            context = getContextRootForCGGTTS()
            # define o nó XML de contexto
            cxn = context.getContextXMLNode()
            labname = cxn.get('labname')
            message = 'A atualização dos arquivos CGGTTS para o repositório de {} foi iniciada'.format(labname)
            atualizaStatusBar(message, "orange")
            # print("labname = {}".format(labname))
            contextcommtype = cxn.get('commtype')
            contextlink = cxn.find('accesslink').text
            contextuser = cxn.find('username').text
            contextpass = cxn.find('password').text
            contextprefix = cxn.find('prefix').text
            contextrxid = cxn.find('rxid').text
            # print('usern: {}'.format(cxn.find('username').text))
            # QtCore.QCoreApplication.processEvents()
            if contextcommtype == 'FTP':
                message = 'Iniciando a conexão ao repositório do BIPM'
                atualizaStatusBar(message, "orange")
                try:
                    ftps = FTP(contextlink)  # replace with your host name or IP
                    ftps.login(user=contextuser, passwd='{}'.format(getDecodedPass(contextpass, 6)))
                    message = str(ftps.getwelcome())
                    atualizaStatusBar(message, "green")
                    TIME.sleep(1)
                    ftps.cwd('data/UTCr/{}/CGGTTS'.format(labname))  # change into "debian" directory
                    ftps.retrlines('NLST', listOfRemotefiles.append)  # list directory contents
                    sortedListOfRemotefiles = np.sort(listOfRemotefiles)
                    # Busca o caminho dinâmico de contexto
                    self.localdynpath = context.getDynrootCGGTTS()
                    # Compara a existência de arquivos locais com o repositório de contexto
                    for path, subdirs, localfiles in os.walk(self.localdynpath):
                        # print(sorted(localfiles)[-1])
                        for remotefile in sortedListOfRemotefiles:

                            filedate = getDateFromCggttsFileName(contextprefix, remotefile)

                            if (remotefile in localfiles) and (filedate < datetodownload):
                                message = "O arquivo '{}' já tem uma versão local".format(remotefile)
                                atualizaStatusBar(message, "orange")
                            else:
                                local_fn = os.path.join(self.localdynpath, os.path.basename(remotefile))
                                message = "Iniciando download do arquivo: {}".format(remotefile)
                                atualizaStatusBar(message, "brown")
                                # print(message)
                                with open(str(local_fn), 'wb') as fp:
                                    ftps.retrbinary('RETR {}'.format(remotefile), fp.write)
                            # TIME.sleep(0.1)
                    ftps.quit()
                    ftps.close()
                    message = "Os arquivos foram atualizados e a conexão FTP foi encerrada"
                    atualizaStatusBar(message, "blue")
                    populateListView()
                except:
                    message = "Não foi possível realizar a conexão {} : {}".format(contextcommtype, contextlink)
                    # print(message)
                    atualizaStatusBar(message, "red")
            else:
                message = 'Iniciando a conexão SCP'
                atualizaStatusBar(message, "orange")
                try:
                    ssh = createSSHClient(contextlink, 22, contextuser, getDecodedPass(contextpass, 6))
                    sftp = paramiko.SFTPClient.from_transport(ssh.get_transport())
                    # remotedir = "./GNSS/data/UTCr/{}/CGGTTS".format(labname)
                    # print('Conexão SCP realizada')
                    remotedir = "/home/{username}/data/UTCr/{lab}/{rxid}/CGGTTS".format(username=contextuser,
                                                                                        lab=labname, rxid=contextrxid)
                    # print(f'remotedir = {remotedir}')
                    listOfRemotefiles = sftp.listdir(remotedir)
                    sortedListOfRemotefiles = np.sort(listOfRemotefiles)
                    # print("sortedListOfRemotefiles = {}".format(sortedListOfRemotefiles))
                    # Fecha o SFTP
                    sftp.close()
                    # Cria o cliente SCP com base no transporte SSH
                    scp = SCPClient(ssh.get_transport())
                    # Busca o caminho dinâmico de contexto
                    self.localdynpath = context.getDynrootCGGTTS()
                    # Compara a existência de arquivos locais com o repositório de contexto
                    for path, subdirs, localfiles in os.walk(self.localdynpath):
                        # print(sorted(localfiles)[-1])
                        for remotefile in sortedListOfRemotefiles:

                            filedate = getDateFromCggttsFileName(contextprefix, remotefile)

                            if (remotefile in localfiles) and (filedate < datetodownload):
                                message = "O arquivo '{}' já tem uma versão local".format(remotefile)
                                atualizaStatusBar(message, "orange")
                            else:
                                remote_fn = str(os.path.join(remotedir, os.path.basename(remotefile))).replace('\\',
                                                                                                               '/')
                                message = "Iniciando download do arquivo: {}".format(remote_fn)
                                atualizaStatusBar(message, "orange")
                                localfilename = remotefile
                                local_fn = str(
                                    os.path.join(self.localdynpath, os.path.basename(localfilename))).replace('\\', '/')
                                scp.get(remote_fn, local_fn, recursive=True)
                                TIME.sleep(0.01)
                    scp.close()
                    ssh.close()
                    message = "Os arquivos foram atualizados e a conexão SCP foi encerrada"
                    atualizaStatusBar(message, "blue")
                    populateListView()
                except:
                    message = "Não foi possível realizar a conexão {} : {}".format(contextcommtype, contextlink)
                    print(message)
                    self.statusbar.setStyleSheet("QStatusBar {background-color: red; color: white}")
                    atualizaStatusBar(message, "red")

        def resetCalendar():
            date = QDate.currentDate()
            self.calendarWidget.setSelectedDate(date)

        def populateListView():
            # removeprocessinggraphs(0)
            resetCalendar()
            self.tableView = getEmbededObjet(self, QTableView, 'tableViewBase')
            # Define o conteúdo do cabeçalho da tabela
            self.tablemodel.clear()
            self.tablemodel.setHorizontalHeaderLabels(["   Arquivos CGGTTS       ", "          Datas         "])
            # Busca no diretório 'rootCGGTTS' todos os aquivos CGGTTS
            contextpath = getContextRootForCGGTTS().getDynrootCGGTTS()
            for path, subdirs, files in os.walk(contextpath):
                # print(files)
                for name in files:
                    rowPosition = self.tablemodel.rowCount()
                    self.tablemodel.insertRow(rowPosition)
                    item0 = QtGui.QStandardItem(str(name))
                    item0.setTextAlignment(Qt.AlignmentFlag.AlignHCenter)
                    #
                    contextprefix = getContextRootForCGGTTS().getDynPrefix()
                    # print("contextpath: {}".format(contextpath))
                    #
                    respectivedate = getDateFromCggttsFileName(contextprefix, str(name))
                    item1 = QtGui.QStandardItem(respectivedate.__str__())
                    item1.setTextAlignment(Qt.AlignmentFlag.AlignHCenter)
                    mjdlist.append(int(''.join(list(filter(str.isdigit, name)))))
                    self.tablemodel.setItem(rowPosition, 0, item0)
                    self.tablemodel.setItem(rowPosition, 1, item1)
            # Determina o estilo da fonte
            self.tableView.setFont(QtGui.QFont('Arial', 9, QFont.Weight.DemiBold))
            # Temporarily set MultiSelection
            self.tableView.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            # Seta o modelo de dados de tableView
            self.tableView.setModel(self.tablemodel)
            # tableviewdynadj deve ser chamado após self.update
            tableviewdynadj()

            inicializaView()

        mjdlist = []

        # Define o modelo de dados para preencher a tabela
        self.tablemodel = QtGui.QStandardItemModel(self)

        # Conecta o sinal 'clicked' em calendarWidget com o método fromCalendar
        # Obs: O signal clicked envia como parâmetro as variáveis "const QDate &date"
        self.calendarWidget.clicked.connect(fromCalendar)

        # Conecta o evento 'clicked' em tableView com o método evento
        self.tableView.clicked.connect(eventolista)
        # Conecta o evento 'currentChanged' em qtabwidget com o método tabevento
        self.qtabwidget.currentChanged.connect(tabevento)

        def tableviewdynadj():
            # Configura a política de ajuste dinâmico
            self.tableView.resizeColumnsToContents()
            self.tableView.resizeRowsToContents()
            self.tableView.setSizeAdjustPolicy(QAbstractScrollArea.SizeAdjustPolicy.AdjustToContents)
            self.tableView.sortByColumn(0, Qt.SortOrder.DescendingOrder)
            # self.tableView.update(0)
            QtCore.QCoreApplication.processEvents()

        def xmltexto(t):
            return t.get('labname')

        def loadClientProfile():
            combolab = self.comboBox.currentText()
            setContextRootForCGGTTS(combolab)
            contextprefix = getContextRootForCGGTTS().getDynPrefix()
            self.btnAtualiza.setText(
                "Atualiza arquivos CGGTTS | {} | {}".format(self.comboBox.currentText(), contextprefix))
            populateListView()

        self.comboBox = getEmbededObjet(self, QComboBox, 'comboBox')
        # A lista de clientes deve ser obtida de clientprofiles.xml onde os perfis dos clientes ficam armazenados
        xpr = xmlprofilesroot.findall(".//profile[@labname]")

        # listaClientes = list(map(xmltexto, tuple(xpr)))
        listaClientes = map(xmltexto, tuple(xpr))
        # print(tuple(listaClientes))
        listaClientesForSubsets = list(map(xmltexto, xpr))

        # print(listaClientesForSubsets)

        def findsubsets(s, n):
            arr = []
            arrx = list(itertools.combinations(s, n))
            for itemx in arrx:
                arr.append("{} - {}".format(str(itemx[0]), str(itemx[1])))
            return arr

        nono = findsubsets(listaClientesForSubsets, 2)
        # print(nono)

        # creating a line edit
        edit = QLineEdit(self)
        # setting line edit
        self.comboBox.setLineEdit(edit)
        line_edit = self.comboBox.lineEdit()
        line_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Populate the combobox
        # self.comboBox.addItems(nono)
        self.comboBox.addItems(listaClientes)

        self.comboBox.activated.connect(loadClientProfile)
        # populateListView()
        self.btnAtualiza = getEmbededObjet(self, QPushButton, 'pushButtonActualiza')
        self.btnAtualiza.clicked.connect(atualizaCGGTTSFiles)

        loadClientProfile()
        # Inicializa a visualização emulando o método eventolista
        inicializaView()

        ################################################################################################################

    def applyLocalFreqCorr(self):
        respvalue, success = self.scheduledValue, False
        print("Aplicando o valor de correção  = {}".format(self.scheduledValue))
        try:
            respvalue, success = self.queryInstrument("FREQ {}".format(self.scheduledValue))
            respvalue, success = self.queryInstrument("FREQ?")
        except BaseException as bex:
            pass

    def defineEstrategCorr(self, est):

        print(f"est = {est}")
        self.estrategCorr = est

        if est == 2:
            self.pushButtonEst.setEnabled(True)
            self.pushButtonEst.setStyleSheet("background-color: rgb(255, 170, 0);")
        else:
            if est == 0:
                current_datetime = Time(datetime.now())
                # self.getUpdatedTimerSchedule(current_datetime)
            self.pushButtonEst.setEnabled(False)
            self.pushButtonEst.setStyleSheet("background-color: rgb(128, 128, 128);")

    def updateHROGID(self):
        ident, sucess = self.queryInstrument('ID?')

        if sucess:
            self.labelEquipIdent.setText("{}".format(str(ident)))
        else:
            self.labelEquipIdent.setText('----')

    def updateInfoInternalTemp(self):
        temper, sucess = self.queryInstrument('TEMP?')
        if sucess:
            self.labelLabTemp.setText(str(temper))
        else:
            self.labelLabTemp.setText('---- ºC')

        threading.Timer(0.5, self.updateInfoInternalTemp).start()
        QtCore.QCoreApplication.processEvents()

    def checkIfComPorts(self):
        portaSEL = {'tokenport': False}
        portslist = deque(serial.tools.list_ports.comports())
        print(f"portslist = {portslist}")
        for porta in portslist:
            idx = ""
            nomePorta = porta.device
            ser.port = nomePorta
            ser.baudrate = 9600
            ser.parity = serial.PARITY_NONE
            ser.stopbits = serial.STOPBITS_ONE
            ser.bytesize = serial.EIGHTBITS
            ser.timeout = 0.1
            ser.write_timeout = 0.1

            if not ser.is_open:
                print("\nTestando a conexão com o HROG-10 na porta: {}".format(ser.portstr))
                try:
                    ser.open()
                    print("A porta [ {} ] foi aberta".format(nomePorta))
                    tokenopenport = True
                except serial.SerialException as ex:
                    tokenopenport = False
                    print("Não foi possível abrir a porta: {}".format(nomePorta))
                    pass

                if tokenopenport:
                    try:
                        idx, se = self.queryInstrument('ID')
                        if se and ("HROG" in idx):
                            print("Porta Selecionada: {}".format(nomePorta))
                            portaSEL['id'] = idx
                            portaSEL['tokenport'] = True
                            portaSEL['nomePorta'] = nomePorta
                            self.comport = ser
                            return portaSEL
                    except serial.SerialException as ex:
                        print("Não foi possível obter o ID na porta: {}".format(nomePorta))
                        ser.close()
                        print("A porta [ {} ] foi fechada\n".format(nomePorta))
                        portaSEL['tokenport'] = False
                        pass
        return portaSEL

    def queryInstrument(self, gc):
        tokensuccess = False
        porta = self.comport
        query = None
        if porta is not None:
            if not porta.is_open:
                porta.open()
            sio = io.TextIOWrapper(io.BufferedRWPair(porta, porta))
            sio.write("{}\n".format(gc))
            # it is buffering. required to get the data out *now*
            sio.flush()
            result = sio.readlines()
            # print(result)
            tamresp = len(result)
            if tamresp > 0:
                query = result[tamresp - 2].replace(gc, '').replace('\n', '')
                tokensuccess = True
            # print(query)
        return query, tokensuccess

    def atualizaAlarmeMonitor(self, alarmeID, inicia):
        label = " "
        for chave in chaves:
            try:
                label = getEmbededObjet(self, QLabel, str("label_{}").format(chave))
                time.sleep(0.05)
                if chave in alarmeID:
                    label.setStyleSheet("background-color: rgb(255, 0, 0);")
                else:
                    if inicia:
                        label.setStyleSheet("background-color: rgb(255, 255, 255);")
                    else:
                        label.setStyleSheet("background-color: rgb(128, 255, 128);")
            except BaseException as bex:
                print(bex)

    def atualizaSteeringDisplay(self, tipo, freqcorr, datetimeparam):
        freqcorr = Quantity(freqcorr, 'Hz')
        freqcorrsplit = str(freqcorr).split(" ")
        # print("freqcorrsplit = {}".format(freqcorrsplit))
        # print("datetimeparam = {}".format(type(datetimeparam)))
        if tipo == 'op':
            self.sevenSEGMENTSFREQCORROP.display(freqcorrsplit[0])
            self.labelUNITFREQCORROP.setText(freqcorrsplit[1])
            self.dateTimeEditOP.setDisplayFormat("[ HH:mm:ss ] dd/MM/yyyy")
            self.dateTimeEditOP.setDateTime(datetimeparam)
        elif tipo == 'ag':
            self.sevenSEGMENTSFREQCORRAG.display(freqcorrsplit[0])
            self.labelUNITFREQCORRAG.setText(freqcorrsplit[1])
            self.dateTimeEditAG.setDisplayFormat("[ HH:mm:ss ] dd/MM/yyyy")
            self.dateTimeEditAG.setDateTime(datetimeparam)

        QtCore.QCoreApplication.processEvents()

    def run(self):
        try:
            while not self.stopped.wait(2):
                updateScheduleConfig()
        except KeyboardInterrupt as e:
            print(e)
            # self.setLogInfo(f"Aplicação encerrada!\n{e}")

    def closeEvent(self, close):
        stopFlag.set()
        self._stop_event.set()
        if close:
            sys.exit(0)

        ################################################################################################################

    def getChildrenObjectUI(self, objtype, chave):
        return list(self.findChildren(objtype, chave))[0]


StyleSheet = '''
QMainWindow {
    border: 1px solid blue;
    font-weight:bold
}
QMenuBar {
    background-color: #F0F0F0;
    color: #000000;
    border: 1px solid #000;
    font-weight:bold
}
QMenuBar::item {
    background-color: rgb(49,49,49);
    color: rgb(255,255,255)
}
QMenuBar::item::selected {
    background-color: rgb(30,30,30)
}
QTabWidget {
    background-color: #F0F0F0;
    border: 1px solid blue;
    border-radius: 20px
}
QTabWidget::pane {
    border: 1px solid #31363B;
    padding: 2px;
    margin:  0px
}
QTableView {
    selection-background-color: #0088cc;
}
QTabBar {
    border: 0px solid #31363B;
    color: #152464
}
QTabBar::tab:top:selected {
    background-color: #0066cc;
    color: white
}
QCalendarWidget{
    border: 2px solid black;
    background-color: rgb(255,255,255)
}
QComboBox {
    border: 1px solid black;
}
QGroupBox {
    border: 2px solid gray;
    border-radius: 4px;
    margin-top: 16px
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 3px 0 3px
}
'''
if __name__ == '__main__':
    # os.environ['PYSIDE_DESIGNER_PLUGINS'] = "."
    # QPyDesignerCustomWidgetCollection.registerCustomWidget(QWidget, module="formHROGWidget")
    # QtCore.QCoreApplication.setAttribute(QtCore.Qt.ApplicationAttribute.AA_EnableHighDpiScaling, True)
    QtCore.QCoreApplication.setAttribute(QtCore.Qt.ApplicationAttribute.AA_Use96Dpi, True)
    # QtCore.QCoreApplication.setAttribute( QtCore.Qt.ApplicationAttribute.AA_PluginApplication)
    QtCore.QCoreApplication.setAttribute(QtCore.Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    QtCore.QCoreApplication.setAttribute(QtCore.Qt.ApplicationAttribute.AA_ForceRasterWidgets)
    QtCore.QCoreApplication.setAttribute(QtCore.Qt.ApplicationAttribute.AA_NativeWindows)
    app = QApplication(sys.argv)
    QPyDesignerCustomWidgetCollection.instance()
    styles = ["Plastique", "Cleanlooks", "CDE", "Motif", "GTK+"]
    app.setStyle(QtWidgets.QStyleFactory.create(styles[-1]))
    app.setStyleSheet(StyleSheet)
    # app.setFont(QtGui.QFont("Arial", 11, QtGui.QFont.Bold))
    app_icon = QtGui.QIcon()
    app_icon.addFile('gui/icons/inmetro.ico', QtCore.QSize(256, 256))
    app.setWindowIcon(app_icon)
    rect = QRect(100, 100, 1280, 720)
    stopFlag = threading.Event()
    window = UserInterfaceSteer(stopFlag)
    window.setGeometry(rect)
    window.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)
    # print("lastvalue = {}".format(dir(UserInterfaceDmtic)))
    window.show()
    app.exec()

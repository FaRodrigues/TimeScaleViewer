# This Python file uses the following encoding: utf-8
# Autor: Fernando Alves Rodrigues (Dimci/Dmtic)

import math
import os
from collections import deque
import random
import serial.tools.list_ports  # pySerial
import serial  # pySerial
import io
import itertools
import numpy as np
from PySide6 import QtCore, QtWidgets
from PySide6.QtCore import QFile, QDate, QSize, Qt, QTime, QDateTime, QRect
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import QWidget, QLCDNumber, QLabel, QDateTimeEdit, QSizePolicy, QComboBox, QPushButton, QLineEdit
from quantiphy import Quantity
from threading import Thread, Event
from datetime import datetime as dtime
from datetime import timedelta
import time as timenative
import paho.mqtt.client as mqtt
from astropy.time import Time
import json

broker = 'broker.emqx.io'
# broker = '3.82.39.163'
port = 1883
topicag = "freqcorrection/stateag"
topicop = "freqcorrection/stateop"

# username = 'emqx'
# password = 'public'

global tokenopenport

class MQTTClient(mqtt.Client, Thread):
    def __init__(self, clientname, **kwargs):
        Thread.__init__(self)
        super(MQTTClient, self).__init__(clientname, **kwargs)
        self.last_pub_time = timenative.time()
        self.topic_ack = []
        self.run_flag = True
        self.subscribe_flag = False
        self.bad_connection_flag = False
        self.connected_flag = True
        self.disconnect_flag = False
        self.disconnect_time = 0.0
        self.pub_msg_count = 0
        self.devices = []

    def connect_mqtt(self):
        def on_connect(client, userdata, flags, rc):
            if rc == 0:
                print("Conectado ao Broker MQTT: {}!".format(broker))
            else:
                print("Falha em conectar, código de retorno %d\n", rc)

        try:
            self.on_connect = on_connect
            self.connect(broker, port)
        except:
            pass
        return self


def getIntPartOfFracTime(bfcin):
    fracout, intNumout = math.modf(bfcin)
    bfcout = fracout * 60
    return bfcout, intNumout


def getDateTimeFromNow():
    t1 = Time(dtime.now())
    stringdate = Time(t1.to_value('iso'), out_subfmt='date_hms').iso
    dt = dtime.fromisoformat(stringdate)
    qdatetime = QtCore.QDateTime(dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second)
    return qdatetime


def getDateFromMJD(MJD):
    tmjd = Time(MJD, format='mjd')
    stringdate = Time(tmjd.to_value('iso'), out_subfmt='date').iso
    return QDate.fromString(str(stringdate), "yyyy-MM-dd")


def getDateTimeFromMJDFrac(MJD):
    # print("MJD = {}".format(MJD))
    tmjd = Time(MJD, format='mjd')
    stringdate = Time(tmjd.to_value('iso'), out_subfmt='date_hms').iso
    dt = dtime.fromisoformat(stringdate)
    qdatetime = QtCore.QDateTime(dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second)
    return qdatetime


def getMJDFracFromTime(delta):
    t0 = timedelta(hours=delta)
    t1 = Time(dtime.now() + t0)
    tmjd = t1.to_value('mjd', subfmt='float')
    # print(tmjd)
    return tmjd


def getMJDFracFromDateTime(dt):
    t1 = Time(dt.toPython())
    tmjd = t1.to_value('mjd', subfmt='float')
    return tmjd


def findsubsets(s, n):
    return list(itertools.combinations(s, n))


def publish(client, msg_dict):
    send_msg = msg_dict
    msg = f"mensagem: {send_msg}"
    result = client.publish(topicop, payload=json.dumps(send_msg), qos=0, retain=False)
    status = result[0]
    if status == 0:
        pass
        print(f"Enviando `{msg}` para o tópico `{topicop}`")
    else:
        print(f"Falha ao enviar mensagem para o tópico {topicop}")


def getEmbededObjet(self, tipo, nome):
    search = self.findChildren(tipo, nome)
    objeto = search[0]
    # print("objeto = {}".format(objeto))
    return objeto


def getContextMJD():
    fracout, intNumout = math.modf(getMJDFracFromTime(0))
    contextmjdlocal = int(intNumout)
    return contextmjdlocal


def getSubDividedDayTime(nowqdtime, localbasetime, instep):
    nowdate = nowqdtime.date()
    sddt = []
    starttime = QTime(00, 00)
    stoptime = QTime(23, 59)
    deltastart = starttime.secsTo(starttime)
    deltastop = starttime.secsTo(stoptime)
    basedelta = localbasetime.secsTo(stoptime)
    if instep > 0:
        try:
            outstep = round((deltastop - deltastart) / instep)
            resp1 = list(range(round(deltastart), round(deltastop), outstep))
            # print(resp1)
            for h in resp1:
                dayslice = round(h + outstep - basedelta)
                if dayslice >= 0:
                    timelocal = starttime.addSecs(dayslice)
                    qdt = QDateTime()
                    qdt.setDate(nowdate)
                    qdt.setTime(timelocal)
                    sddt.append(qdt)
        except:
            print("Não foi possível gerar a lista de horários")
    return sddt


class HROGWidget(QWidget, Thread):
    def __init__(self, event, *args, **kwargs):
        super(HROGWidget, self).__init__()
        # QWidget.__init__(self)
        Thread.__init__(self)
        self.optionsAlarm = None
        self.stopped = event

        # def resizeEvent(self, event):
        #     tabgeo = event.size()
        #     self.resize(QSize(tabgeo.width(), tabgeo.height()))
        #     # self.formHROGWidget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        #     QtCore.QCoreApplication.processEvents()

        self.basetimetoschedule = QTime(22, 20)
        self.contextmjd = getContextMJD()

        print("self.contextmjd = {}".format(self.contextmjd))

        self.qdtnow = getDateTimeFromNow()
        self.scheduledValue = None
        self.lastscheduledDatetime = 0

        self.listOfFixedTime = getSubDividedDayTime(self.qdtnow, QTime(22, 20), 4)
        print(f"{self.listOfFixedTime}")

        self.nextScheduledDatetime = self.qdtnow
        self.datetimeToDoTask = self.qdtnow

        self.activeFreqOffset = 0
        self.estrategCorr = 0
        self.clientebase = None
        self.client = None  # Define MQTT Client

        loader = QUiLoader()
        guipath = os.path.abspath(os.path.join(".", "gui", "ui", "formHROG.ui"))
        # print("guipath = {}".format(guipath))
        file = QFile(guipath)
        file.open(QFile.ReadOnly)
        self.ui = loader.load(file, self)
        file.close()

        self.formHROGWidget = getEmbededObjet(self, QWidget, "formHROGWidget")
        self.setGeometry(self.ui.geometry())

        # self.formHROGWidget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.ser = serial.Serial()
        self.portaSEL = deque([])

        # global tokenopenport
        # global alarmeID, listaresp, alarmePOS

        self.tokenHROGPORT = False  # Indica se uma porta serial está ativa
        self.tokenCORREXEC = False  # Indica se uma correção de frequência foi realizada
        self.deadTime = 0

        # self.evaluateSchedule = QtCore.pyqtSignal(object)

        self.optoken = False
        self.opvalue = 0
        self.opalarm = 0
        self.opid = "HROG"
        self.opport = "COM"
        self.optemp = 22
        self.ophum = 60
        self.optime = None
        self.opwindow = self.lastscheduledDatetime

        self.stateDictAcceptedAG = {
            "agtoken": self.optoken,
            "agvalue": self.opvalue,
            "agalarm": self.opalarm,
            "agid": self.opid,
            "agport": self.opport,
            "agtemp": self.optemp,
            "aghum": self.ophum,
            "agtime": self.optime
        }

        self.stateDictProposedAG = {
            "agtoken": self.optoken,
            "agvalue": self.opvalue,
            "agalarm": self.opalarm,
            "agid": self.opid,
            "agport": self.opport,
            "agtemp": self.optemp,
            "aghum": self.ophum,
            "agtime": self.optime
        }

        self.stateDictOP = {
            "optoken": self.optoken,
            "opvalue": self.opvalue,
            "opalarm": self.opalarm,
            "opid": self.opid,
            "opport": self.opport,
            "optemp": self.optemp,
            "ophum": self.ophum,
            "optime": self.optime,
            "opwindow": self.opwindow
        }

        # Opções de alarme descritas no manual do equipamento e definidas no código na forma de um dict
        self.optionsAlarmDict = {
            1: "External reference error",
            2: "Internal oscillator error",
            4: "PLL Lock error",
            8: "Tuning voltage error",
            16: "Invalid parameter",
            32: "Invalid command",
            64: "DC Backup Loss",
            128: "AC Power Loss"
        }

        self.chaves = list(self.optionsAlarmDict.keys())
        self.valores = list(self.optionsAlarmDict.values())
        self.atualizaAlarmeMonitor([], True)

        self.groupBox3Text = getEmbededObjet(self, QLabel, "labelEquipIdent")
        self.groupBox4Text = getEmbededObjet(self, QLabel, "labelPortIdent")

        self.labelUNITFREQCORROP = getEmbededObjet(self, QLabel, "labelNumberFREQ")
        self.sevenSEGMENTSERRO = getEmbededObjet(self, QLCDNumber, "lcdNumberERRO")
        self.sevenSEGMENTSFREQCORROP = getEmbededObjet(self, QLCDNumber, "lcdNumberFREQ")

        self.dateTimeEditOP = getEmbededObjet(self, QDateTimeEdit, "dateTimeEdit")

        self.sevenSEGMENTSFREQCORRAG = getEmbededObjet(self, QLCDNumber, "lcdNumberFREQAG")
        self.labelUNITFREQCORRAG = getEmbededObjet(self, QLabel, "labelNumberFREQAG")
        self.dateTimeEditAG = getEmbededObjet(self, QDateTimeEdit, "dateTimeEditAG")

        self.labelEquipIdent = getEmbededObjet(self, QLabel, "labelEquipIdent")
        self.labelPortIdent = getEmbededObjet(self, QLabel, "labelPortIdent")

        self.labelLabTemp = getEmbededObjet(self, QLabel, "labelLabTemp")
        self.labelLabHum = getEmbededObjet(self, QLabel, "labelLabHum")

        self.pushButtonEst = getEmbededObjet(self, QPushButton, "pushButtonEst")
        self.pushButtonEst.clicked.connect(self.applyLocalFreqCorr)

        listaEstrategCorr = {1: "Horário Fixo", 2: "Intervalo Fixo", 3: "Manual"}
        self.comboBoxEst = getEmbededObjet(self, QComboBox, "comboBoxEst")
        self.comboBoxEst.addItems(listaEstrategCorr.values())
        self.comboBoxEst.activated.connect(self.defineEstrategCorr)
        # creating a line edit
        combolinedit = QLineEdit(self)
        # setting line edit
        self.comboBoxEst.setLineEdit(combolinedit)
        line_edit = self.comboBoxEst.lineEdit()
        line_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Atualiza a interface
        self.atualizaDisplayOP()
        self.displayErrorCodeForRemoteAG(0)
        self.getUpdatedTimerSchedule(self.qdtnow)

    def run(self):
        self.evaluateAGTaskForLocal(self.qdtnow, self.stateDictOP)
        while not self.stopped.wait(60):
            self.qdtnow = getDateTimeFromNow()
            self.evaluateAGTaskForLocal(self.qdtnow, self.stateDictOP)

    def applyLocalFreqCorr(self):
        respvalue, success = self.scheduledValue, False
        print("Aplicando o valor de correção  = {}".format(self.scheduledValue))
        try:
            respvalue, success = self.setTransactCommand("FREQ {}".format(self.scheduledValue), "FREQ?")
        except:
            pass

    def defineEstrategCorr(self, est):

        print(f"est = {est}")
        self.estrategCorr = est

        if est == 2:
            self.pushButtonEst.setEnabled(True)
            self.pushButtonEst.setStyleSheet("background-color: rgb(255, 170, 0);")
        else:
            if est == 0:
                datetimenow = getDateTimeFromNow()
                self.getUpdatedTimerSchedule(datetimenow)

            self.pushButtonEst.setEnabled(False)
            self.pushButtonEst.setStyleSheet("background-color: rgb(128, 128, 128);")

    def setCurrentMQTTClient(self, cl):
        self.client = cl

    def getCurrentMQTTClient(self):
        return self.client

    def on_message(self, client, userdata, msg):
        modeag = "ag"
        decodedmsg = msg.payload.decode()
        # mens = f"Received in widget `{decodedmsg}` from `{msg.topic}` topic {client} \n"
        # print(mens)
        dictrec = json.loads(decodedmsg)
        for di in dictrec:
            self.stateDictProposedAG['{}'.format(di)] = dictrec['{}'.format(di)]
        # print("stateDictProposedAG = {}".format(self.stateDictProposedAG))

        datetimenow = getDateTimeFromNow()

        self.getUpdatedTimerSchedule(datetimenow)

        # Recupera a unidade uHz
        self.scheduledValue = np.double(self.stateDictProposedAG['{}value'.format(modeag)]) / 1000000
        token = self.stateDictProposedAG['{}token'.format(modeag)]
        preconditions = (token == True)
        if preconditions:
            self.evaluateAGTaskForLocal(datetimenow, self.stateDictProposedAG)

    def initiateMQTT(self):
        if self.getCurrentMQTTClient() is None:
            CLIENT_ID = f'publish-{random.randint(0, 1000)}'
            print("CLIENT_ID = {}".format(CLIENT_ID))
            self.clientebase = MQTTClient(CLIENT_ID)
            self.clientebase.start()
            try:
                self.client = self.clientebase.connect_mqtt()
                self.setCurrentMQTTClient(self.client)
                self.client.subscribe(topicag)
                print('A conexão MQTT está inscrita como [ ASSINANTE ] no tópico {}'.format(topicag))
                self.client.on_message = self.on_message
                self.client.loop_start()
                print('A Thread MQTT está {}'.format(self.clientebase.is_alive()))
            except:
                pass
        else:
            if self.clientebase.is_connected():
                print('A conexão MQTT está ativa! A Thread MQTT está {} e será reiniciada'.format(
                    self.clientebase.is_alive()))
                self.client.on_message = self.on_message
                self.client.loop_start()
                print('A Thread MQTT está {}'.format(self.clientebase.is_alive()))

    def setTransactCommand(self, commandToSet, commandToGet):
        ctg = " "
        if not (self.ser.isOpen()):
            print("Abrindo a porta: {}".format(self.ser.portstr))
            self.ser.open()
        sio = io.TextIOWrapper(io.BufferedRWPair(self.ser, self.ser))
        sio.write("{}\n\n".format(commandToSet))
        timenative.sleep(0.2)
        ctg, success = self.queryInstrument(commandToGet)
        return ctg, success

    def getUpdatedTimerSchedule(self, now):
        difftimetofinal = now.time().secsTo(self.basetimetoschedule)
        fimdodiatoken = difftimetofinal < 0
        print("fimdodiatoken = {}\ndifftimetofinal = {}".format(fimdodiatoken, difftimetofinal))
        verifiedcontextmjd = getContextMJD()

        if verifiedcontextmjd > self.contextmjd or fimdodiatoken:
            self.contextmjd = verifiedcontextmjd
            self.listOfFixedTime = getSubDividedDayTime(now.addDays(1), self.basetimetoschedule, 4)
            print("Gerando nova lista de horários para agendamento.\n{}".format(self.listOfFixedTime))

        for qdtlocal in self.listOfFixedTime:
            # print("qdtlocal.secsTo(now) = {}".format(qdtlocal.secsTo(now)))
            if qdtlocal.secsTo(now) <= 0:
                self.datetimeToDoTask = qdtlocal
                self.nextScheduledDatetime = qdtlocal
                self.atualizaDisplayAG(False)
                return qdtlocal

    def evaluateAGTaskForLocal(self, dtnow, dictrec):
        global agtime, clientop
        modeag = 'ag'
        modeop = 'op'

        self.atualizaDisplayOP()
        novahoraagenda = self.getUpdatedTimerSchedule(dtnow)
        print("novahoraagenda = {}".format(novahoraagenda))
        print("datetimeToDoTask = {}".format(self.datetimeToDoTask))

        respvalue, success = self.activeFreqOffset, False
        operrcode = self.stateDictOP['{}alarm'.format(modeop)]

        self.stateDictOP['{}time'.format(modeop)] = getMJDFracFromDateTime(dtnow)
        # A janela opwindow é configurada com o valor MJD de self.scheduledDatetime
        self.stateDictOP['{}window'.format(modeop)] = getMJDFracFromDateTime(self.nextScheduledDatetime)

        try:
            clientop = self.getCurrentMQTTClient()
            # print("clientop = {}".format(clientop))
            print("self.stateDictOP3 = {}".format(self.stateDictOP))
            publish(clientop, self.stateDictOP)
            clientop.loop_start()
        except:
            print("Não foi possível abrir a conexão MQTT")
            pass

        success = False

        try:
            if dtnow.secsTo(self.datetimeToDoTask) < 600:  # Janela de 10 minutos
                operrcode = self.stateDictOP['{}alarm'.format(modeop)]
                respvalue, success = self.scheduledValue, False
                try:
                    print("Configurando o offset de frequência | scheduledValue = {}, {}".format(self.scheduledValue,
                                                                                                 success))
                    respvalue, success = self.setTransactCommand("FREQ {}".format(self.scheduledValue), "FREQ?")
                    pass
                except:
                    pass
                # Remover #Remover
                # success = True  # Remover
                # print("respvalue = {}, {}".format(respvalue, success))
                if success:
                    self.tokenCORREXEC = True
                    self.activeFreqOffset = respvalue
                    # self.deadTime = 1  # in hours
                    agtime = getMJDFracFromTime(0)
                    print("agtime = {}".format(agtime))
                    # agtime = getMJDFracFromTime(self.deadTime)
                    # self.scheduledDatetime = getDateTimeFromMJDFrac(agtime)
                    # self.datetimeToDoTask = self.scheduledDatetime
                    self.lastscheduledDatetime = agtime
                    # Store the last time the scheduled freq off set was adjusted
                    self.stateDictOP['{}window'.format(modeop)] = agtime
                else:
                    self.deadTime = 0

                try:
                    operrcode = self.queryInstrument('*SRE')
                except:
                    pass

                self.stateDictOP['{}alarm'.format(modeop)] = operrcode
                self.stateDictOP['{}time'.format(modeop)] = agtime
                dictrec['{}time'.format(modeag)] = agtime
                self.stateDictOP['{}token'.format(modeop)] = success
                self.stateDictOP['{}value'.format(modeop)] = np.double(respvalue)

            self.atualizaDisplayAG(success)
            self.atualizaDisplayOPForRemoteMonitor(respvalue, self.nextScheduledDatetime)
            self.displayErrorCodeForRemoteAG(operrcode)
        except:
            pass

    def atualizaDisplayOP(self):
        freqcorr = self.activeFreqOffset
        # Query frequency offset
        if self.tokenHROGPORT == True:
            try:
                freqcorr = self.getHROGFreqOffSet()
            except:
                pass
        freqcorr = Quantity(freqcorr, 'Hz')
        freqcorrsplit = str(freqcorr).split(" ")
        # print("freqcorrsplit = {}".format(freqcorrsplit))
        self.sevenSEGMENTSFREQCORROP.display(freqcorrsplit[0])
        self.labelUNITFREQCORROP.setText(freqcorrsplit[1])
        datetimeOP = getDateTimeFromNow()  # self.getDateTimeFromMJDFrac(timestamp)
        self.dateTimeEditOP.setDisplayFormat("[ HH:mm ] dd/MM/yyyy")
        self.dateTimeEditOP.setDateTime(datetimeOP)

        usedport = self.stateDictOP['opport']

        try:
            try:
                idequip = self.queryInstrumentID()
                self.stateDictOP['opid'] = idequip
            except:
                idequip = self.stateDictOP['opid']

            self.labelEquipIdent.setText(self.stateDictOP['opid'])

            if len(list(self.portaSEL)) > 0:
                usedport = list(self.portaSEL)[0]

            self.stateDictOP['opport'] = usedport
            self.labelPortIdent.setText(self.stateDictOP['opport'])

            self.stateDictOP['optemp'] = self.optemp
            self.labelLabTemp.setText('{} ºC'.format(self.stateDictOP['optemp']))

            self.stateDictOP['ophum'] = self.ophum
            self.labelLabHum.setText('{} %'.format(self.stateDictOP['ophum']))

        except:
            pass

        QtCore.QCoreApplication.processEvents()

    def atualizaDisplayOPForRemoteMonitor(self, valor, timestamp):
        freqcorr = Quantity(valor, 'Hz')
        freqcorrsplit = str(freqcorr).split(" ")
        # print("freqcorrsplit = {}".format(freqcorrsplit))
        self.sevenSEGMENTSFREQCORROP.display(freqcorrsplit[0])
        self.labelUNITFREQCORROP.setText(freqcorrsplit[1])
        datetimeOP = getDateTimeFromMJDFrac(timestamp)
        self.dateTimeEditOP.setDisplayFormat("[ HH:mm ] dd/MM/yyyy")
        self.dateTimeEditOP.setDateTime(datetimeOP)
        QtCore.QCoreApplication.processEvents()

    def atualizaDisplayAG(self, se):
        # print("se = {} | dictrec = {}".format(se, dictrec))
        print("self.stateDictProposedAG['agtoken'] = {}".format(self.stateDictProposedAG['agtoken']))
        # if self.stateDictProposedAG['agtoken']:
        datetimeAG = self.nextScheduledDatetime
        print("datetimeAG = {}".format(datetimeAG))
        self.dateTimeEditAG.setDisplayFormat("[ HH:mm ] dd/MM/yyyy")
        self.dateTimeEditAG.setDateTime(datetimeAG)
        self.sevenSEGMENTSFREQCORRAG.display(self.stateDictProposedAG['agvalue'])
        self.labelUNITFREQCORRAG.setText('uHz')
        #
        # if se == True:
        #     cor = "rgb(255,255,255)"
        # else:
        #     cor = "rgb(255,170,0)"
        #
        # stylelocal = ("background-color: {};")
        # style = stylelocal.format(cor)
        # self.dateTimeEditAG.setStyleSheet(style)
        # time.sleep(0.05)
        # self.sevenSEGMENTSFREQCORRAG.setStyleSheet(style)
        # time.sleep(0.05)
        # self.labelUNITFREQCORRAG.setStyleSheet(style)
        # else:
        # self.dateTimeEditAG.setEnabled(False)
        QtCore.QCoreApplication.processEvents()

    def getHROGFreqOffSet(self):
        rawfreqcorr, se = self.queryInstrument('FREQ?')
        freqcorr = Quantity(rawfreqcorr, 'Hz')
        return freqcorr

    def showInterfaceValues(self):
        arrmessage = ["A interface não pode ser atualizada!", "red"]
        try:
            self.groupBox3Text.setText(self.queryInstrumentID())
            self.groupBox4Text.setText(self.getComPort().portstr)
            self.atualizaDisplayOP()
            # Atualiza o display da correção de frequência agendada
            # self.getFreqCorrData()
            arrmessage = ["A interface foi atualizada!", "green"]
        except:
            pass

    def readCurrentFreqCorrData(self):
        rawfreqcorr = 0.000000000000
        if self.tokenHROGPORT == True:
            rawfreqcorr, se = self.queryInstrument('FREQ?')
        else:
            pass
        freqcorr = Quantity(rawfreqcorr, 'Hz')
        freqcorrsplit = str(freqcorr).split(" ")
        # print("freqcorrsplit = {}".format(freqcorrsplit))
        self.sevenSEGMENTSFREQCORROP.display(freqcorrsplit[0])
        self.labelUNITFREQCORROP.setText(freqcorrsplit[1])
        self.dateTimeEditOP.setDisplayFormat("[ HH:mm ] dd/MM/yyyy")
        self.dateTimeEditOP.setDateTime(self.dateTimeEditOP.dateTimeFromText("[ 00:00 ] 01/01/2000"))
        # print("textFromDateTime = {}".format(self.dateTimeEdit.dateTime()))

    def getFreqCorrDataX(self):
        rawfreqcorr, se = 0, False
        try:
            rawfreqcorr, se = self.queryInstrument('FREQ?')
        except:
            pass
        freqcorr = Quantity(rawfreqcorr, 'Hz')
        freqcorrsplit = str(freqcorr).split(" ")
        # print("freqcorrsplit = {}".format(freqcorrsplit))
        self.sevenSEGMENTSFREQCORRAG.display(freqcorrsplit[0])
        self.labelUNITFREQCORRAG.setText(freqcorrsplit[1])
        self.dateTimeEditAG.setDisplayFormat("[ HH:mm ] dd/MM/yyyy")
        self.dateTimeEditAG.setDateTime(self.dateTimeEditAG.dateTimeFromText("[ 00:00 ] 01/01/2000"))
        # print("textFromDateTime = {}".format(self.dateTimeEditAG.dateTime()))

    def displayErrorCodeForRemoteAG(self, err):
        arrmessage = ["Código de erro não encontrado!", "red"]
        errcode = err
        try:
            errcode = self.queryInstrument('*SRE')
            self.sevenSEGMENTSERRO.display(errcode)
            self.returnListOfAlarmsByCode(int(errcode))
            arrmessage = ["Código de erro atualizado com sucesso!", "green"]
        except:
            pass
        return arrmessage

    def displayErrorCode(self):
        arrmessage = ["Código de erro não encontrado!", "red"]
        try:
            errcode, se = self.queryInstrument('*SRE')
            # errcode = 23
            self.sevenSEGMENTSERRO.display(errcode)
            errcodeDESCS = self.returnListOfAlarmsByCode(int(errcode))
            alarmeid = errcodeDESCS[0]
            self.atualizaAlarmeMonitor(alarmeid, False)
            arrmessage = ["Código de erro atualizado com sucesso!", "green"]
        except:
            pass
        return arrmessage

    def setTimerplotinterval(self, timerplotinterval):
        self.timerplotinterval = int(timerplotinterval)
        # self.ui.spinBox_timer.setValue(timerplotinterval)

    def getComPort(self):
        return self.ser

    def checkIfComPorts(self):
        self.tokenHROGPORT = False
        self.portaSEL = deque([])

        portslist = deque(serial.tools.list_ports.comports())
        for porta in portslist:
            idx = ""
            nomePorta = porta.device
            self.ser.port = nomePorta
            self.ser.baudrate = 9600
            self.ser.parity = serial.PARITY_NONE
            self.ser.stopbits = serial.STOPBITS_ONE
            self.ser.bytesize = serial.EIGHTBITS
            self.ser.timeout = 0.1
            self.ser.write_timeout = 0.1

            if not self.ser.isOpen():
                print("\nTestando a conexão com o HROG-10 na porta: {}".format(self.ser.portstr))
                try:
                    self.ser.open()
                    print("A porta [ {} ] foi aberta".format(nomePorta))
                    tokenopenport = True
                except:
                    tokenopenport = False
                    print("Não foi possível abrir a porta: {}".format(nomePorta))
                    pass

                if tokenopenport == True:
                    try:
                        idx = self.queryInstrumentID()
                        if "HROG" in idx:
                            print("Porta Selecionada: {}".format(nomePorta))
                            self.tokenHROGPORT = True
                            self.portaSEL.append(nomePorta)
                            return [self.tokenHROGPORT, list(self.portaSEL)]
                    except:
                        print("Não foi possível obter o ID na porta: {}".format(nomePorta))
                        self.ser.close()
                        print("A porta [ {} ] foi fechada\n".format(nomePorta))
                        self.tokenHROGPORT = False
                        pass

        return [self.tokenHROGPORT, list(self.portaSEL)]

    def queryInstrumentID(self):
        gc = "ID"
        if not (self.ser.isOpen()): self.ser.open()
        sio = io.TextIOWrapper(io.BufferedRWPair(self.ser, self.ser))
        sio.write("{}\n".format(gc))
        # it is buffering. required to get the data out *now*
        sio.flush()
        result = sio.readlines()
        # print(result[0])
        tamresp = len(result)
        if tamresp > 0:
            query = result[tamresp - 2].replace(gc, '').replace('\n', '')
        else:
            query = None
        return query

    def queryInstrument(self, gc):
        tokensuccess = False
        if not (self.ser.isOpen()):
            self.ser.open()
        sio = io.TextIOWrapper(io.BufferedRWPair(self.ser, self.ser))
        sio.write("{}\n".format(gc))
        # it is buffering. required to get the data out *now*
        sio.flush()
        result = sio.readlines()
        # print(result)
        tamresp = len(result)
        if tamresp > 0:
            query = result[tamresp - 2].replace(gc, '').replace('\n', '')
            tokensuccess = True
        else:
            query = " "
        # print(query)
        return query, tokensuccess

    def returnListOfAlarmsByCode(self, errcode):
        global alarmeID
        respostacheia = deque([])
        respostavazia = []

        for x in range(8):

            def getindexes(x):
                return self.chaves.index(x)

            def findsubsets(s, n):
                return list(itertools.combinations(s, n))

            # Gera subsets de optionsAlarm com tamanho 4
            subsetsresp = findsubsets(self.chaves, x)
            # print("subsetsresp = {}".format(subsetsresp))

            try:
                mapaiterativo = list(map(sum, subsetsresp))
                # print("mapaiterativo = {}".format(mapaiterativo))
                subsetsrespsummatch = list(mapaiterativo).index(errcode)
                # print("subsetsrespsummatch = {}".format(subsetsrespsummatch))
            except:
                subsetsrespsummatch = -1

            if (subsetsrespsummatch > -1):
                # print(subsetsrespsummatch)
                alarmeID = list(subsetsresp[subsetsrespsummatch])
                # print("alarmeID = {}".format(alarmeID))
                respostacheia.append(alarmeID)
                alarmePOS = list(map(getindexes, alarmeID))
                # print("alarmePOS = {}".format(alarmePOS))
                respostacheia.append(alarmePOS)
                listaresp = list(np.array(self.valores)[alarmePOS])
                # print("listaresp = {}".format(listaresp))
                respostacheia.append(listaresp)
                self.atualizaAlarmeMonitor(alarmeID, False)
                return respostacheia
        return respostavazia

    def indexListOfAlarmsByCode(self, errcode):
        # global alarmeID, listaresp, alarmePOS
        global listaresp, alarmeID, alarmePOS

        for x in range(8):

            def getindexes(item):
                return self.optionsAlarm.index(item)

            def getitembychave(ch):
                return self.chaves[ch]

            # Gera subsets de optionsAlarm com tamanho 4
            subsetsresp = findsubsets(self.optionsAlarm, x)
            # print(subsetsresp)
            try:
                subsetsrespsummatch = list(map(sum, subsetsresp)).index(errcode)
            except:
                subsetsrespsummatch = -1

            if subsetsrespsummatch > -1:
                # print(subsetsrespsummatch)
                alarmeID = list(subsetsresp[subsetsrespsummatch])
                alarmePOS = list(map(getindexes, alarmeID))
                listaresp = list(map(getitembychave, alarmePOS))
                self.atualizaAlarmeMonitor(alarmeID, False)
                # return
        return [listaresp, alarmeID, alarmePOS]

    def atualizaAlarmeMonitor(self, alarmeID, inicia):
        label = " "
        for chave in self.chaves:
            try:
                label = getEmbededObjet(self.ui, QLabel, str("label_{}").format(chave))
                timenative.sleep(0.05)
                if chave in alarmeID:
                    label.setStyleSheet("background-color: rgb(255, 0, 0);")
                else:
                    if inicia:
                        label.setStyleSheet("background-color: rgb(255, 255, 255);")
                    else:
                        label.setStyleSheet("background-color: rgb(128, 255, 128);")
            except:
                pass

    def inicializa(self):
        return self.ser

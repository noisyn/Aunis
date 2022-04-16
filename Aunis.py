# Copyright (c) 2022 Taner Esat <t.esat@fz-juelich.de>

import os
import sys
import time

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import QFile
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import QApplication, QMainWindow

from PyNanonis import NanonisInterface

class runScriptThread(QtCore.QThread):
    logSignal = QtCore.Signal(str, str)

    def __init__(self):
        super(runScriptThread, self).__init__()
        self.script = ''
        self.cancelScript = False
        self.nni = None

    def run(self):
        repeat_counter = 0
        repeat_startindex = 0
        repeat_loop = False
        script = self.script
        all_cmds = script.split('\n')
        index = 0
        while index < len(all_cmds) and self.cancelScript == False:
            cmdLine = all_cmds[index]
            if len(cmdLine) > 1:
                cmd = cmdLine.split(' ')
                cmdAlias = cmd[0]
                cmdArgs = cmd[1:]
                if cmdAlias == 'repeat':
                    repeat_counter = np.int(cmdArgs[0])
                    repeat_loop = True
                    repeat_startindex = index
                elif cmdAlias == 'end' and repeat_loop == True:
                    if repeat_counter == 0:
                        repeat_loop = False
                        repeat_startindex = 0
                    else:
                        repeat_counter -= 1
                        if repeat_counter > 0:
                            index = repeat_startindex
                else:
                    self.logSignal.emit('Request', cmdLine)
                    err, resp = self.nni.command(cmdAlias, cmdArgs)
                    if len(resp) > 0:
                        self.logSignal.emit('Response', str(resp)) 
                    print(cmdLine)      
            index += 1

class AunisGUI(QMainWindow):
    def __init__(self):
        super(AunisGUI, self).__init__()
        self.fileAunisIcon = 'GUI\\AunisIcon.svg'

        self.connected = False
        self.cancelScript = False
        self.threadScript = runScriptThread()
        self.threadScript.logSignal.connect(self.logCommand)

        self.log_folder = 'logs'
        self.log_date = time.strftime('%Y-%m-%d %H%M%S', time.localtime())

        self.setupUI()
        self.startUp()
    
    def setupUI(self):
        ui_file = QFile('GUI\\AunisGUI.ui')
        ui_file.open(QFile.ReadOnly)

        loader = QUiLoader()
        self.ui = loader.load(ui_file)
        self.ui.setWindowIcon(QtGui.QIcon(self.fileAunisIcon))
        app.aboutToQuit.connect(self.closeEvent)
        self.ui.show()
        
        # References to all required widgets
        # Status bar
        # self.statusBar = self.ui.statusbar
        self.menuSaveFile = self.ui.menuSaveFile
        self.menuLoadFile = self.ui.menuLoadFile
        self.menuAboutHelp = self.ui.menuAboutHelp
        self.menuManualHelp = self.ui.menuManualHelp
        self.menuSaveFile.triggered.connect(self.saveScript)
        self.menuLoadFile.triggered.connect(self.loadScript)
        self.menuAboutHelp.triggered.connect(self.aboutMessage)
        self.menuManualHelp.triggered.connect(self.openManual)

        self.status_Status = self.ui.status_Status
        self.status_Setpoint = self.ui.status_Setpoint
        self.status_Feedback = self.ui.status_Feedback
        self.status_Refresh = self.ui.status_Refresh
        self.status_Feedback.clicked.connect(self.switchFBOnOff)
        self.status_Refresh.clicked.connect(self.updateStatus)
        self.settings_IP = self.ui.settings_IP
        self.settings_Port = self.ui.settings_Port
        self.settings_Connect = self.ui.settings_Connect
        self.settings_Disconnect = self.ui.settings_Disconnect
        self.settings_Connect.clicked.connect(self.connect)
        self.settings_Disconnect.clicked.connect(self.disconnect)
        self.scripting_Script = self.ui.scripting_Script
        self.scripting_Run = self.ui.scripting_Run
        self.scripting_Stop = self.ui.scripting_Stop
        self.status_Log = self.ui.status_Log
        self.scripting_Run.clicked.connect(self.runScript)
        self.scripting_Stop.clicked.connect(self.stopScript)
        self.tipman_Yplus = self.ui.tipman_Yplus
        self.tipman_Yminus = self.ui.tipman_Yminus
        self.tipman_Xminus = self.ui.tipman_Xminus
        self.tipman_Xplus = self.ui.tipman_Xplus
        self.tipman_Zplus = self.ui.tipman_Zplus
        self.tipman_Zminus = self.ui.tipman_Zminus
        self.tipman_dx = self.ui.tipman_dx
        self.tipman_dy = self.ui.tipman_dy
        self.tipman_dz = self.ui.tipman_dz
        self.tipman_Yplus.clicked.connect(self.moveTipYplus)
        self.tipman_Yminus.clicked.connect(self.moveTipYminus)
        self.tipman_Xminus.clicked.connect(self.moveTipXminus)
        self.tipman_Xplus.clicked.connect(self.moveTipXplus)
        self.tipman_Zplus.clicked.connect(self.moveTipZplus)
        self.tipman_Zminus.clicked.connect(self.moveTipZminus)

    def startUp(self):
        self.nni = NanonisInterface()
        self.updateStatus()

    def connect(self):
        ip = self.settings_IP.text()
        port = np.int(self.settings_Port.text())
        self.connected = self.nni.connect(ip, port)
        self.updateStatus()
    
    def disconnect(self):
        self.connected = self.nni.disconnect()
        self.updateStatus()
    
    def updateStatus(self):
        if self.connected:
            self.status_Status.setText('Connected')
            self.status_Status.setStyleSheet('color: rgb(0,0,0); background-color: rgb(51,209,122);')
            self.getSetpoint()
            self.getFBStatus()
        else:
            self.status_Status.setText('Disonnected')
            self.status_Status.setStyleSheet('color: rgb(0,0,0); background-color: rgb(237,51,59);')

    @QtCore.Slot(str, str)
    def logCommand(self, msgType, message):
        directory = os.path.join(self.log_folder, self.log_date)
        if not os.path.exists(directory):
            os.mkdir(directory)
        
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
        log = os.path.join(directory, '{}.log'.format('cmds'))
        data = '{}\t{}\t{}\n'.format(timestamp, msgType, message)

        cursor = QtGui.QTextCursor(self.status_Log.document())
        cursor.setPosition(0)
        self.status_Log.setTextCursor(cursor)
        self.status_Log.insertPlainText(data)

        with open(log, 'a+') as f:           
            f.write(data)

    def getSetpoint(self):
        err, resp = self.nni.command("getCurrent", [])
        I = resp['Z-Controller setpoint'] / 1e-12
        err, resp = self.nni.command("getBias", [])
        V = resp['Bias value (V)'] / 1e-3
        setpoint = '{:.2f} pA; {:.2f} mV'.format(I, V)
        self.status_Setpoint.setText(setpoint)

    def switchFBOnOff(self):
        err, resp = self.nni.command("getFeedback", [])
        fbStatus = resp["Z-Controller status"]
        if fbStatus == 0:
            err, resp = self.nni.command("setFeedback", [1])
        if fbStatus == 1:
            err, resp = self.nni.command("setFeedback", [0])
        time.sleep(1)
        self.getFBStatus()
    
    def getFBStatus(self):
        err, resp = self.nni.command("getFeedback", [])
        if resp["Z-Controller status"] == 0:
            self.status_Feedback.setText('Off')
            self.status_Feedback.setStyleSheet('color: rgb(0,0,0); background-color: rgb(237,51,59);')
        if resp["Z-Controller status"] == 1:
            self.status_Feedback.setText('On')
            self.status_Feedback.setStyleSheet('color: rgb(0,0,0); background-color: rgb(51,209,122);')

    def runScript(self):
        self.threadScript.nni = self.nni
        self.threadScript.script = self.scripting_Script.toPlainText()
        self.threadScript.cancelScript = False
        # self.threadScript.logSignal.connect(self.logCommand)
        self.threadScript.start()
      
    def stopScript(self):
         if self.threadScript.isRunning():
             self.threadScript.cancelScript = True
    
    def moveTipXplus(self):
        dx = self.tipman_dx.value() * 1e-10
        err, resp = self.nni.command("addX", [dx])

    def moveTipXminus(self):
        dx = (-1) * self.tipman_dx.value() * 1e-10
        err, resp = self.nni.command("addX", [dx])
    
    def moveTipYplus(self):
        dy = self.tipman_dy.value() * 1e-10
        err, resp = self.nni.command("addY", [dy])

    def moveTipYminus(self):
        dy = (-1) * self.tipman_dy.value() * 1e-10
        err, resp = self.nni.command("addY", [dy])

    def moveTipZplus(self):
        dz = self.tipman_dz.value() * 1e-10
        err, resp = self.nni.command("addZ", [dz])

    def moveTipZminus(self):
        dz = (-1) * self.tipman_dz.value() * 1e-10
        err, resp = self.nni.command("addZ", [dz])

    def showErrorMessage(self, msg):
        msgbox = QtWidgets.QMessageBox()
        msgbox.setWindowIcon(QtGui.QIcon(self.fileAunisIcon))
        msgbox.setWindowTitle('Information')
        msgbox.setIcon(QtWidgets.QMessageBox.Information)
        msgbox.setText(msg)
        msgbox.exec()

    def saveScript(self):
        filename = QtWidgets.QFileDialog.getSaveFileName(self, caption="Save script", dir='scripts')
        script = self.scripting_Script.toPlainText()
        if len(filename[0]) > 0:
            with open(filename[0], 'w') as f:
                f.write(script)

    def loadScript(self):
        filename = QtWidgets.QFileDialog.getOpenFileName(self, caption="Load script", dir='scripts')
        if len(filename[0]) > 0:
            with open(filename[0], 'r') as f:
                script = f.readlines()
            self.scripting_Script.clear()
            for i in range(len(script)):
                scriptLine = script[i]
                scriptLine = scriptLine.replace('\n', '')
                scriptLine = scriptLine.replace('\r', '')
                self.scripting_Script.appendPlainText(scriptLine)

    def openManual(self):
        os.startfile('Manual\\manual.pdf')
    
    def aboutMessage(self):
        msg = 'Aunis - Nanonis Control & Scripting Interface\n\n'
        msg += 'Version 0.2 (21.02.2022)\n\n'
        msg += '© 2022 Taner Esat'
        msgbox = QtWidgets.QMessageBox()
        msgbox.setWindowIcon(QtGui.QIcon(self.fileAunisIcon))
        msgbox.setWindowTitle('About')
        msgbox.setText(msg)
        msgbox.exec()
  
    # def showMessageStatusbar(self, msg):
    #     self.statusBar.showMessage(msg, 0)

    def closeEvent(self):
        self.stopScript()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    gui = AunisGUI()
    sys.exit(app.exec())
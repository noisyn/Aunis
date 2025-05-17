# Copyright (c) 2022-2025 Taner Esat <t.esat@fz-juelich.de>

import os
import sys
import time

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtWidgets import QApplication, QMainWindow

from PyNanonis import NanonisInterface

from UI.ui_Aunis import Ui_Aunis

class runScriptThread(QtCore.QThread):
    logSignal = QtCore.Signal(str, str)

    def __init__(self):
        super(runScriptThread, self).__init__()
        self.script = ''
        self.cancelScript = False
        self.nni = None

    def run(self):
        """Executes the commands one after the other.
        Non-nested loops are also possible.
        """        
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

class AunisUI(QMainWindow):
    def __init__(self):
        super(AunisUI, self).__init__()
        self.uiAu = Ui_Aunis()
        self.uiAu.setupUi(self)

        self.connected = False
        self.cancelScript = False
        self.threadScript = runScriptThread()
        self.threadScript.logSignal.connect(self.logCommand)

        self.log_folder = 'logs'
        self.log_date = time.strftime('%Y-%m-%d %H%M%S', time.localtime())

        self.updateUI()
        self.startUp()
    
    def updateUI(self):
        """Sets up the user interface.
        """ 
        self.fileIcon = 'UI\\Aunis.svg'
        self.setWindowIcon(QtGui.QIcon(self.fileIcon))

        # app.aboutToQuit.connect(self.closeEvent)   
        self.uiAu.menuSaveFile.triggered.connect(self.saveScript)
        self.uiAu.menuLoadFile.triggered.connect(self.loadScript)
        self.uiAu.menuAboutHelp.triggered.connect(self.aboutMessage)
        self.uiAu.menuManualHelp.triggered.connect(self.openManual)
        self.uiAu.status_Connect.clicked.connect(self.connect)
        self.uiAu.status_Disconnect.clicked.connect(self.disconnect)
        self.uiAu.status_Feedback.clicked.connect(self.switchFBOnOff)
        self.uiAu.status_Refresh.clicked.connect(self.updateStatus)
        self.uiAu.scripting_Run.clicked.connect(self.runScript)
        self.uiAu.scripting_Stop.clicked.connect(self.stopScript)
        self.uiAu.tipman_Yplus.clicked.connect(self.moveTipYplus)
        self.uiAu.tipman_Yminus.clicked.connect(self.moveTipYminus)
        self.uiAu.tipman_Xminus.clicked.connect(self.moveTipXminus)
        self.uiAu.tipman_Xplus.clicked.connect(self.moveTipXplus)
        self.uiAu.tipman_Zplus.clicked.connect(self.moveTipZplus)
        self.uiAu.tipman_Zminus.clicked.connect(self.moveTipZminus)

    def startUp(self):
        """Initializes the Nanonis Interface.
        """        
        self.nni = NanonisInterface()
        self.loadExternalInterfaces()
        self.updateStatus()

    def connect(self):
        """Connects to the Nanonis.
        """        
        ip = self.uiAu.settings_NanonisIP.text()
        port = np.int64(self.uiAu.settings_NanonisPort.text())
        self.connected = self.nni.connect(ip, port)
        self.updateStatus()
    
    def disconnect(self):
        """Disconnects from the Nanonis.
        """        
        self.connected = self.nni.disconnect()
        self.updateStatus()
    
    def updateStatus(self):
        """Updates the connection status and the setpoint values.
        """        
        if self.connected:
            self.uiAu.status_Status.setText('Connected')
            self.uiAu.status_Status.setStyleSheet('color: rgb(0,0,0); background-color: rgb(51,209,122);')
            self.getSetpoint()
            self.getFBStatus()
        else:
            self.uiAu.status_Status.setText('Disonnected')
            self.uiAu.status_Status.setStyleSheet('color: rgb(0,0,0); background-color: rgb(237,51,59);')

    @QtCore.Slot(str, str)
    def logCommand(self, msgType, message):
        """Saves an executed command and/or response message into a log file.

        Args:
            msgType (str): Request or Response
            message (str): Message text.
        """        
        directory = os.path.join(self.log_folder, self.log_date)
        if not os.path.exists(directory):
            os.mkdir(directory)
        
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
        log = os.path.join(directory, '{}.log'.format('cmds'))
        data = '{}\t{}\t{}\n'.format(timestamp, msgType, message)

        cursor = QtGui.QTextCursor(self.uiAu.status_Log.document())
        cursor.setPosition(0)
        self.uiAu.status_Log.setTextCursor(cursor)
        self.uiAu.status_Log.insertPlainText(data)

        with open(log, 'a+') as f:           
            f.write(data)

    def getSetpoint(self):
        """Reads out and displays the setpoint values.
        """        
        err, resp = self.nni.command("getCurrent", [])
        I = resp['Z-Controller setpoint'] / 1e-12
        err, resp = self.nni.command("getBias", [])
        V = resp['Bias value (V)'] / 1e-3
        setpoint = '{:.2f} pA; {:.2f} mV'.format(I, V)
        self.status_Setpoint.setText(setpoint)

    def switchFBOnOff(self):
        """Switches the feedback on or off.
        """        
        err, resp = self.nni.command("getFeedback", [])
        fbStatus = resp["Z-Controller status"]
        if fbStatus == 0:
            err, resp = self.nni.command("setFeedback", [1])
        if fbStatus == 1:
            err, resp = self.nni.command("setFeedback", [0])
        time.sleep(1)
        self.getFBStatus()
    
    def getFBStatus(self):
        """Reads out and displays the feedback status.
        """        
        err, resp = self.nni.command("getFeedback", [])
        if resp["Z-Controller status"] == 0:
            self.status_Feedback.setText('Off')
            self.status_Feedback.setStyleSheet('color: rgb(0,0,0); background-color: rgb(237,51,59);')
        if resp["Z-Controller status"] == 1:
            self.status_Feedback.setText('On')
            self.status_Feedback.setStyleSheet('color: rgb(0,0,0); background-color: rgb(51,209,122);')

    def runScript(self):
        """Starts the execution of the current script.
        """        
        self.threadScript.nni = self.nni
        self.threadScript.script = self.scripting_Script.toPlainText()
        self.threadScript.cancelScript = False
        self.threadScript.start()
      
    def stopScript(self):
        """Stops the execution of the current script.
        """        
        if self.threadScript.isRunning():
            self.threadScript.cancelScript = True
    
    def moveTipXplus(self):
        """Moves the tip in X+ direction by the specified amount.
        """        
        dx = self.tipman_dx.value() * 1e-10
        err, resp = self.nni.command("addX", [dx])

    def moveTipXminus(self):
        """Moves the tip in X- direction by the specified amount.
        """        
        dx = (-1) * self.tipman_dx.value() * 1e-10
        err, resp = self.nni.command("addX", [dx])
    
    def moveTipYplus(self):
        """Moves the tip in Y+ direction by the specified amount.
        """        
        dy = self.tipman_dy.value() * 1e-10
        err, resp = self.nni.command("addY", [dy])

    def moveTipYminus(self):
        """Moves the tip in Y- direction by the specified amount.
        """        
        dy = (-1) * self.tipman_dy.value() * 1e-10
        err, resp = self.nni.command("addY", [dy])

    def moveTipZplus(self):
        """Moves the tip in Z+ direction by the specified amount.
        """        
        dz = self.tipman_dz.value() * 1e-10
        err, resp = self.nni.command("addZ", [dz])

    def moveTipZminus(self):
        """Moves the tip in Z- direction by the specified amount.
        """        
        dz = (-1) * self.tipman_dz.value() * 1e-10
        err, resp = self.nni.command("addZ", [dz])

    def loadExternalInterfaces(self):
        """Loads and displays all external TCP interfaces.
        """        
        interfaces = self.nni.getExternalInterfaces()

        for counter, intf in enumerate(interfaces):
            item = QtWidgets.QTableWidgetItem(intf['Name'])
            item.setTextAlignment(QtCore.Qt.AlignCenter)
            self.uiAu.external_Interfaces.setItem(counter, 0, item)
            item = QtWidgets.QTableWidgetItem(intf['IP-Adress'])
            item.setTextAlignment(QtCore.Qt.AlignCenter)
            self.uiAu.external_Interfaces.setItem(counter, 1, item)
            item = QtWidgets.QTableWidgetItem(str(intf['Port']))
            item.setTextAlignment(QtCore.Qt.AlignCenter)
            self.uiAu.external_Interfaces.setItem(counter, 2, item)

    def showErrorMessage(self, msg):
        """Displays a message box with an error text.

        Args:
            msg (str): Error message.
        """        
        msgbox = QtWidgets.QMessageBox()
        msgbox.setWindowIcon(QtGui.QIcon(self.fileAunisIcon))
        msgbox.setWindowTitle('Information')
        msgbox.setIcon(QtWidgets.QMessageBox.Information)
        msgbox.setText(msg)
        msgbox.exec()

    def saveScript(self):
        """Saves the current script into a file.
        """        
        filename = QtWidgets.QFileDialog.getSaveFileName(self, caption="Save script", dir='scripts')
        script = self.uiAu.scripting_Script.toPlainText()
        if len(filename[0]) > 0:
            with open(filename[0], 'w') as f:
                f.write(script)

    def loadScript(self):
        """Loads a script from an existing file.
        """        
        filename = QtWidgets.QFileDialog.getOpenFileName(self, caption="Load script", dir='scripts')
        if len(filename[0]) > 0:
            with open(filename[0], 'r') as f:
                script = f.readlines()
            self.uiAu.scripting_Script.clear()
            for i in range(len(script)):
                scriptLine = script[i]
                scriptLine = scriptLine.replace('\n', '')
                scriptLine = scriptLine.replace('\r', '')
                self.uiAu.scripting_Script.appendPlainText(scriptLine)

    def openManual(self):
        """Opens the manual.
        """        
        os.startfile('manual\\manual.pdf')
    
    def aboutMessage(self):
        msg = 'Aunis - Nanonis Control & Scripting Interface\n\n'
        msg += 'Version 0.32 (04.05.2025)\n\n'
        msg += '© 2022-2025 Taner Esat'
        msgbox = QtWidgets.QMessageBox()
        msgbox.setWindowIcon(QtGui.QIcon(self.fileIcon))
        msgbox.setWindowTitle('About')
        msgbox.setText(msg)
        msgbox.exec()
  
    # def showMessageStatusbar(self, msg):
    #     self.statusBar.showMessage(msg, 0)

    def closeEvent(self, event: QtGui.QCloseEvent):
        try:
            self.stopScript()
        except:
            pass
        return super().closeEvent(event)

if __name__ == '__main__':
    # sys.argv += ['-platform', 'windows:darkmode=2']
    # darkmode=1  # light theme
    # darkmode=2  # dark theme
    app = QApplication(sys.argv)
    # app.setStyle(QtWidgets.QStyleFactory.create("Fusion"))
    ui = AunisUI()
    ui.show()
    sys.exit(app.exec())
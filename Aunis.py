# Copyright (c) 2022-2026 Taner Esat <t.esat@fz-juelich.de>

import os
import sys
import time
import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtWidgets import QApplication, QMainWindow
from Scripting import ScriptingInterface, TCP_INTERFACES
from UI.ui_Aunis import Ui_Aunis

class runScriptThread(QtCore.QThread):
    logSignal = QtCore.Signal(str, str, str)
    errorMsg = QtCore.Signal(str)
    scriptStatus = QtCore.Signal(str)

    def __init__(self):
        super(runScriptThread, self).__init__()
        self.script = ''
        self.cancelScript = False
        self.nni = None
    
    def run(self): 
        """Executes the commands one after the other.
        Nested loops are also possible.
        """            
        script = self.script
        commands, errors = self.nni.parse_commands(script)
        if errors:
            msg = "SYNTAX ERRORS:\n"
            for e in errors:
                msg += e + "\n"
            self.errorMsg.emit(msg)
            self.scriptStatus.emit('Syntax errors')
        else:
            self.execute(commands)

    def execute(self, commands):
        """
        Executes parsed commands.
        """
        self.scriptStatus.emit('Running')
        for entry in commands:
            if self.cancelScript == False:
                cmd = entry["cmd"]
                func = entry["func"]
                args = entry["args"]
                errorString, response, variables = func(*args)
                if(len(errorString) != 0):
                    status = errorString
                else:
                    status = "OK"
                self.logSignal.emit('Request', cmd + ' ' + ' '.join(str(x) for x in args), status)
                if len(variables) > 0:
                    self.logSignal.emit('Response', '[' + ", ".join(str(x) for x in variables) + "]", "")
        self.scriptStatus.emit('Finished')
        

class AunisUI(QMainWindow):
    def __init__(self):
        super(AunisUI, self).__init__()
        self.uiAu = Ui_Aunis()
        self.uiAu.setupUi(self)

        self.connected = False
        self.cancelScript = False
        self.threadScript = runScriptThread()
        self.threadScript.logSignal.connect(self.logCommand)
        self.threadScript.errorMsg.connect(self.showErrorMessage)
        self.threadScript.scriptStatus.connect(self.updateScriptingStatus)

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
        self.nni = ScriptingInterface()
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
    
    @QtCore.Slot(str)
    def updateScriptingStatus(self, status):
        self.uiAu.scripting_Status.setText(status)

    @QtCore.Slot(str, str)
    def logCommand(self, msgType, message, status):
        """Saves an executed command and/or response message into a log file.

        Args:
            msgType (str): Request or Response
            message (str): Message text.
        """
        if not os.path.exists(self.log_folder):
            os.mkdir(self.log_folder)

        directory = os.path.join(self.log_folder, self.log_date)
        if not os.path.exists(directory):
            os.mkdir(directory)
        
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
        log = os.path.join(directory, '{}.log'.format('cmds'))
        data = '{}\t{}\t{}\t{}\n'.format(timestamp, msgType, message, status)

        cursor = QtGui.QTextCursor(self.uiAu.status_Log.document())
        cursor.setPosition(0)
        self.uiAu.status_Log.setTextCursor(cursor)
        self.uiAu.status_Log.insertPlainText(data)

        with open(log, 'a+') as f:           
            f.write(data)

    def getSetpoint(self):
        """Reads out and displays the setpoint values.
        """
        errorString, response, variables = self.nni.execute("current.Get")
        I = variables[0] / 1e-12
        errorString, response, variables = self.nni.execute("bias.Get")
        V = variables[0] / 1e-3
        setpoint = '{:.2f} pA; {:.2f} mV'.format(I, V)
        self.uiAu.status_Setpoint.setText(setpoint)

    def switchFBOnOff(self):
        """Switches the feedback on or off.
        """        
        errorString, response, variables = self.nni.execute("fb.Get")   
        fbStatus = variables[0]
        if fbStatus == 0:
            errorString, response, variables = self.nni.execute("fb.Set 1")
        if fbStatus == 1:
            errorString, response, variables = self.nni.execute("fb.Set 0")
        time.sleep(1)
        self.getFBStatus()
    
    def getFBStatus(self):
        """Reads out and displays the feedback status.
        """        
        errorString, response, variables = self.nni.execute("fb.Get")        
        fbStatus = variables[0]
        if fbStatus == 0:
            self.uiAu.status_Feedback.setText('Off')
            self.uiAu.status_Feedback.setStyleSheet('color: rgb(0,0,0); background-color: rgb(237,51,59);')
        if fbStatus == 1:
            self.uiAu.status_Feedback.setText('On')
            self.uiAu.status_Feedback.setStyleSheet('color: rgb(0,0,0); background-color: rgb(51,209,122);')

    def runScript(self):
        """Starts the execution of the current script.
        """        
        self.threadScript.nni = self.nni
        self.threadScript.script = self.uiAu.scripting_Script.toPlainText()
        self.threadScript.cancelScript = False
        self.threadScript.start()
      
    def stopScript(self):
        """Stops the execution of the current script.
        """        
        if self.threadScript.isRunning():
            self.threadScript.cancelScript = True
            self.updateScriptingStatus('Stopping...')
    
    def moveTipXplus(self):
        """Moves the tip in X+ direction by the specified amount.
        """        
        dx = self.uiAu.tipman_dx.value() * 1e-10
        self.nni.addX(dx)

    def moveTipXminus(self):
        """Moves the tip in X- direction by the specified amount.
        """        
        dx = (-1) * self.uiAu.tipman_dx.value() * 1e-10
        self.nni.addX(dx)
    
    def moveTipYplus(self):
        """Moves the tip in Y+ direction by the specified amount.
        """        
        dy = self.uiAu.tipman_dy.value() * 1e-10
        self.nni.addY(dy)

    def moveTipYminus(self):
        """Moves the tip in Y- direction by the specified amount.
        """        
        dy = (-1) * self.uiAu.tipman_dy.value() * 1e-10
        self.nni.addY(dy)

    def moveTipZplus(self):
        """Moves the tip in Z+ direction by the specified amount.
        """        
        dz = self.uiAu.tipman_dz.value() * 1e-10
        self.nni.addZ(dz)

    def moveTipZminus(self):
        """Moves the tip in Z- direction by the specified amount.
        """        
        dz = (-1) * self.uiAu.tipman_dz.value() * 1e-10
        self.nni.addZ(dz)

    def loadExternalInterfaces(self):
        """Loads and displays all external TCP interfaces.
        """        
        for index, (key, value) in enumerate(TCP_INTERFACES.items()):
            item = QtWidgets.QTableWidgetItem(str(key))
            item.setTextAlignment(QtCore.Qt.AlignCenter)
            self.uiAu.external_Interfaces.setItem(index, 0, item)
            item = QtWidgets.QTableWidgetItem(str(value['host']))
            item.setTextAlignment(QtCore.Qt.AlignCenter)
            self.uiAu.external_Interfaces.setItem(index, 1, item)
            item = QtWidgets.QTableWidgetItem(str(value['port']))
            item.setTextAlignment(QtCore.Qt.AlignCenter)
            self.uiAu.external_Interfaces.setItem(index, 2, item)

    @QtCore.Slot(str)
    def showErrorMessage(self, msg):
        """Displays a message box with an error text.

        Args:
            msg (str): Error message.
        """        
        msgbox = QtWidgets.QMessageBox()
        msgbox.setWindowIcon(QtGui.QIcon(self.fileIcon))
        msgbox.setWindowTitle('Information')
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
        msg = 'Aunis - Nanonis Scripting Interface\n\n'
        msg += 'Version 0.6 (02 Jan 2026)\n\n'
        msg += '© 2022-2026 Taner Esat\n'
        msg += 'Email: t.esat@fz-juelich.de'
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
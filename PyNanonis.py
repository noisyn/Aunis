# Copyright (c) 2022 Taner Esat <t.esat@fz-juelich.de>

import json
import socket
import struct
import time

import numpy as np
from scipy.optimize import curve_fit

class NanonisInterface():
    def __init__(self):
        """Loads the command lists from the JSON files.
        """        
        self.connected = False
        self.commandList = self.getCommandList("cmds/commands.json")
        self.specialCommandList = self.getCommandList("cmds/special_commands.json")

    def getCommandList(self, filename):
        """Reads the predefined commands from a JSON file.

        Args:
            filename (str): Name of the JSON file.

        Returns:
            dict: List of commands and arguments.
        """        
        with open(filename, "r") as cmd_file:
            commandList = json.load(cmd_file)
        return commandList

    def connect(self, ip, port):
        """Connects to the Nanonis software via the TCP interface.

        Args:
            ip (str): IP adress of the TCP interface.
            port (int): Port of the TCP interface.

        Returns:
            bool: Connection status. True: Connected. False: Disconnected.
        """        
        try:
            self.nanonis = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.nanonis.connect((ip, port))
            self.connected = True
        except:
            self.connected = False

        return self.connected
    
    def disconnect(self):
        """Disconnects from the Nanonis software.

        Returns:
            bool: Connection status. True: Connected. False: Disconnected.
        """        
        if self.connected:
            self.nanonis.close()
            self.connected = False
        
        return self.connected

    def convertStringToByte(self, cmd, size):
        """Converts a string to a bytes object. 
        Byte object is padded with zeros until the length equals 'size'.

        Args:
            cmd (str): String to be converted.
            size (int): Size of byte-array.

        Returns:
            byte: Converted string as bytes object.
        """        
        cmd_bytes = cmd.encode()
        if len(cmd_bytes) < size:
            num_pads = size - len(cmd_bytes)
            for _ in range(num_pads):
                cmd_bytes += bytes([0])
        return cmd_bytes

    def convertNumberToByte(self, num, numType):
        """Converts a number into a byte object (big-endian).

        Args:
            num (int, float, etc.): Any number that is accepted by struct.pack().
            numType (str): Format type according to the module struct().

        Returns:
            bytes: Converted number as bytes object.
        """        
        conv_format = '>{}'.format(numType)
        num_bytes = struct.pack(conv_format, num)
        return num_bytes

    def convertBytesToNumber(self, numBytes, numType):
        """Converts a bytes object (big-endian) into a number.

        Args:
            numBytes (bytes): Bytes object to be converted.
            numType (str): Format type according to the module struct().

        Returns:
            int, float, etc.: Number. Type according to specified Number Formatting Type.
        """        
        conv_format = '>{}'.format(numType)
        num = struct.unpack(conv_format, numBytes)[0]
        return num

    def encodeRequestMessage(self, cmdName, sendResponse, argValues, argTypes):
        """Encodes a command including arguments into a byte array that can be interpreted 
        by the Nanonis software. For syntax of the request messages see page 23-29 in 
        Nanonis TCP Protocol. 

        Args:
            cmdName (str): Name of the executed command.
            sendResponse (int): Defines if the server sends a message back (=1) or not (=0).
            argValues (list): Argument values.
            argTypes (list): Argument types according to Number Formatting Type.

        Returns:
            bytes: Encoded request message.
        """        
        request = b''
        body = b''
        if len(argValues) > 0:
            for key, value in argValues.items():
                if argTypes[key] != 's':
                    arg = self.convertNumberToByte(value, argTypes[key])
                    body += arg

        cmd = self.convertStringToByte(cmdName, 32)
        body_size = self.convertNumberToByte(len(body), 'i')
        response = self.convertNumberToByte(sendResponse, 'h')
        not_used = self.convertNumberToByte(0, 'h')
        request = cmd + body_size + response + not_used + body

        return request
    
    def decodeResponseMessage(self, resp, respTypes):
        """Decodes a response message from the Nanonis software. 
        Currently only single values can be decoded. Arrays are not yet supported.

        Args:
            resp (bytes): Response message from Nanonis.
            respTypes (str): Response type according to Number Formatting Types.

        Returns:
            int, float, etc.: Decoded response message.
        """        
        headerSize = 40 # Fixed
        index = headerSize
        decodedResp = {}
        for key, value in respTypes.items():
            size = len(self.convertNumberToByte(0, value))
            decodedResp[key] = self.convertBytesToNumber(resp[index:index+size], value)
            index += size
        return decodedResp
    
    def sendRequest(self, request):
        """Sends a data/request message to the Nanonis software.

        Args:
            request (bytes): Request message encoded according to the Nanonis TCP Protocol.

        Returns:
            bool, number: Error (True/False), Decoded response message.
        """        
        resp = ''
        err = False
        if self.connected:
            self.nanonis.sendall(request)
            resp = self.nanonis.recv(1024)
        else:
            err = True  
        return err, resp
          
    def command(self, cmdAlias, cmdArgs):
        """Executes a (normal) command, i.e. a single command.

        Args:
            cmdAlias (str): Command name/alias according to JSON files.
            cmdArgs (list): Command arguments.

        Returns:
            bool, number: Error (True/False), Decoded response message.
        """        
        resp = ''
        err = False
        print(cmdAlias, cmdArgs)
        if cmdAlias in self.commandList:
            cmdName = self.commandList[cmdAlias]['cmdName']
            argTypes = self.commandList[cmdAlias]['argTypes']
            argValues = self.commandList[cmdAlias]['argValues']
            respTypes = self.commandList[cmdAlias]['respTypes']
            if len(cmdArgs) == len(self.commandList[cmdAlias]['args']):
                if len(cmdArgs) > 0:
                    i = 0
                    for arg in self.commandList[cmdAlias]['args']:
                        if argTypes[arg] == 's':
                            argValues[arg] = cmdArgs[i]
                        elif argTypes[arg] == 'I':
                            argValues[arg] = np.int(cmdArgs[i])
                        elif argTypes[arg] == 'i':
                            argValues[arg] = np.int(cmdArgs[i])
                        elif argTypes[arg] == 'H':
                            argValues[arg] = np.int(cmdArgs[i])
                        else:
                            argValues[arg] = np.float(cmdArgs[i])

                        i += 1
                
                sendResponse = 1
                request = self.encodeRequestMessage(cmdName, sendResponse, argValues, argTypes)
                err, resp = self.sendRequest(request)
                # Debugging
                # resp = b'\x46\x6F\x6C\x4D\x65\x2E\x58\x59\x50\x6F\x73\x47\x65\x74\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x18\x00\x00\x00\x00\x3E\x35\x79\x8E\xE2\x30\x8C\x3A\xBE\x35\x79\x8E\xE2\x30\x8C\x3A\x00\x00\x00\x00\x00\x00\x00\x00'
                # resp = b'FolMe.XYPosGet\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x18\x00\x00\x00\x00\xbd\x7f\x02m\x00\x00\x00\x00\xbd\x91\xe4\xa4\x80\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
                # print(resp)
                resp = self.decodeResponseMessage(resp, respTypes)

                print(cmdName)
                # print(argTypes)
                # print(argValues)
                # print(respTypes)
                # print(request)
                # print(resp)
        elif cmdAlias in self.specialCommandList:
            err, resp = self.specialCommand(cmdAlias, cmdArgs)
        
        return err, resp
    
    def specialCommand(self, cmdAlias, cmdArgs):
        """Executes a (special) command.
        Special commands are either compound commands or commands that require 
        further intermediate steps or calculations. These commands are hard coded.

        Args:
            cmdAlias (str): Command name/alias according to JSON files.
            cmdArgs (list): Command arguments.

        Returns:
            bool, number: Error (True/False), Decoded response message.
        """
        resp = ''
        err = False
        if cmdAlias in self.specialCommandList:
            if len(cmdArgs) == len(self.specialCommandList[cmdAlias]['args']):
                if cmdAlias == "addX":
                    err, resp = self.command('getXY', [])
                    x = resp['X (m)'] + np.float(cmdArgs[0])
                    y = resp['Y (m)']
                    err, resp = self.command('setXY', [x, y])
                if cmdAlias == "addY":
                    err, resp = self.command('getXY', [])
                    x = resp['X (m)']
                    y = resp['Y (m)'] + np.float(cmdArgs[0])
                    err, resp = self.command('setXY', [x, y])
                if cmdAlias == "addZ":
                    err, resp = self.command('getZ', [])
                    z = resp['Z position (m)'] + np.float(cmdArgs[0])
                    err, resp = self.command('setZ', [z])
                if cmdAlias == "addCurrent":
                    err, resp = self.command('getCurrent', [])
                    current = resp['Z-Controller setpoint'] + np.float(cmdArgs[0])
                    err, resp = self.command('setCurrent', [current])
                if cmdAlias == "addBias":
                    err, resp = self.command('getBias', [])
                    bias = resp['Bias value (V)'] + np.float(cmdArgs[0])
                    err, resp = self.command('setBias', [bias])
                if cmdAlias == "correctZDrift":
                    err, resp = self.command('getDriftComp', [])
                    comp_status = resp['Compensation status']
                    old_vx = resp['Vx (m/s)']
                    old_vy = resp['Vy (m/s)']
                    old_vz = resp['Vz (m/s)']

                    dt = 1 
                    n = int(np.float(cmdArgs[0]) / dt)
                    t_data = np.zeros(n)
                    z_data = np.zeros(n)

                    for i in range(len(t_data)):
                        err, resp = self.command('getZ', [])
                        z = resp['Z position (m)']
                        t_data[i] = dt * i
                        z_data[i] = z
                        time.sleep(int(dt))

                    popt, _ = curve_fit(self.lin_func, t_data, z_data)
                    vz = popt[0]

                    if comp_status == 1:
                        new_vz = old_vz + vz
                    else:
                        old_vx = 0
                        old_vy = 0
                        new_vz = vz
                    err, resp = self.command('setDriftComp', [1, old_vx, old_vy, new_vz])
                if cmdAlias == "wait":
                    time.sleep(np.float(cmdArgs[0]))

        return err, resp

    def lin_func(self, x, m, b):
        return x * m + b
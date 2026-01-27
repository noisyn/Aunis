# Copyright (c) 2022-2026 Taner Esat <t.esat@fz-juelich.de>

import ast
import socket
import re
import time
import numbers
import numpy as np
import nanonis_spm
from scipy.optimize import curve_fit

# -------------------------------
# TCP INTERFACES
# -------------------------------
"""
Define all TCP remote interfaces here.
Key: interface name (used to reference remote devices)
Value: dict with 'host' and 'port'
    host → IP address of the remote device.
    port → TCP port where the device is listening.
"""
TCP_INTERFACES = {
    "QuPe": {"host": "192.168.1.10", "port": 1337}, # Example
}

# -------------------------------
# TCP Client Class
# -------------------------------
class TCPClient:
    """
    Encapsulates sending commands to a remote TCP interface.

    Provides two modes:
    - send: fire-and-forget
    - query: send and wait for response
    """
    def __init__(self, interface_name: str):
        if interface_name not in TCP_INTERFACES:
            raise ValueError(f"Unknown interface: {interface_name}")
        self.host = TCP_INTERFACES[interface_name]["host"]
        self.port = TCP_INTERFACES[interface_name]["port"]

    def query(self, command_name: str, args: list):
        """Sends a command with arguments to the remote device and waits for response.
        Response format expected from device: "error|response|variable"
        This format is necessary for compatibility with the Python Package for Nanonis (nanonis_spm).

        Args:
            command_name (str): Remote command name.
            args (list): Arguments for the remote command.

        Returns:
            tuple: (errorString, response, variables)
                - errorString (str): Error message.
                - response (str or bytes): Raw response from the remote device.
                - variables (list): Returned variables from the remote device.
        """
        script_line = f"{command_name} " + " ".join(map(str, args)) + "\n"
        print(script_line)
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((self.host, self.port))
                s.sendall(script_line.encode())
                response_data = b""
                while True:
                    data = s.recv(1024)
                    if not data:
                        break
                    response_data += data

            # Assume the remote device sends a response in the format:
            # "error|response|variable1,variable2" (use 'None' for empty fields)
            decoded = response_data.decode().strip()
            parts = decoded.split("|")
            if len(parts) != 3:
                # Malformed response from device
                return ("Malformed response", decoded, [])
            error = "" if parts[0] == "None" else parts[0]
            response = "" if parts[1] == "None" else parts[1]
            # variable = [] if parts[2] == "None" else parts[2]
            if parts[2] == "None":
                variable = []
            else:
                variable = parts[2].split(",")
            return ([error], response, variable)

        except Exception as e:
            print(str(e))
            return (str(e), "", [])
        
    def send(self, command_name: str, args: list):
        """
        Sends a command without expecting a response.
        Returns (error, "", [])
        """
        script_line = f"{command_name} " + " ".join(map(str, args)) + "\n"
        print(script_line)
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((self.host, self.port))
                s.sendall(script_line.encode())
            return ("", "", [])
        except Exception as e:
            return (str(e), "", [])
        

# -------------------------------
# Scripting Interface Class
# -------------------------------
class ScriptingInterface():
    commandList = {}

    def __init__(self):
        self.commandList = FUNCTION_REGISTRY
        self.connected = False

        # List/for support (parse-time only)
        self._var_placeholder = re.compile(r"\$([A-Za-z_]\w*)")
    
    def connect(self, ip, port): 
        """Connect to Nanonis TCP Interface.

        Args:
            ip (str): IP adress of the interface.
            port (int): Port of the interface.

        Returns:
            bool: True if connected and false if not.
        """           
        try:
            connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            connection.connect((ip, port))
            self.nanonis = nanonis_spm.Nanonis(connection)
            self.connected = True
        except:
            self.connected = False

        return self.connected
    
    def disconnect(self):
        """Disconnect from Nanonis.
        """        
        if self.connected:
            self.nanonis.close()
            self.connected = False

    def _parse_numeric_list_literal(self, rhs: str):
        """Parse numeric-only list literals like [1, 2, 3.5, 1e-3].

        Allowed:
            - int, float (incl. scientific notation)

        Disallowed:
            - bool, strings, nested lists, any non-numeric type
        """
        val = ast.literal_eval(rhs.strip())

        if not isinstance(val, list):
            raise ValueError("List definition must be a list literal like [1,2,3]")

        for v in val:
            # bool is a subclass of int -> exclude explicitly
            if isinstance(v, bool) or not isinstance(v, numbers.Real):
                raise ValueError(f"Invalid list element {v!r}: only numeric values are allowed")

        return val
    
    def _interpolate_token(self, token: str, vars_env: dict):
        """Replace $var and {var} with vars_env[var] if present (stringified)."""
        def repl_placeholder(m):
            k = m.group(1)
            return str(vars_env.get(k, m.group(0)))

        token = self._var_placeholder.sub(repl_placeholder, token)
        return token
    
    def check_syntax(self, script: str):
        """Validate text script for correct commands and argument counts.

        Args:
            script (str): The text-based script.

        Returns:
            list[str]: A list of syntax errors (empty if valid). Checks:
                - Unknown commands
                - Wrong number of arguments
                - Invalid loop syntax
                - Unbalanced loops
        """       
        errors = []
        lines = [line.strip() for line in script.splitlines() if line.strip()]

        block_stack = []   # entries: "loop" or "for"
        var_stack = []     # stack of sets of active loop variables
        known_lists = set()

        VAR_REF = re.compile(r"\$([A-Za-z_]\w*)|\{([A-Za-z_]\w*)\}")

        for line_num, line in enumerate(lines, start=1):

            # list <name> [ ... ]
            if line.startswith("list "):
                try:
                    parts = line.split(None, 2)
                    if len(parts) != 3:
                        raise ValueError
                    _, name, rhs = parts

                    if not re.match(r"^[A-Za-z_]\w*$", name):
                        raise ValueError

                    self._parse_numeric_list_literal(rhs)
                    known_lists.add(name)
                except Exception:
                    errors.append(f"Line {line_num}: invalid list syntax → {line}")
                continue

            # loop N (does not introduce variables)
            if line.startswith("loop"):
                parts = line.split()
                if len(parts) != 2 or not parts[1].isdigit():
                    errors.append(f"Line {line_num}: invalid loop syntax → {line}")
                else:
                    block_stack.append("loop")
                    var_stack.append(set(var_stack[-1]) if var_stack else set())
                continue

            # for var in listname (introduces a variable)
            if line.startswith("for "):
                parts = line.split()
                if len(parts) != 4 or parts[2] != "in":
                    errors.append(f"Line {line_num}: invalid for syntax → {line}")
                else:
                    var_name = parts[1]
                    list_name = parts[3]

                    if not re.match(r"^[A-Za-z_]\w*$", var_name):
                        errors.append(f"Line {line_num}: invalid loop variable name → {line}")

                    if list_name not in known_lists:
                        errors.append(f"Line {line_num}: unknown list '{list_name}' → {line}")

                    block_stack.append("for")

                    # new variable scope level
                    current_vars = set(var_stack[-1]) if var_stack else set()
                    current_vars.add(var_name)
                    var_stack.append(current_vars)
                continue

            # end
            if line == "end":
                if not block_stack:
                    errors.append(f"Line {line_num}: 'end' without opener")
                else:
                    block_stack.pop()
                    var_stack.pop()
                continue

            # normal command line
            parts = line.split()
            cmd_name = parts[0]

            if cmd_name not in FUNCTION_REGISTRY:
                errors.append(f"Line {line_num}: unknown command → {line}")
                continue

            # validate argument count
            cmd_info = FUNCTION_REGISTRY[cmd_name]
            expected = sum(1 for a in cmd_info["args"].values() if a["user"])
            given = len(parts) - 1

            if expected != given:
                errors.append(
                    f"Line {line_num}: wrong number of arguments for '{cmd_name}' "
                    f"(expected {expected}, got {given})"
                )

            active_vars = var_stack[-1] if var_stack else set()

            for token in parts[1:]:
                for m in VAR_REF.finditer(token):
                    var_name = m.group(1) or m.group(2)
                    if var_name not in active_vars:
                        errors.append(
                            f"Line {line_num}: undefined loop variable '${var_name}' → {line}"
                        )

        if block_stack:
            errors.append("Unclosed block detected")

        return errors

    def parse_commands(self, script: str):
        """Parse a text-based script into a flat list of commands with arguments.

        The parser:
        - Splits the script into lines.
        - Handles nested loops ("loop X" ... "end").
        - Handles list definitions ("list name [..]") (numeric-only).
        - Handles list iteration ("for var in listname" ... "end").
        - Expands loops/for into repeated command blocks.
        - Performs $var substitution during parsing.
        - Casts args to the required types during parsing.
        - Validates syntax before parsing.

        Args:
            script (str): The raw text script with commands, one per line.

        Returns:
            tuple: (commands, errors)
                - commands (list[dict]): A flat list of parsed commands, where each command is a dict:
                                {
                                    "cmd": <str>,   # Command name as written in script
                                    "func": <callable>, # Function or method reference
                                    "args": <list>,     # Positional argument values
                                }
                - errors (list[str]): List of syntax error strings (empty if valid)
        """
        errors = self.check_syntax(script)
        if errors:
            return None, errors

        lines = [line.strip() for line in script.splitlines() if line.strip()]
        commands, _ = self._parse_block(lines)
        return commands, []
    
    def _parse_block(self, lines, index=0, lists_env=None, vars_env=None):
        """ Recursively parse a block of script lines, expanding loops into repeated commands.

        Args:
            lines (list[str]): List of non-empty script lines.
            index (int): Current index to start parsing from.

        Returns:
            tuple: (parsed_commands, next_index)
                - parsed_commands: list of dicts with keys "command", "func", "args". See also parse_commands for details.
                - next_index: next line index after this block (used for recursion)
        """

        """
        INSTANCE_MAP maps class names to pre-created instances.
        Used to automatically inject instances for class methods in FUNCTION_REGISTRY.
        """
        INSTANCE_MAP = {
            "Nanonis": self.nanonis,
            "ScriptingInterface": self,
        }

        if lists_env is None:
            lists_env = {}
        if vars_env is None:
            vars_env = {}

        def _extract_block_lines(lines, start_index):
            """Return (block_lines, next_index_after_end) for the block starting at start_index."""
            depth = 0
            block_lines = []
            i = start_index

            while i < len(lines):
                ln = lines[i]

                if ln.startswith("loop") or ln.startswith("for "):
                    depth += 1
                    block_lines.append(ln)
                    i += 1
                    continue

                if ln == "end":
                    if depth == 0:
                        return block_lines, i + 1
                    depth -= 1
                    block_lines.append(ln)
                    i += 1
                    continue

                block_lines.append(ln)
                i += 1

            # should not happen if check_syntax passed
            raise ValueError("Unclosed block while extracting lines")

        result = []
        while index < len(lines):
            line = lines[index]

            # list <name> [ ... ]  -> store only (no command emitted)
            if line.startswith("list "):
                _, name, rhs = line.split(None, 2)
                lists_env[name] = self._parse_numeric_list_literal(rhs)
                index += 1
                continue

            # loop N
            if line.startswith("loop"):
                _, count_str = line.split()
                count = int(count_str)

                body_lines, next_index = _extract_block_lines(lines, index + 1)
                block, _ = self._parse_block(body_lines, 0, lists_env, vars_env)
                result.extend(block * count)

                index = next_index
                continue

            # for var in listname
            if line.startswith("for "):
                parts = line.split()
                var_name = parts[1]
                list_name = parts[3]

                body_lines, next_index = _extract_block_lines(lines, index + 1)

                for v in lists_env[list_name]:
                    new_vars = dict(vars_env)
                    new_vars[var_name] = v
                    block, _ = self._parse_block(body_lines, 0, lists_env, new_vars)
                    result.extend(block)

                index = next_index
                continue

            # end
            if line == "end":
                return result, index + 1

            # normal command
            parts = line.split()
            cmd_name = parts[0]
            cmd_info = FUNCTION_REGISTRY[cmd_name]

            # interpolate user values BEFORE casting
            user_values = [self._interpolate_token(tok, vars_env) for tok in parts[1:]]

            args = []
            user_index = 0
            for arg_name, arg_info in cmd_info["args"].items():
                if arg_info["user"]:
                    args.append(arg_info["type"](user_values[user_index]))
                    user_index += 1
                else:
                    args.append(arg_info["default"])

            func_ref = cmd_info["func"]
            if hasattr(func_ref, "__qualname__") and "." in func_ref.__qualname__:
                cls_name = func_ref.__qualname__.split(".")[0]
                instance = INSTANCE_MAP[cls_name]
                func = func_ref.__get__(instance)
            else:
                func = func_ref

            result.append({
                "cmd": cmd_name,
                "func": func,
                "args": args,
            })
            index += 1

        return result, index
    
    def execute(self, script):
        """Execute a text-based script.

        Args:
            script (str): The text-based script.

        Returns:
            tuple: (errorString, response, variables)
                - errorString (str): Error messages.
                - response (str or bytes): Raw response from the called function(s).
                - variables (list): List of returned variables from the called function(s)
        """
        commands, errors = self.parse_commands(script)
        # print("PARSED:", commands)

        for entry in commands:
            cmd = entry["cmd"]
            func = entry["func"]
            args = entry["args"]
            errorString, response, variables = func(*args)

        return errorString, response, variables
   
    # -------------------------------
    # CUSTOM FUNCTIONS
    # -------------------------------
    def getXY(self):
        errorString, response, variables = self.nanonis.FolMe_XYPosGet(1)
        print(self.nanonis.FolMe_XYPosGet(1))
        x = variables[0]
        y = variables[1]
        return errorString, response, [x, y]
    
    def getZ(self):
        errorString, response, variables = self.nanonis.ZCtrl_ZPosGet()
        z = variables[0]
        return errorString, response, [z]

    def setXY(self, x, y):
        errorString, response, variables = self.nanonis.FolMe_XYPosSet(np.float64(x), np.float64(y), 1)
        return errorString, response, variables
    
    def setZ(self, z):
        errorString, response, variables = self.nanonis.ZCtrl_ZPosSet(np.float32(z))
        return errorString, response, variables

    def addX(self, dx):
        errorString, response, [x, y] = self.getXY()
        x = x + dx
        self.setXY(x, y)
        return errorString, response, [x, y]

    def addY(self, dy):
        errorString, response, [x, y] = self.getXY()
        y = y + dy
        self.setXY(x, y)
        return errorString, response, [x, y]
    
    def addZ(self, dz):
        errorString, response, [z] = self.getZ()
        z = z + dz
        self.setZ(z)
        return errorString, response, [z]
    
    def addBias(self, dV):
        errorString, response, variables = self.nanonis.Bias_Get()
        bias = variables[0]
        bias = bias + dV
        errorString, response, variables = self.nanonis.Bias_Set(np.float32(bias))
        return errorString, response, variables
    
    def addCurrent(self, dI):
        errorString, response, variables = self.nanonis.ZCtrl_SetpntGet()
        current = variables[0]
        current = current + dI
        error, response, variables = self.nanonis.ZCtrl_SetpntSet(np.float32(current))
        return errorString, response, variables

    def wait(self, dt):
        time.sleep(float(dt))
        errorString = ''
        response = ''
        variables = []
        return errorString, response, variables
        
    def correctZDrift(self, duration):
        errorString, response, variables = self.execute('drift.Get')
        comp_status = variables[0]
        old_vx = variables[1]
        old_vy = variables[2]
        old_vz = variables[3]

        dt = 1 
        n = int(np.float32(duration / dt))
        t_data = np.zeros(n)
        z_data = np.zeros(n)

        for i in range(len(t_data)):
            errorString, response, [z] = self.getZ()
            t_data[i] = dt * i
            z_data[i] = z
            time.sleep(int(dt))

        def lin_func(x, m, b):
            return x * m + b

        popt, _ = curve_fit(lin_func, t_data, z_data)
        vz = popt[0]

        if comp_status == 1:
            new_vz = old_vz + vz
        else:
            old_vx = 0
            old_vy = 0
            new_vz = vz
        errorString, response, variables = self.execute(f'drift.Set 1 {old_vx} {old_vy} {new_vz}')
        return errorString, response, variables


# -------------------------------
# FUNCTION_REGISTRY
# -------------------------------
"""
FUNCTION_REGISTRY is a dictionary mapping command names (strings) to function metadata.

Each entry defines:
    "func": reference to function or unbound class method
    "args": dictionary of arguments:
        - "type": Python (numpy) type for input conversion
        - "default": default value if not user-supplied
        - "user": True if user must provide argument, False if defaulted

Remote commands are added to FUNCTION_REGISTRY just like normal commands.

Example:
FUNCTION_REGISTRY = {
    "add": {
        "func": add,
        "args": {
            "a": {"type": int, "default": 0, "user": True},
            "b": {"type": int, "default": 2, "user": False},
        },
    },
}
"""
FUNCTION_REGISTRY = {
    "bias.Set": {
        "func": nanonis_spm.Nanonis.Bias_Set,
        "args": {
            "Bias value (V)": {"type": np.float32, "default": 0.5, "user": True}
        },
    },
    "bias.Get": {
        "func": nanonis_spm.Nanonis.Bias_Get,
        "args": {
        },
    },
    "current.Set": {
        "func": nanonis_spm.Nanonis.ZCtrl_SetpntSet,
        "args": {
            "Z-Controller setpoint": {"type": np.float32, "default": 100e-12, "user": True},
        },
    },
    "current.Get": {
        "func": nanonis_spm.Nanonis.ZCtrl_SetpntGet,
        "args": {          
        },
    },
    "fb.Set": {
        "func": nanonis_spm.Nanonis.ZCtrl_OnOffSet,
        "args": {
            "Z-Controller status": {"type": np.uint32, "default": 1, "user": True},
        },
    },
    "fb.Get": {
        "func": nanonis_spm.Nanonis.ZCtrl_OnOffGet,
        "args": {
        },
    },
    "biasSpec.Start": {
        "func": nanonis_spm.Nanonis.BiasSpectr_Start,
        "args": {
            "Get data": {"type": np.uint32, "default": 0, "user": False},
            "Save base name": {"type": str, "default": "", "user": False},
        },
    },
    "biasSpec.LimitsGet": {
        "func": nanonis_spm.Nanonis.BiasSpectr_LimitsGet,
        "args": {
        },
    },
    "biasSpec.LimitsSet": {
        "func": nanonis_spm.Nanonis.BiasSpectr_LimitsSet,
        "args": {
            "Start value (V)": {"type": np.float32, "default": 0.1, "user": True},
            "End value (V)": {"type": np.float32, "default": 1.0, "user": True},
        },
    },
    "biasSpec.SweepsSet": {
        "func": nanonis_spm.Nanonis.BiasSpectr_PropsSet,
        "args": {
            "Save all": {"type": np.uint16, "default": 1, "user": False},
            "Number of sweeps": {"type": np.int32, "default": 0, "user": True},
            "Backward sweeps": {"type": np.uint16, "default": 0, "user": False},
            "Number of points": {"type": np.int32, "default": 0, "user": False},
            "Z offset (m)": {"type": np.float32, "default": 0, "user": False},
            "Autosave": {"type": np.uint16, "default": 0, "user": False},
            "Show save dialog": {"type": np.uint16, "default": 0, "user": False}
        },
    },
    "biasSpec.PointsSet": {
        "func": nanonis_spm.Nanonis.BiasSpectr_PropsSet,
        "args": {
            "Save all": {"type": np.uint16, "default": 1, "user": False},
            "Number of sweeps": {"type": np.int32, "default": 0, "user": False},
            "Backward sweeps": {"type": np.uint16, "default": 0, "user": False},
            "Number of points": {"type": np.int32, "default": 0, "user": True},
            "Z offset (m)": {"type": np.float32, "default": 0, "user": False},
            "Autosave": {"type": np.uint16, "default": 0, "user": False},
            "Show save dialog": {"type": np.uint16, "default": 0, "user": False}
        },
    },
    "scan.Start": {
        "func": nanonis_spm.Nanonis.Scan_Action,
        "args": {
            "Scan action": {"type": np.uint16, "default": 0, "user": False},
            "Scan direction": {"type": np.uint32, "default": 0, "user": False},
        },
    },
    "scan.Wait": {
        "func": nanonis_spm.Nanonis.Scan_WaitEndOfScan,
        "args": {
            "Timeout (ms)": {"type": np.int32, "default": -1, "user": False},
        },
    },
    "lockin.PhaseSet": {
        "func": nanonis_spm.Nanonis.LockIn_DemodPhasSet,
        "args": {
            "Demodulator number": {"type": np.int32, "default": 1, "user": False},
            "Phase (deg)": {"type": np.float32, "default": 0.0, "user": True},
        },
    },
    "lockin.PhaseGet": {
        "func": nanonis_spm.Nanonis.LockIn_DemodPhasGet,
        "args": {
            "Demodulator number": {"type": np.int32, "default": 1, "user": False},        
        },
    },
    "lockin.AmplSet": {
        "func": nanonis_spm.Nanonis.LockIn_ModAmpSet,
        "args": {
            "Modulator number": {"type": np.int32, "default": 1, "user": False},
            "Amplitude": {"type": np.float32, "default": 1e-3, "user": True},
        },
    },
    "lockin.AmplGet": {
        "func": nanonis_spm.Nanonis.LockIn_ModAmpGet,
        "args": {
            "Modulator number": {"type": np.int32, "default": 1, "user": False}, 
        },
    },
    "lockin.FreqSet": {
        "func": nanonis_spm.Nanonis.LockIn_ModPhasFreqSet,
        "args": {
            "Modulator number": {"type": np.int32, "default": 1, "user": False},
            "Frequency (Hz)": {"type": np.float32, "default": 187.0, "user": True},
        },
    },
    "lockin.FreqGet": {
        "func": nanonis_spm.Nanonis.LockIn_ModPhasFreqGet,
        "args": {
            "Modulator number": {"type": np.int32, "default": 1, "user": False}, 
        },
    },
    "lockin.ModSet": {
        "func": nanonis_spm.Nanonis.LockIn_ModOnOffSet,
        "args": {
            "Modulator number": {"type": np.int32, "default": 1, "user": False},
            "Lock-In On/Off": {"type": np.uint32, "default": 1, "user": True},
        },
    },
    "atomtrack.ModSet": {
        "func": nanonis_spm.Nanonis.AtomTrack_CtrlSet,
        "args": {
            "AT control": {"type": np.uint16, "default": 0, "user": False},
            "Status": {"type": np.uint16, "default": 0, "user": True},
        },
    },
    "atomtrack.CtrlSet": {
        "func": nanonis_spm.Nanonis.AtomTrack_CtrlSet,
        "args": {
             "AT control": {"type": np.uint16, "default": 1, "user": False},
            "Status": {"type": np.uint16, "default": 0, "user": True},
        },
    },
    "atomtrack.DriftMeasSet": {
        "func": nanonis_spm.Nanonis.AtomTrack_CtrlSet,
        "args": {
             "AT control": {"type": np.uint16, "default": 2, "user": False},
            "Status": {"type": np.uint16, "default": 0, "user": True},
        },
    },
    "atomtrack.DriftComp": {
        "func": nanonis_spm.Nanonis.AtomTrack_DriftComp,
        "args": {
        },
    },
    "withdraw": {
        "func": nanonis_spm.Nanonis.ZCtrl_Withdraw,
        "args": {
            "Wait until finished": {"type": np.uint32, "default": 1, "user": False},
            "punTimeout (ms)ct": {"type": np.int32, "default": -1, "user": False},
        },
    },
    "drift.Get": {
        "func": nanonis_spm.Nanonis.Piezo_DriftCompGet,
        "args": {
        },
    },
    "drift.Set": {
        "func": nanonis_spm.Nanonis.Piezo_DriftCompSet,
        "args": {
            "Compensation status": {"type": np.uint32, "default": 1, "user": True},
            "Vx (m/s)": {"type": np.float32, "default": 0.0, "user": True},
            "Vy (m/s)": {"type": np.float32, "default": 0.0, "user": True},
            "Vz (m/s)": {"type": np.float32, "default": 0.0, "user": True},
            "Saturation limit (%)": {"type": np.float32, "default": 10.0, "user": False},
        },
    },
    "xy.Get": {
        "func": ScriptingInterface.getXY,
        "args": {
        },
    },
    "xy.Set": {
        "func": ScriptingInterface.setXY,
        "args": {
            "x (m)": {"type": np.float64, "default": 0.0, "user": True},
            "y (m)": {"type": np.float64, "default": 0.0, "user": True},
        },
    },
    "z.Get": {
        "func": ScriptingInterface.getZ,
        "args": {
        },
    },
    "z.Set": {
        "func": ScriptingInterface.setZ,
        "args": {
            "z (m)": {"type": np.float32, "default": 0.0, "user": True},
        },
    },
    "x.Add": {
        "func": ScriptingInterface.addX,
        "args": {
            "dx (m)": {"type": np.float64, "default": 0.0, "user": True},
        },
    },
    "y.Add": {
        "func": ScriptingInterface.addY,
        "args": {
            "dy (m)": {"type": np.float64, "default": 0.0, "user": True},
        },
    },
    "z.Add": {
        "func": ScriptingInterface.addZ,
        "args": {
            "dz (m)": {"type": np.float32, "default": 0.0, "user": True},
        },
    },
    "wait": {
        "func": ScriptingInterface.wait,
        "args": {
            "Time (s)": {"type": np.uint32, "default": 5, "user": True},
        },
    },
    "bias.Add": {
        "func": ScriptingInterface.addBias,
        "args": {
            "Bias value (V)": {"type": np.float32, "default": 0.1, "user": True},
        },
    },
    "current.Add": {
        "func": ScriptingInterface.addCurrent,
        "args": {
            "Current value (A)": {"type": np.float32, "default": 50e-12, "user": True},
        },
    },
    "drift.correctZ": {
        "func": ScriptingInterface.correctZDrift,
        "args": {
            "Time (s)": {"type": np.uint32, "default": 5, "user": True},
        },
    },
    "QuPe.FreqSet": {
        "func": lambda freq: TCPClient("QuPe").send("setFrequency", [freq]),
        "args": {
            "Frequency (Hz)": {"type": np.float32, "default": 1e9, "user": True},
        },
    },
}
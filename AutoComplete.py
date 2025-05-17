# Copyright (c) 2022-2025 Taner Esat <t.esat@fz-juelich.de>

from PySide6 import QtGui
from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QCompleter, QPlainTextEdit

from PyNanonis import NanonisInterface
import config as cfg

class TextEditAutoComplete(QPlainTextEdit):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.nni = NanonisInterface()
        completer = QCompleter(self.getCmdList())
        completer.activated.connect(self.insert_completion)
        completer.setWidget(self)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseSensitive)
        self.completer = completer
        self.textChanged.connect(self.complete)

    def getCmdList(self):
        cmds = ['repeat', 'end']
        self.commandList = self.nni.commandList
        self.specialCommandList = self.nni.loadCommandList(cfg.JSON_SPECIALCMD)
        self.externalInterfacesCommandLists = self.nni.loadExternalInterfaceCommandLists(cfg.FOLDER_EXTCMD)
        for cmd in self.commandList.keys():
            cmds.append(cmd)
        for cmd in self.specialCommandList.keys():
            cmds.append(cmd)
        if len(self.externalInterfacesCommandLists) > 0:
            for interfaceCmds in self.externalInterfacesCommandLists:
                for cmd in interfaceCmds.keys():
                    if cmd != 'Interface':           
                        cmds.append(cmd)
        return cmds

    def insert_completion(self, completion):
        tc = self.textCursor()
        extra = len(completion) - len(self.completer.completionPrefix())
        tc.movePosition(QTextCursor.MoveOperation.Left)
        tc.movePosition(QTextCursor.MoveOperation.EndOfWord)
        tc.insertText(completion[-extra:])
        self.setTextCursor(tc)

    @property
    def text_under_cursor(self):
        tc = self.textCursor()
        tc.select(QTextCursor.SelectionType.WordUnderCursor)
        return tc.selectedText()

    def complete(self):
        prefix = self.text_under_cursor
        self.completer.setCompletionPrefix(prefix)
        popup = self.completer.popup()
        cr = self.cursorRect()
        popup.setCurrentIndex(self.completer.completionModel().index(0, 0))
        cr.setWidth(
            self.completer.popup().sizeHintForColumn(0)
            + self.completer.popup().verticalScrollBar().sizeHint().width()
        )
        self.completer.complete(cr)

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        if self.completer.popup().isVisible() and event.key() in [
            # Qt.Key.Key_Enter,
            # Qt.Key.Key_Return,
            Qt.Key.Key_Up,
            Qt.Key.Key_Down,
            Qt.Key.Key_Tab,
            Qt.Key.Key_Backtab,
        ]:
            event.ignore()
            return
        super().keyPressEvent(event)
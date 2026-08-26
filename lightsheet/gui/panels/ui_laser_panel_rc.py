# Resource object code (Python 3)
# Created by: object code
# Created by: The Resource Compiler for Qt version 6.11.2
# WARNING! All changes made in this file will be lost!

from PySide6 import QtCore

# Empty .qrc (RCC root with no resources) — pyside6-rcc generates qInitResources referencing
# these variables but omits their definitions when there are no resources.
# Defined as empty bytes so the module imports as a no-op.
qt_resource_struct = b""
qt_resource_name = b""
qt_resource_data = b""

def qInitResources():
    QtCore.qRegisterResourceData(0x03, qt_resource_struct, qt_resource_name, qt_resource_data)

def qCleanupResources():
    QtCore.qUnregisterResourceData(0x03, qt_resource_struct, qt_resource_name, qt_resource_data)

qInitResources()

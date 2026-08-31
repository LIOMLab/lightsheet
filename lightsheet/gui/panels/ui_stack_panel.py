# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'ui_stack_panel.ui'
##
## Created by: Qt User Interface Compiler version 6.11.2
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (QCoreApplication, QDate, QDateTime, QLocale,
    QMetaObject, QObject, QPoint, QRect,
    QSize, QTime, QUrl, Qt)
from PySide6.QtGui import (QBrush, QColor, QConicalGradient, QCursor,
    QFont, QFontDatabase, QGradient, QIcon,
    QImage, QKeySequence, QLinearGradient, QPainter,
    QPalette, QPixmap, QRadialGradient, QTransform)
from PySide6.QtWidgets import (QApplication, QCheckBox, QFormLayout, QFrame,
    QGroupBox, QHBoxLayout, QLabel, QPushButton,
    QSizePolicy, QSpacerItem, QVBoxLayout, QWidget)

from lightsheet.gui.widgets.field_spec_spinbox import FieldSpecSpinBox

class Ui_StackPanel(object):
    def setupUi(self, stackPanel):
        if not stackPanel.objectName():
            stackPanel.setObjectName(u"stackPanel")
        self.verticalLayout_panel = QVBoxLayout(stackPanel)
        self.verticalLayout_panel.setObjectName(u"verticalLayout_panel")
        self.groupBox_18 = QGroupBox(stackPanel)
        self.groupBox_18.setObjectName(u"groupBox_18")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.groupBox_18.sizePolicy().hasHeightForWidth())
        self.groupBox_18.setSizePolicy(sizePolicy)
        self.groupBox_18.setMinimumSize(QSize(0, 126))
        self.horizontalLayout_9 = QHBoxLayout(self.groupBox_18)
        self.horizontalLayout_9.setObjectName(u"horizontalLayout_9")
        self.verticalLayout_13 = QVBoxLayout()
        self.verticalLayout_13.setObjectName(u"verticalLayout_13")
        self.pushButton_acqStartStackMode = QPushButton(self.groupBox_18)
        self.pushButton_acqStartStackMode.setObjectName(u"pushButton_acqStartStackMode")
        sizePolicy1 = QSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.pushButton_acqStartStackMode.sizePolicy().hasHeightForWidth())
        self.pushButton_acqStartStackMode.setSizePolicy(sizePolicy1)

        self.verticalLayout_13.addWidget(self.pushButton_acqStartStackMode)

        self.horizontalLayout_89 = QHBoxLayout()
        self.horizontalLayout_89.setObjectName(u"horizontalLayout_89")
        self.horizontalLayout_89.setContentsMargins(0, -1, 0, -1)
        self.label_41 = QLabel(self.groupBox_18)
        self.label_41.setObjectName(u"label_41")
        sizePolicy2 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        sizePolicy2.setHorizontalStretch(0)
        sizePolicy2.setVerticalStretch(0)
        sizePolicy2.setHeightForWidth(self.label_41.sizePolicy().hasHeightForWidth())
        self.label_41.setSizePolicy(sizePolicy2)

        self.horizontalLayout_89.addWidget(self.label_41)

        self.label_acqNumberOfPlanes = QLabel(self.groupBox_18)
        self.label_acqNumberOfPlanes.setObjectName(u"label_acqNumberOfPlanes")
        sizePolicy3 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        sizePolicy3.setHorizontalStretch(0)
        sizePolicy3.setVerticalStretch(0)
        sizePolicy3.setHeightForWidth(self.label_acqNumberOfPlanes.sizePolicy().hasHeightForWidth())
        self.label_acqNumberOfPlanes.setSizePolicy(sizePolicy3)

        self.horizontalLayout_89.addWidget(self.label_acqNumberOfPlanes)


        self.verticalLayout_13.addLayout(self.horizontalLayout_89)

        self.verticalSpacer_7 = QSpacerItem(20, 1, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.verticalLayout_13.addItem(self.verticalSpacer_7)


        self.horizontalLayout_9.addLayout(self.verticalLayout_13)

        self.line_6 = QFrame(self.groupBox_18)
        self.line_6.setObjectName(u"line_6")
        self.line_6.setFrameShadow(QFrame.Raised)
        self.line_6.setFrameShape(QFrame.Shape.VLine)

        self.horizontalLayout_9.addWidget(self.line_6)

        self.verticalLayout_14 = QVBoxLayout()
        self.verticalLayout_14.setObjectName(u"verticalLayout_14")
        self.horizontalLayout_88 = QHBoxLayout()
        self.horizontalLayout_88.setObjectName(u"horizontalLayout_88")
        self.horizontalLayout_88.setContentsMargins(0, -1, 0, -1)
        self.label_84 = QLabel(self.groupBox_18)
        self.label_84.setObjectName(u"label_84")
        sizePolicy2.setHeightForWidth(self.label_84.sizePolicy().hasHeightForWidth())
        self.label_84.setSizePolicy(sizePolicy2)

        self.horizontalLayout_88.addWidget(self.label_84)

        self.doubleSpinBox_acqPlaneStepSize = FieldSpecSpinBox(self.groupBox_18)
        self.doubleSpinBox_acqPlaneStepSize.setObjectName(u"doubleSpinBox_acqPlaneStepSize")
        sizePolicy3.setHeightForWidth(self.doubleSpinBox_acqPlaneStepSize.sizePolicy().hasHeightForWidth())
        self.doubleSpinBox_acqPlaneStepSize.setSizePolicy(sizePolicy3)
        self.doubleSpinBox_acqPlaneStepSize.setDecimals(2)
        self.doubleSpinBox_acqPlaneStepSize.setMinimum(0.250000000000000)
        self.doubleSpinBox_acqPlaneStepSize.setMaximum(25.000000000000000)
        self.doubleSpinBox_acqPlaneStepSize.setSingleStep(0.250000000000000)
        self.doubleSpinBox_acqPlaneStepSize.setValue(5.000000000000000)

        self.horizontalLayout_88.addWidget(self.doubleSpinBox_acqPlaneStepSize)


        self.verticalLayout_14.addLayout(self.horizontalLayout_88)

        self.horizontalLayout_90 = QHBoxLayout()
        self.horizontalLayout_90.setObjectName(u"horizontalLayout_90")
        self.pushButton_acqSetFirstPlane = QPushButton(self.groupBox_18)
        self.pushButton_acqSetFirstPlane.setObjectName(u"pushButton_acqSetFirstPlane")
        sizePolicy3.setHeightForWidth(self.pushButton_acqSetFirstPlane.sizePolicy().hasHeightForWidth())
        self.pushButton_acqSetFirstPlane.setSizePolicy(sizePolicy3)
        self.pushButton_acqSetFirstPlane.setMinimumSize(QSize(140, 0))

        self.horizontalLayout_90.addWidget(self.pushButton_acqSetFirstPlane)

        self.doubleSpinBox_acqFirstPlane = FieldSpecSpinBox(self.groupBox_18)
        self.doubleSpinBox_acqFirstPlane.setObjectName(u"doubleSpinBox_acqFirstPlane")
        sizePolicy1.setHeightForWidth(self.doubleSpinBox_acqFirstPlane.sizePolicy().hasHeightForWidth())
        self.doubleSpinBox_acqFirstPlane.setSizePolicy(sizePolicy1)
        self.doubleSpinBox_acqFirstPlane.setMinimumSize(QSize(120, 0))
        self.doubleSpinBox_acqFirstPlane.setDecimals(2)
        self.doubleSpinBox_acqFirstPlane.setMinimum(-100000.000000000000000)
        self.doubleSpinBox_acqFirstPlane.setMaximum(100000.000000000000000)

        self.horizontalLayout_90.addWidget(self.doubleSpinBox_acqFirstPlane)


        self.verticalLayout_14.addLayout(self.horizontalLayout_90)

        self.horizontalLayout_91 = QHBoxLayout()
        self.horizontalLayout_91.setSpacing(6)
        self.horizontalLayout_91.setObjectName(u"horizontalLayout_91")
        self.pushButton_acqSetLastPlane = QPushButton(self.groupBox_18)
        self.pushButton_acqSetLastPlane.setObjectName(u"pushButton_acqSetLastPlane")
        sizePolicy3.setHeightForWidth(self.pushButton_acqSetLastPlane.sizePolicy().hasHeightForWidth())
        self.pushButton_acqSetLastPlane.setSizePolicy(sizePolicy3)
        self.pushButton_acqSetLastPlane.setMinimumSize(QSize(140, 0))

        self.horizontalLayout_91.addWidget(self.pushButton_acqSetLastPlane)

        self.doubleSpinBox_acqLastPlane = FieldSpecSpinBox(self.groupBox_18)
        self.doubleSpinBox_acqLastPlane.setObjectName(u"doubleSpinBox_acqLastPlane")
        sizePolicy1.setHeightForWidth(self.doubleSpinBox_acqLastPlane.sizePolicy().hasHeightForWidth())
        self.doubleSpinBox_acqLastPlane.setSizePolicy(sizePolicy1)
        self.doubleSpinBox_acqLastPlane.setMinimumSize(QSize(120, 0))
        self.doubleSpinBox_acqLastPlane.setDecimals(2)
        self.doubleSpinBox_acqLastPlane.setMinimum(-100000.000000000000000)
        self.doubleSpinBox_acqLastPlane.setMaximum(100000.000000000000000)

        self.horizontalLayout_91.addWidget(self.doubleSpinBox_acqLastPlane)


        self.verticalLayout_14.addLayout(self.horizontalLayout_91)

        self.label_stackPlanSummary = QLabel(self.groupBox_18)
        self.label_stackPlanSummary.setObjectName(u"label_stackPlanSummary")
        sizePolicy3.setHeightForWidth(self.label_stackPlanSummary.sizePolicy().hasHeightForWidth())
        self.label_stackPlanSummary.setSizePolicy(sizePolicy3)
        self.label_stackPlanSummary.setMinimumSize(QSize(0, 60))
        self.label_stackPlanSummary.setWordWrap(True)

        self.verticalLayout_14.addWidget(self.label_stackPlanSummary)

        self.verticalSpacer_9 = QSpacerItem(20, 1, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.verticalLayout_14.addItem(self.verticalSpacer_9)


        self.horizontalLayout_9.addLayout(self.verticalLayout_14)


        self.verticalLayout_panel.addWidget(self.groupBox_18)

        self.groupBox_adaptiveControl = QGroupBox(stackPanel)
        self.groupBox_adaptiveControl.setObjectName(u"groupBox_adaptiveControl")
        self.verticalLayout_adaptiveControl = QVBoxLayout(self.groupBox_adaptiveControl)
        self.verticalLayout_adaptiveControl.setObjectName(u"verticalLayout_adaptiveControl")
        self.checkBox_adaptiveEnable = QCheckBox(self.groupBox_adaptiveControl)
        self.checkBox_adaptiveEnable.setObjectName(u"checkBox_adaptiveEnable")

        self.verticalLayout_adaptiveControl.addWidget(self.checkBox_adaptiveEnable)

        self.widget_adaptiveFields = QWidget(self.groupBox_adaptiveControl)
        self.widget_adaptiveFields.setObjectName(u"widget_adaptiveFields")
        self.formLayout_adaptiveFields = QFormLayout(self.widget_adaptiveFields)
        self.formLayout_adaptiveFields.setObjectName(u"formLayout_adaptiveFields")
        self.formLayout_adaptiveFields.setContentsMargins(0, 0, 0, 0)
        self.label_adaptiveMinExposure = QLabel(self.widget_adaptiveFields)
        self.label_adaptiveMinExposure.setObjectName(u"label_adaptiveMinExposure")

        self.formLayout_adaptiveFields.setWidget(0, QFormLayout.ItemRole.LabelRole, self.label_adaptiveMinExposure)

        self.doubleSpinBox_adaptiveMinExposure = FieldSpecSpinBox(self.widget_adaptiveFields)
        self.doubleSpinBox_adaptiveMinExposure.setObjectName(u"doubleSpinBox_adaptiveMinExposure")
        self.doubleSpinBox_adaptiveMinExposure.setDecimals(0)
        self.doubleSpinBox_adaptiveMinExposure.setMinimum(1.000000000000000)
        self.doubleSpinBox_adaptiveMinExposure.setMaximum(1000.000000000000000)
        self.doubleSpinBox_adaptiveMinExposure.setSingleStep(1.000000000000000)
        self.doubleSpinBox_adaptiveMinExposure.setValue(1.000000000000000)

        self.formLayout_adaptiveFields.setWidget(0, QFormLayout.ItemRole.FieldRole, self.doubleSpinBox_adaptiveMinExposure)

        self.label_adaptiveMaxExposure = QLabel(self.widget_adaptiveFields)
        self.label_adaptiveMaxExposure.setObjectName(u"label_adaptiveMaxExposure")

        self.formLayout_adaptiveFields.setWidget(1, QFormLayout.ItemRole.LabelRole, self.label_adaptiveMaxExposure)

        self.doubleSpinBox_adaptiveMaxExposure = FieldSpecSpinBox(self.widget_adaptiveFields)
        self.doubleSpinBox_adaptiveMaxExposure.setObjectName(u"doubleSpinBox_adaptiveMaxExposure")
        self.doubleSpinBox_adaptiveMaxExposure.setDecimals(0)
        self.doubleSpinBox_adaptiveMaxExposure.setMinimum(1.000000000000000)
        self.doubleSpinBox_adaptiveMaxExposure.setMaximum(1000.000000000000000)
        self.doubleSpinBox_adaptiveMaxExposure.setSingleStep(1.000000000000000)
        self.doubleSpinBox_adaptiveMaxExposure.setValue(1000.000000000000000)

        self.formLayout_adaptiveFields.setWidget(1, QFormLayout.ItemRole.FieldRole, self.doubleSpinBox_adaptiveMaxExposure)

        self.label_adaptiveLaser1MinPower = QLabel(self.widget_adaptiveFields)
        self.label_adaptiveLaser1MinPower.setObjectName(u"label_adaptiveLaser1MinPower")

        self.formLayout_adaptiveFields.setWidget(2, QFormLayout.ItemRole.LabelRole, self.label_adaptiveLaser1MinPower)

        self.doubleSpinBox_adaptiveLaser1MinPower = FieldSpecSpinBox(self.widget_adaptiveFields)
        self.doubleSpinBox_adaptiveLaser1MinPower.setObjectName(u"doubleSpinBox_adaptiveLaser1MinPower")
        self.doubleSpinBox_adaptiveLaser1MinPower.setDecimals(1)
        self.doubleSpinBox_adaptiveLaser1MinPower.setMinimum(0.000000000000000)
        self.doubleSpinBox_adaptiveLaser1MinPower.setMaximum(150.000000000000000)
        self.doubleSpinBox_adaptiveLaser1MinPower.setSingleStep(0.500000000000000)
        self.doubleSpinBox_adaptiveLaser1MinPower.setValue(0.000000000000000)

        self.formLayout_adaptiveFields.setWidget(2, QFormLayout.ItemRole.FieldRole, self.doubleSpinBox_adaptiveLaser1MinPower)

        self.label_adaptiveLaser1MaxPower = QLabel(self.widget_adaptiveFields)
        self.label_adaptiveLaser1MaxPower.setObjectName(u"label_adaptiveLaser1MaxPower")

        self.formLayout_adaptiveFields.setWidget(3, QFormLayout.ItemRole.LabelRole, self.label_adaptiveLaser1MaxPower)

        self.doubleSpinBox_adaptiveLaser1MaxPower = FieldSpecSpinBox(self.widget_adaptiveFields)
        self.doubleSpinBox_adaptiveLaser1MaxPower.setObjectName(u"doubleSpinBox_adaptiveLaser1MaxPower")
        self.doubleSpinBox_adaptiveLaser1MaxPower.setDecimals(1)
        self.doubleSpinBox_adaptiveLaser1MaxPower.setMinimum(0.000000000000000)
        self.doubleSpinBox_adaptiveLaser1MaxPower.setMaximum(150.000000000000000)
        self.doubleSpinBox_adaptiveLaser1MaxPower.setSingleStep(0.500000000000000)
        self.doubleSpinBox_adaptiveLaser1MaxPower.setValue(5.000000000000000)

        self.formLayout_adaptiveFields.setWidget(3, QFormLayout.ItemRole.FieldRole, self.doubleSpinBox_adaptiveLaser1MaxPower)

        self.label_adaptiveLaser2MinPower = QLabel(self.widget_adaptiveFields)
        self.label_adaptiveLaser2MinPower.setObjectName(u"label_adaptiveLaser2MinPower")

        self.formLayout_adaptiveFields.setWidget(4, QFormLayout.ItemRole.LabelRole, self.label_adaptiveLaser2MinPower)

        self.doubleSpinBox_adaptiveLaser2MinPower = FieldSpecSpinBox(self.widget_adaptiveFields)
        self.doubleSpinBox_adaptiveLaser2MinPower.setObjectName(u"doubleSpinBox_adaptiveLaser2MinPower")
        self.doubleSpinBox_adaptiveLaser2MinPower.setDecimals(1)
        self.doubleSpinBox_adaptiveLaser2MinPower.setMinimum(0.000000000000000)
        self.doubleSpinBox_adaptiveLaser2MinPower.setMaximum(150.000000000000000)
        self.doubleSpinBox_adaptiveLaser2MinPower.setSingleStep(0.500000000000000)
        self.doubleSpinBox_adaptiveLaser2MinPower.setValue(0.000000000000000)

        self.formLayout_adaptiveFields.setWidget(4, QFormLayout.ItemRole.FieldRole, self.doubleSpinBox_adaptiveLaser2MinPower)

        self.label_adaptiveLaser2MaxPower = QLabel(self.widget_adaptiveFields)
        self.label_adaptiveLaser2MaxPower.setObjectName(u"label_adaptiveLaser2MaxPower")

        self.formLayout_adaptiveFields.setWidget(5, QFormLayout.ItemRole.LabelRole, self.label_adaptiveLaser2MaxPower)

        self.doubleSpinBox_adaptiveLaser2MaxPower = FieldSpecSpinBox(self.widget_adaptiveFields)
        self.doubleSpinBox_adaptiveLaser2MaxPower.setObjectName(u"doubleSpinBox_adaptiveLaser2MaxPower")
        self.doubleSpinBox_adaptiveLaser2MaxPower.setDecimals(1)
        self.doubleSpinBox_adaptiveLaser2MaxPower.setMinimum(0.000000000000000)
        self.doubleSpinBox_adaptiveLaser2MaxPower.setMaximum(150.000000000000000)
        self.doubleSpinBox_adaptiveLaser2MaxPower.setSingleStep(0.500000000000000)
        self.doubleSpinBox_adaptiveLaser2MaxPower.setValue(150.000000000000000)

        self.formLayout_adaptiveFields.setWidget(5, QFormLayout.ItemRole.FieldRole, self.doubleSpinBox_adaptiveLaser2MaxPower)

        self.label_adaptiveTargetBandLo = QLabel(self.widget_adaptiveFields)
        self.label_adaptiveTargetBandLo.setObjectName(u"label_adaptiveTargetBandLo")

        self.formLayout_adaptiveFields.setWidget(6, QFormLayout.ItemRole.LabelRole, self.label_adaptiveTargetBandLo)

        self.doubleSpinBox_adaptiveTargetBandLo = FieldSpecSpinBox(self.widget_adaptiveFields)
        self.doubleSpinBox_adaptiveTargetBandLo.setObjectName(u"doubleSpinBox_adaptiveTargetBandLo")
        self.doubleSpinBox_adaptiveTargetBandLo.setDecimals(0)
        self.doubleSpinBox_adaptiveTargetBandLo.setMinimum(0.000000000000000)
        self.doubleSpinBox_adaptiveTargetBandLo.setMaximum(100.000000000000000)
        self.doubleSpinBox_adaptiveTargetBandLo.setSingleStep(1.000000000000000)
        self.doubleSpinBox_adaptiveTargetBandLo.setValue(90.000000000000000)

        self.formLayout_adaptiveFields.setWidget(6, QFormLayout.ItemRole.FieldRole, self.doubleSpinBox_adaptiveTargetBandLo)

        self.label_adaptiveTargetBandHi = QLabel(self.widget_adaptiveFields)
        self.label_adaptiveTargetBandHi.setObjectName(u"label_adaptiveTargetBandHi")

        self.formLayout_adaptiveFields.setWidget(7, QFormLayout.ItemRole.LabelRole, self.label_adaptiveTargetBandHi)

        self.doubleSpinBox_adaptiveTargetBandHi = FieldSpecSpinBox(self.widget_adaptiveFields)
        self.doubleSpinBox_adaptiveTargetBandHi.setObjectName(u"doubleSpinBox_adaptiveTargetBandHi")
        self.doubleSpinBox_adaptiveTargetBandHi.setDecimals(0)
        self.doubleSpinBox_adaptiveTargetBandHi.setMinimum(0.000000000000000)
        self.doubleSpinBox_adaptiveTargetBandHi.setMaximum(100.000000000000000)
        self.doubleSpinBox_adaptiveTargetBandHi.setSingleStep(1.000000000000000)
        self.doubleSpinBox_adaptiveTargetBandHi.setValue(95.000000000000000)

        self.formLayout_adaptiveFields.setWidget(7, QFormLayout.ItemRole.FieldRole, self.doubleSpinBox_adaptiveTargetBandHi)

        self.label_adaptiveReacquireThreshold = QLabel(self.widget_adaptiveFields)
        self.label_adaptiveReacquireThreshold.setObjectName(u"label_adaptiveReacquireThreshold")

        self.formLayout_adaptiveFields.setWidget(8, QFormLayout.ItemRole.LabelRole, self.label_adaptiveReacquireThreshold)

        self.doubleSpinBox_adaptiveReacquireThreshold = FieldSpecSpinBox(self.widget_adaptiveFields)
        self.doubleSpinBox_adaptiveReacquireThreshold.setObjectName(u"doubleSpinBox_adaptiveReacquireThreshold")
        self.doubleSpinBox_adaptiveReacquireThreshold.setDecimals(1)
        self.doubleSpinBox_adaptiveReacquireThreshold.setMinimum(0.000000000000000)
        self.doubleSpinBox_adaptiveReacquireThreshold.setMaximum(50.000000000000000)
        self.doubleSpinBox_adaptiveReacquireThreshold.setSingleStep(0.500000000000000)
        self.doubleSpinBox_adaptiveReacquireThreshold.setValue(8.000000000000000)

        self.formLayout_adaptiveFields.setWidget(8, QFormLayout.ItemRole.FieldRole, self.doubleSpinBox_adaptiveReacquireThreshold)

        self.label_adaptiveBlockSizeN = QLabel(self.widget_adaptiveFields)
        self.label_adaptiveBlockSizeN.setObjectName(u"label_adaptiveBlockSizeN")

        self.formLayout_adaptiveFields.setWidget(9, QFormLayout.ItemRole.LabelRole, self.label_adaptiveBlockSizeN)

        self.doubleSpinBox_adaptiveBlockSizeN = FieldSpecSpinBox(self.widget_adaptiveFields)
        self.doubleSpinBox_adaptiveBlockSizeN.setObjectName(u"doubleSpinBox_adaptiveBlockSizeN")
        self.doubleSpinBox_adaptiveBlockSizeN.setDecimals(0)
        self.doubleSpinBox_adaptiveBlockSizeN.setMinimum(1.000000000000000)
        self.doubleSpinBox_adaptiveBlockSizeN.setMaximum(100.000000000000000)
        self.doubleSpinBox_adaptiveBlockSizeN.setSingleStep(1.000000000000000)
        self.doubleSpinBox_adaptiveBlockSizeN.setValue(8.000000000000000)

        self.formLayout_adaptiveFields.setWidget(9, QFormLayout.ItemRole.FieldRole, self.doubleSpinBox_adaptiveBlockSizeN)

        self.label_adaptiveKp = QLabel(self.widget_adaptiveFields)
        self.label_adaptiveKp.setObjectName(u"label_adaptiveKp")

        self.formLayout_adaptiveFields.setWidget(10, QFormLayout.ItemRole.LabelRole, self.label_adaptiveKp)

        self.doubleSpinBox_adaptiveKp = FieldSpecSpinBox(self.widget_adaptiveFields)
        self.doubleSpinBox_adaptiveKp.setObjectName(u"doubleSpinBox_adaptiveKp")
        self.doubleSpinBox_adaptiveKp.setDecimals(3)
        self.doubleSpinBox_adaptiveKp.setMinimum(0.000000000000000)
        self.doubleSpinBox_adaptiveKp.setMaximum(5.000000000000000)
        self.doubleSpinBox_adaptiveKp.setSingleStep(0.050000000000000)
        self.doubleSpinBox_adaptiveKp.setValue(0.400000000000000)

        self.formLayout_adaptiveFields.setWidget(10, QFormLayout.ItemRole.FieldRole, self.doubleSpinBox_adaptiveKp)

        self.label_adaptiveKi = QLabel(self.widget_adaptiveFields)
        self.label_adaptiveKi.setObjectName(u"label_adaptiveKi")

        self.formLayout_adaptiveFields.setWidget(11, QFormLayout.ItemRole.LabelRole, self.label_adaptiveKi)

        self.doubleSpinBox_adaptiveKi = FieldSpecSpinBox(self.widget_adaptiveFields)
        self.doubleSpinBox_adaptiveKi.setObjectName(u"doubleSpinBox_adaptiveKi")
        self.doubleSpinBox_adaptiveKi.setDecimals(3)
        self.doubleSpinBox_adaptiveKi.setMinimum(0.000000000000000)
        self.doubleSpinBox_adaptiveKi.setMaximum(1.000000000000000)
        self.doubleSpinBox_adaptiveKi.setSingleStep(0.010000000000000)
        self.doubleSpinBox_adaptiveKi.setValue(0.050000000000000)

        self.formLayout_adaptiveFields.setWidget(11, QFormLayout.ItemRole.FieldRole, self.doubleSpinBox_adaptiveKi)

        self.label_adaptivePilotCount = QLabel(self.widget_adaptiveFields)
        self.label_adaptivePilotCount.setObjectName(u"label_adaptivePilotCount")

        self.formLayout_adaptiveFields.setWidget(12, QFormLayout.ItemRole.LabelRole, self.label_adaptivePilotCount)

        self.doubleSpinBox_adaptivePilotCount = FieldSpecSpinBox(self.widget_adaptiveFields)
        self.doubleSpinBox_adaptivePilotCount.setObjectName(u"doubleSpinBox_adaptivePilotCount")
        self.doubleSpinBox_adaptivePilotCount.setDecimals(0)
        self.doubleSpinBox_adaptivePilotCount.setMinimum(0.000000000000000)
        self.doubleSpinBox_adaptivePilotCount.setMaximum(50.000000000000000)
        self.doubleSpinBox_adaptivePilotCount.setSingleStep(1.000000000000000)
        self.doubleSpinBox_adaptivePilotCount.setValue(5.000000000000000)

        self.formLayout_adaptiveFields.setWidget(12, QFormLayout.ItemRole.FieldRole, self.doubleSpinBox_adaptivePilotCount)

        self.label_adaptiveShutterModeHint = QLabel(self.widget_adaptiveFields)
        self.label_adaptiveShutterModeHint.setObjectName(u"label_adaptiveShutterModeHint")
        self.label_adaptiveShutterModeHint.setWordWrap(True)

        self.formLayout_adaptiveFields.setWidget(13, QFormLayout.ItemRole.SpanningRole, self.label_adaptiveShutterModeHint)


        self.verticalLayout_adaptiveControl.addWidget(self.widget_adaptiveFields)


        self.verticalLayout_panel.addWidget(self.groupBox_adaptiveControl)

        self.groupBox_acquisitionQueue = QGroupBox(stackPanel)
        self.groupBox_acquisitionQueue.setObjectName(u"groupBox_acquisitionQueue")
        self.verticalLayout_acquisitionQueue = QVBoxLayout(self.groupBox_acquisitionQueue)
        self.verticalLayout_acquisitionQueue.setObjectName(u"verticalLayout_acquisitionQueue")

        self.verticalLayout_panel.addWidget(self.groupBox_acquisitionQueue)


        self.retranslateUi(stackPanel)

        QMetaObject.connectSlotsByName(stackPanel)
    # setupUi

    def retranslateUi(self, stackPanel):
        self.groupBox_18.setTitle(QCoreApplication.translate("StackPanel", u"Automatic Acquisition", None))
#if QT_CONFIG(tooltip)
        self.pushButton_acqStartStackMode.setToolTip(QCoreApplication.translate("StackPanel", u"Start multiple images acquisition", None))
#endif // QT_CONFIG(tooltip)
        self.pushButton_acqStartStackMode.setText(QCoreApplication.translate("StackPanel", u"Start Stack Mode", None))
#if QT_CONFIG(shortcut)
        self.pushButton_acqStartStackMode.setShortcut(QCoreApplication.translate("StackPanel", u"Ctrl+K", None))
#endif // QT_CONFIG(shortcut)
#if QT_CONFIG(tooltip)
        self.label_41.setToolTip(QCoreApplication.translate("StackPanel", u"Number of planes of stack acquisition", None))
#endif // QT_CONFIG(tooltip)
        self.label_41.setText(QCoreApplication.translate("StackPanel", u"Number Of Planes:", None))
        self.label_acqNumberOfPlanes.setText(QCoreApplication.translate("StackPanel", u"N/A", None))
#if QT_CONFIG(tooltip)
        self.label_84.setToolTip(QCoreApplication.translate("StackPanel", u"The plane step for stack acquisition", None))
#endif // QT_CONFIG(tooltip)
        self.label_84.setText(QCoreApplication.translate("StackPanel", u"Plane Step:", None))
#if QT_CONFIG(tooltip)
        self.doubleSpinBox_acqPlaneStepSize.setToolTip(QCoreApplication.translate("StackPanel", u"Step between adjacent z-planes in the stack. Unit: the active unit (\u03bcm/mm). Valid range: >0 (a zero step is rejected). Effect: smaller steps = finer z-resolution but more frames and a longer acquisition.", None))
#endif // QT_CONFIG(tooltip)
        self.doubleSpinBox_acqPlaneStepSize.setSuffix(QCoreApplication.translate("StackPanel", u" \u03bcm", None))
#if QT_CONFIG(tooltip)
        self.pushButton_acqSetFirstPlane.setToolTip(QCoreApplication.translate("StackPanel", u"Set the current horizontal position as starting point for stack acquisition", None))
#endif // QT_CONFIG(tooltip)
        self.pushButton_acqSetFirstPlane.setText(QCoreApplication.translate("StackPanel", u"Set Starting Plane", None))
#if QT_CONFIG(tooltip)
        self.doubleSpinBox_acqFirstPlane.setToolTip(QCoreApplication.translate("StackPanel", u"Stack start position. Unit: the active unit (\u03bcm/mm). Set via the Set button (reads the current motor position) or type directly. Valid range: the stage travel limits (reject-and-beep if out of range).", None))
#endif // QT_CONFIG(tooltip)
        self.doubleSpinBox_acqFirstPlane.setSuffix(QCoreApplication.translate("StackPanel", u" \u03bcm", None))
#if QT_CONFIG(tooltip)
        self.pushButton_acqSetLastPlane.setToolTip(QCoreApplication.translate("StackPanel", u"Set the current horizontal position as ending point for stack acquisition", None))
#endif // QT_CONFIG(tooltip)
        self.pushButton_acqSetLastPlane.setText(QCoreApplication.translate("StackPanel", u"Set Ending Plane", None))
#if QT_CONFIG(tooltip)
        self.doubleSpinBox_acqLastPlane.setToolTip(QCoreApplication.translate("StackPanel", u"Stack end position. Unit: the active unit (\u03bcm/mm). Set via the Set button (reads the current motor position) or type directly. Valid range: the stage travel limits (reject-and-beep if out of range).", None))
#endif // QT_CONFIG(tooltip)
        self.doubleSpinBox_acqLastPlane.setSuffix(QCoreApplication.translate("StackPanel", u" \u03bcm", None))
        self.label_stackPlanSummary.setText(QCoreApplication.translate("StackPanel", u"No stack configured. Drive the stage to the start position and press Set, or type start/end positions and a step.", None))
        self.groupBox_adaptiveControl.setTitle(QCoreApplication.translate("StackPanel", u"Adaptive Control", None))
#if QT_CONFIG(tooltip)
        self.checkBox_adaptiveEnable.setToolTip(QCoreApplication.translate("StackPanel", u"Enable per-plane adaptive exposure + laser power control. When unchecked the stack runs with fixed exposure/power; when checked the controller adjusts per plane from observed intensity within the configured bounds.", None))
#endif // QT_CONFIG(tooltip)
        self.checkBox_adaptiveEnable.setText(QCoreApplication.translate("StackPanel", u"Adaptive exposure & power control", None))
        self.label_adaptiveMinExposure.setText(QCoreApplication.translate("StackPanel", u"Min Exposure:", None))
        self.label_adaptiveMaxExposure.setText(QCoreApplication.translate("StackPanel", u"Max Exposure:", None))
        self.label_adaptiveLaser1MinPower.setText(QCoreApplication.translate("StackPanel", u"Laser1 Min Power:", None))
        self.label_adaptiveLaser1MaxPower.setText(QCoreApplication.translate("StackPanel", u"Laser1 Max Power:", None))
        self.label_adaptiveLaser2MinPower.setText(QCoreApplication.translate("StackPanel", u"Laser2 Min Power:", None))
        self.label_adaptiveLaser2MaxPower.setText(QCoreApplication.translate("StackPanel", u"Laser2 Max Power:", None))
        self.label_adaptiveTargetBandLo.setText(QCoreApplication.translate("StackPanel", u"Target Band Lo:", None))
        self.label_adaptiveTargetBandHi.setText(QCoreApplication.translate("StackPanel", u"Target Band Hi:", None))
        self.label_adaptiveReacquireThreshold.setText(QCoreApplication.translate("StackPanel", u"Reacquire Threshold:", None))
        self.label_adaptiveBlockSizeN.setText(QCoreApplication.translate("StackPanel", u"Block Size N:", None))
        self.label_adaptiveKp.setText(QCoreApplication.translate("StackPanel", u"Kp:", None))
        self.label_adaptiveKi.setText(QCoreApplication.translate("StackPanel", u"Ki:", None))
        self.label_adaptivePilotCount.setText(QCoreApplication.translate("StackPanel", u"Pilot Count:", None))
        self.label_adaptiveShutterModeHint.setText(QCoreApplication.translate("StackPanel", u"Rolling shutter \u2014 exposure bound in milliseconds.", None))
        self.groupBox_acquisitionQueue.setTitle(QCoreApplication.translate("StackPanel", u"Acquisition Queue", None))
        pass
    # retranslateUi


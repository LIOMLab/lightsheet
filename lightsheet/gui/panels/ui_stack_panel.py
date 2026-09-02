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
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFrame,
    QGridLayout, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QSizePolicy, QSpacerItem,
    QVBoxLayout, QWidget)

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
        self.line_6.setFrameShadow(QFrame.Shadow.Raised)
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
        self.doubleSpinBox_acqPlaneStepSize.setValue(6.500000000000000)

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
        self.gridLayout_adaptiveFields = QGridLayout(self.widget_adaptiveFields)
        self.gridLayout_adaptiveFields.setObjectName(u"gridLayout_adaptiveFields")
        self.gridLayout_adaptiveFields.setContentsMargins(0, 0, 0, 0)
        self.label_adaptiveMinExposure = QLabel(self.widget_adaptiveFields)
        self.label_adaptiveMinExposure.setObjectName(u"label_adaptiveMinExposure")

        self.gridLayout_adaptiveFields.addWidget(self.label_adaptiveMinExposure, 0, 0, 1, 1)

        self.doubleSpinBox_adaptiveMinExposure = FieldSpecSpinBox(self.widget_adaptiveFields)
        self.doubleSpinBox_adaptiveMinExposure.setObjectName(u"doubleSpinBox_adaptiveMinExposure")
        self.doubleSpinBox_adaptiveMinExposure.setDecimals(0)
        self.doubleSpinBox_adaptiveMinExposure.setMinimum(1.000000000000000)
        self.doubleSpinBox_adaptiveMinExposure.setMaximum(10000.000000000000000)
        self.doubleSpinBox_adaptiveMinExposure.setSingleStep(1.000000000000000)
        self.doubleSpinBox_adaptiveMinExposure.setValue(1.000000000000000)

        self.gridLayout_adaptiveFields.addWidget(self.doubleSpinBox_adaptiveMinExposure, 0, 1, 1, 1)

        self.label_adaptiveMaxExposure = QLabel(self.widget_adaptiveFields)
        self.label_adaptiveMaxExposure.setObjectName(u"label_adaptiveMaxExposure")

        self.gridLayout_adaptiveFields.addWidget(self.label_adaptiveMaxExposure, 0, 2, 1, 1)

        self.doubleSpinBox_adaptiveMaxExposure = FieldSpecSpinBox(self.widget_adaptiveFields)
        self.doubleSpinBox_adaptiveMaxExposure.setObjectName(u"doubleSpinBox_adaptiveMaxExposure")
        self.doubleSpinBox_adaptiveMaxExposure.setDecimals(0)
        self.doubleSpinBox_adaptiveMaxExposure.setMinimum(1.000000000000000)
        self.doubleSpinBox_adaptiveMaxExposure.setMaximum(10000.000000000000000)
        self.doubleSpinBox_adaptiveMaxExposure.setSingleStep(1.000000000000000)
        self.doubleSpinBox_adaptiveMaxExposure.setValue(100.000000000000000)

        self.gridLayout_adaptiveFields.addWidget(self.doubleSpinBox_adaptiveMaxExposure, 0, 3, 1, 1)

        self.label_adaptiveLaser1MinPower = QLabel(self.widget_adaptiveFields)
        self.label_adaptiveLaser1MinPower.setObjectName(u"label_adaptiveLaser1MinPower")

        self.gridLayout_adaptiveFields.addWidget(self.label_adaptiveLaser1MinPower, 1, 0, 1, 1)

        self.doubleSpinBox_adaptiveLaser1MinPower = FieldSpecSpinBox(self.widget_adaptiveFields)
        self.doubleSpinBox_adaptiveLaser1MinPower.setObjectName(u"doubleSpinBox_adaptiveLaser1MinPower")
        self.doubleSpinBox_adaptiveLaser1MinPower.setDecimals(1)
        self.doubleSpinBox_adaptiveLaser1MinPower.setMinimum(0.000000000000000)
        self.doubleSpinBox_adaptiveLaser1MinPower.setMaximum(150.000000000000000)
        self.doubleSpinBox_adaptiveLaser1MinPower.setSingleStep(0.500000000000000)
        self.doubleSpinBox_adaptiveLaser1MinPower.setValue(0.000000000000000)

        self.gridLayout_adaptiveFields.addWidget(self.doubleSpinBox_adaptiveLaser1MinPower, 1, 1, 1, 1)

        self.label_adaptiveLaser1MaxPower = QLabel(self.widget_adaptiveFields)
        self.label_adaptiveLaser1MaxPower.setObjectName(u"label_adaptiveLaser1MaxPower")

        self.gridLayout_adaptiveFields.addWidget(self.label_adaptiveLaser1MaxPower, 1, 2, 1, 1)

        self.doubleSpinBox_adaptiveLaser1MaxPower = FieldSpecSpinBox(self.widget_adaptiveFields)
        self.doubleSpinBox_adaptiveLaser1MaxPower.setObjectName(u"doubleSpinBox_adaptiveLaser1MaxPower")
        self.doubleSpinBox_adaptiveLaser1MaxPower.setDecimals(1)
        self.doubleSpinBox_adaptiveLaser1MaxPower.setMinimum(0.000000000000000)
        self.doubleSpinBox_adaptiveLaser1MaxPower.setMaximum(150.000000000000000)
        self.doubleSpinBox_adaptiveLaser1MaxPower.setSingleStep(0.500000000000000)
        self.doubleSpinBox_adaptiveLaser1MaxPower.setValue(5.000000000000000)

        self.gridLayout_adaptiveFields.addWidget(self.doubleSpinBox_adaptiveLaser1MaxPower, 1, 3, 1, 1)

        self.label_adaptiveLaser2MinPower = QLabel(self.widget_adaptiveFields)
        self.label_adaptiveLaser2MinPower.setObjectName(u"label_adaptiveLaser2MinPower")

        self.gridLayout_adaptiveFields.addWidget(self.label_adaptiveLaser2MinPower, 2, 0, 1, 1)

        self.doubleSpinBox_adaptiveLaser2MinPower = FieldSpecSpinBox(self.widget_adaptiveFields)
        self.doubleSpinBox_adaptiveLaser2MinPower.setObjectName(u"doubleSpinBox_adaptiveLaser2MinPower")
        self.doubleSpinBox_adaptiveLaser2MinPower.setDecimals(1)
        self.doubleSpinBox_adaptiveLaser2MinPower.setMinimum(0.000000000000000)
        self.doubleSpinBox_adaptiveLaser2MinPower.setMaximum(150.000000000000000)
        self.doubleSpinBox_adaptiveLaser2MinPower.setSingleStep(0.500000000000000)
        self.doubleSpinBox_adaptiveLaser2MinPower.setValue(0.000000000000000)

        self.gridLayout_adaptiveFields.addWidget(self.doubleSpinBox_adaptiveLaser2MinPower, 2, 1, 1, 1)

        self.label_adaptiveLaser2MaxPower = QLabel(self.widget_adaptiveFields)
        self.label_adaptiveLaser2MaxPower.setObjectName(u"label_adaptiveLaser2MaxPower")

        self.gridLayout_adaptiveFields.addWidget(self.label_adaptiveLaser2MaxPower, 2, 2, 1, 1)

        self.doubleSpinBox_adaptiveLaser2MaxPower = FieldSpecSpinBox(self.widget_adaptiveFields)
        self.doubleSpinBox_adaptiveLaser2MaxPower.setObjectName(u"doubleSpinBox_adaptiveLaser2MaxPower")
        self.doubleSpinBox_adaptiveLaser2MaxPower.setDecimals(1)
        self.doubleSpinBox_adaptiveLaser2MaxPower.setMinimum(0.000000000000000)
        self.doubleSpinBox_adaptiveLaser2MaxPower.setMaximum(150.000000000000000)
        self.doubleSpinBox_adaptiveLaser2MaxPower.setSingleStep(0.500000000000000)
        self.doubleSpinBox_adaptiveLaser2MaxPower.setValue(150.000000000000000)

        self.gridLayout_adaptiveFields.addWidget(self.doubleSpinBox_adaptiveLaser2MaxPower, 2, 3, 1, 1)

        self.label_adaptiveShutterModeHint = QLabel(self.widget_adaptiveFields)
        self.label_adaptiveShutterModeHint.setObjectName(u"label_adaptiveShutterModeHint")
        self.label_adaptiveShutterModeHint.setWordWrap(True)

        self.gridLayout_adaptiveFields.addWidget(self.label_adaptiveShutterModeHint, 3, 0, 1, 4)


        self.verticalLayout_adaptiveControl.addWidget(self.widget_adaptiveFields)


        self.verticalLayout_panel.addWidget(self.groupBox_adaptiveControl)

        self.groupBox_focusControl = QGroupBox(stackPanel)
        self.groupBox_focusControl.setObjectName(u"groupBox_focusControl")
        self.verticalLayout_focusControl = QVBoxLayout(self.groupBox_focusControl)
        self.verticalLayout_focusControl.setObjectName(u"verticalLayout_focusControl")
        self.checkBox_focusEnable = QCheckBox(self.groupBox_focusControl)
        self.checkBox_focusEnable.setObjectName(u"checkBox_focusEnable")

        self.verticalLayout_focusControl.addWidget(self.checkBox_focusEnable)

        self.widget_focusFields = QWidget(self.groupBox_focusControl)
        self.widget_focusFields.setObjectName(u"widget_focusFields")
        self.widget_focusFields.setVisible(False)
        self.gridLayout_focusFields = QGridLayout(self.widget_focusFields)
        self.gridLayout_focusFields.setObjectName(u"gridLayout_focusFields")
        self.gridLayout_focusFields.setContentsMargins(0, 0, 0, 0)
        self.lineEdit_focusCurvePath = QLineEdit(self.widget_focusFields)
        self.lineEdit_focusCurvePath.setObjectName(u"lineEdit_focusCurvePath")

        self.gridLayout_focusFields.addWidget(self.lineEdit_focusCurvePath, 0, 0, 1, 2)

        self.pushButton_focusBrowse = QPushButton(self.widget_focusFields)
        self.pushButton_focusBrowse.setObjectName(u"pushButton_focusBrowse")

        self.gridLayout_focusFields.addWidget(self.pushButton_focusBrowse, 0, 2, 1, 1)

        self.pushButton_focusLoad = QPushButton(self.widget_focusFields)
        self.pushButton_focusLoad.setObjectName(u"pushButton_focusLoad")

        self.gridLayout_focusFields.addWidget(self.pushButton_focusLoad, 0, 3, 1, 1)

        self.doubleSpinBox_focusBlockSize = FieldSpecSpinBox(self.widget_focusFields)
        self.doubleSpinBox_focusBlockSize.setObjectName(u"doubleSpinBox_focusBlockSize")
        self.doubleSpinBox_focusBlockSize.setDecimals(0)
        self.doubleSpinBox_focusBlockSize.setMinimum(1.000000000000000)
        self.doubleSpinBox_focusBlockSize.setMaximum(100.000000000000000)
        self.doubleSpinBox_focusBlockSize.setSingleStep(1.000000000000000)
        self.doubleSpinBox_focusBlockSize.setValue(8.000000000000000)

        self.gridLayout_focusFields.addWidget(self.doubleSpinBox_focusBlockSize, 1, 0, 1, 4)

        self.checkBox_focusAutofocusResidual = QCheckBox(self.widget_focusFields)
        self.checkBox_focusAutofocusResidual.setObjectName(u"checkBox_focusAutofocusResidual")
        self.checkBox_focusAutofocusResidual.setChecked(True)

        self.gridLayout_focusFields.addWidget(self.checkBox_focusAutofocusResidual, 2, 0, 1, 4)

        self.label_focusXAxisVariable = QLabel(self.widget_focusFields)
        self.label_focusXAxisVariable.setObjectName(u"label_focusXAxisVariable")

        self.gridLayout_focusFields.addWidget(self.label_focusXAxisVariable, 3, 0, 1, 1)

        self.comboBox_focusXAxisVariable = QComboBox(self.widget_focusFields)
        self.comboBox_focusXAxisVariable.addItem("")
        self.comboBox_focusXAxisVariable.addItem("")
        self.comboBox_focusXAxisVariable.setObjectName(u"comboBox_focusXAxisVariable")

        self.gridLayout_focusFields.addWidget(self.comboBox_focusXAxisVariable, 3, 1, 1, 3)

        self.label_focusStatus = QLabel(self.widget_focusFields)
        self.label_focusStatus.setObjectName(u"label_focusStatus")

        self.gridLayout_focusFields.addWidget(self.label_focusStatus, 4, 0, 1, 4)

        self.label_focusBlockHint = QLabel(self.widget_focusFields)
        self.label_focusBlockHint.setObjectName(u"label_focusBlockHint")
        self.label_focusBlockHint.setWordWrap(True)

        self.gridLayout_focusFields.addWidget(self.label_focusBlockHint, 5, 0, 1, 4)


        self.verticalLayout_focusControl.addWidget(self.widget_focusFields)


        self.verticalLayout_panel.addWidget(self.groupBox_focusControl)

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
        self.label_adaptiveLaser1MinPower.setText(QCoreApplication.translate("StackPanel", u"L1 Min Power:", None))
        self.label_adaptiveLaser1MaxPower.setText(QCoreApplication.translate("StackPanel", u"L1 Max Power:", None))
        self.label_adaptiveLaser2MinPower.setText(QCoreApplication.translate("StackPanel", u"L2 Min Power:", None))
        self.label_adaptiveLaser2MaxPower.setText(QCoreApplication.translate("StackPanel", u"L2 Max Power:", None))
        self.label_adaptiveShutterModeHint.setText(QCoreApplication.translate("StackPanel", u"Rolling shutter \u2014 exposure bound in milliseconds.", None))
        self.groupBox_focusControl.setTitle(QCoreApplication.translate("StackPanel", u"Focus Control", None))
#if QT_CONFIG(tooltip)
        self.checkBox_focusEnable.setToolTip(QCoreApplication.translate("StackPanel", u"Enable camera focus compensation during the stack. When unchecked the stack runs with fixed camera position.", None))
#endif // QT_CONFIG(tooltip)
        self.checkBox_focusEnable.setText(QCoreApplication.translate("StackPanel", u"Camera focus compensation", None))
#if QT_CONFIG(tooltip)
        self.lineEdit_focusCurvePath.setToolTip(QCoreApplication.translate("StackPanel", u"Absolute or relative path to the JSON focus calibration file.", None))
#endif // QT_CONFIG(tooltip)
        self.pushButton_focusBrowse.setText(QCoreApplication.translate("StackPanel", u"Browse...", None))
        self.pushButton_focusLoad.setText(QCoreApplication.translate("StackPanel", u"Load Calibration", None))
#if QT_CONFIG(tooltip)
        self.doubleSpinBox_focusBlockSize.setToolTip(QCoreApplication.translate("StackPanel", u"Number of planes between camera focus updates. The last applied position is held between blocks.", None))
#endif // QT_CONFIG(tooltip)
#if QT_CONFIG(tooltip)
        self.checkBox_focusAutofocusResidual.setToolTip(QCoreApplication.translate("StackPanel", u"Enable per-block sharpness-based residual correction on top of the feedforward calibration curve.", None))
#endif // QT_CONFIG(tooltip)
        self.checkBox_focusAutofocusResidual.setText(QCoreApplication.translate("StackPanel", u"Enable autofocus residual", None))
        self.label_focusXAxisVariable.setText(QCoreApplication.translate("StackPanel", u"X axis:", None))
        self.comboBox_focusXAxisVariable.setItemText(0, QCoreApplication.translate("StackPanel", u"Plane", None))
        self.comboBox_focusXAxisVariable.setItemText(1, QCoreApplication.translate("StackPanel", u"Stage position (mm)", None))

        self.label_focusStatus.setText(QCoreApplication.translate("StackPanel", u"Not armed \u2014 no file loaded", None))
        self.label_focusBlockHint.setText(QCoreApplication.translate("StackPanel", u"Camera focus is updated once every 8 planes. The last applied position is held between blocks.", None))
        self.groupBox_acquisitionQueue.setTitle(QCoreApplication.translate("StackPanel", u"Acquisition Queue", None))
        pass
    # retranslateUi


# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'ui_motor_panel.ui'
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
from PySide6.QtWidgets import (QApplication, QFrame, QGridLayout, QGroupBox,
    QHBoxLayout, QLabel, QPushButton, QSizePolicy,
    QSpacerItem, QVBoxLayout, QWidget)

from lightsheet.gui.widgets.field_spec_spinbox import FieldSpecSpinBox

class Ui_MotorPanel(object):
    def setupUi(self, motorPanel):
        if not motorPanel.objectName():
            motorPanel.setObjectName(u"motorPanel")
        self.verticalLayout_panel = QVBoxLayout(motorPanel)
        self.verticalLayout_panel.setObjectName(u"verticalLayout_panel")
        self.groupBox_SampleMovement = QGroupBox(motorPanel)
        self.groupBox_SampleMovement.setObjectName(u"groupBox_SampleMovement")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.groupBox_SampleMovement.sizePolicy().hasHeightForWidth())
        self.groupBox_SampleMovement.setSizePolicy(sizePolicy)
        self.groupBox_SampleMovement.setMinimumSize(QSize(300, 0))
        self.gridLayout_7 = QGridLayout(self.groupBox_SampleMovement)
        self.gridLayout_7.setObjectName(u"gridLayout_7")
        self.verticalLayout_32 = QVBoxLayout()
        self.verticalLayout_32.setSpacing(10)
        self.verticalLayout_32.setObjectName(u"verticalLayout_32")
        self.gridLayout_5 = QGridLayout()
        self.gridLayout_5.setObjectName(u"gridLayout_5")
        self.label_21 = QLabel(self.groupBox_SampleMovement)
        self.label_21.setObjectName(u"label_21")
        sizePolicy1 = QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.label_21.sizePolicy().hasHeightForWidth())
        self.label_21.setSizePolicy(sizePolicy1)
        self.label_21.setMinimumSize(QSize(170, 0))

        self.gridLayout_5.addWidget(self.label_21, 0, 0, 1, 1)

        self.label_sampleCurrentHPosition = QLabel(self.groupBox_SampleMovement)
        self.label_sampleCurrentHPosition.setObjectName(u"label_sampleCurrentHPosition")
        self.label_sampleCurrentHPosition.setMinimumSize(QSize(80, 0))

        self.gridLayout_5.addWidget(self.label_sampleCurrentHPosition, 0, 1, 1, 1)

        self.pushButton_sampleSetOrigin = QPushButton(self.groupBox_SampleMovement)
        self.pushButton_sampleSetOrigin.setObjectName(u"pushButton_sampleSetOrigin")
        self.pushButton_sampleSetOrigin.setEnabled(True)
        sizePolicy2 = QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        sizePolicy2.setHorizontalStretch(0)
        sizePolicy2.setVerticalStretch(0)
        sizePolicy2.setHeightForWidth(self.pushButton_sampleSetOrigin.sizePolicy().hasHeightForWidth())
        self.pushButton_sampleSetOrigin.setSizePolicy(sizePolicy2)
        self.pushButton_sampleSetOrigin.setMinimumSize(QSize(100, 0))

        self.gridLayout_5.addWidget(self.pushButton_sampleSetOrigin, 0, 2, 2, 1)

        self.label_22 = QLabel(self.groupBox_SampleMovement)
        self.label_22.setObjectName(u"label_22")
        sizePolicy1.setHeightForWidth(self.label_22.sizePolicy().hasHeightForWidth())
        self.label_22.setSizePolicy(sizePolicy1)
        self.label_22.setMinimumSize(QSize(170, 0))
        self.label_22.setAlignment(Qt.AlignLeading|Qt.AlignLeft|Qt.AlignVCenter)

        self.gridLayout_5.addWidget(self.label_22, 1, 0, 1, 1)

        self.label_sampleCurrentVPosition = QLabel(self.groupBox_SampleMovement)
        self.label_sampleCurrentVPosition.setObjectName(u"label_sampleCurrentVPosition")
        self.label_sampleCurrentVPosition.setMinimumSize(QSize(80, 0))

        self.gridLayout_5.addWidget(self.label_sampleCurrentVPosition, 1, 1, 1, 1)


        self.verticalLayout_32.addLayout(self.gridLayout_5)

        self.line = QFrame(self.groupBox_SampleMovement)
        self.line.setObjectName(u"line")
        self.line.setFrameShape(QFrame.Shape.HLine)
        self.line.setFrameShadow(QFrame.Shadow.Sunken)

        self.verticalLayout_32.addWidget(self.line)

        self.stepButtonsAndFields = QHBoxLayout()
        self.stepButtonsAndFields.setSpacing(12)
        self.stepButtonsAndFields.setObjectName(u"stepButtonsAndFields")
        self.gridLayout_3 = QGridLayout()
        self.gridLayout_3.setSpacing(4)
        self.gridLayout_3.setObjectName(u"gridLayout_3")
        self.pushButton_sampleStepUp = QPushButton(self.groupBox_SampleMovement)
        self.pushButton_sampleStepUp.setObjectName(u"pushButton_sampleStepUp")
        sizePolicy2.setHeightForWidth(self.pushButton_sampleStepUp.sizePolicy().hasHeightForWidth())
        self.pushButton_sampleStepUp.setSizePolicy(sizePolicy2)
        self.pushButton_sampleStepUp.setMinimumSize(QSize(48, 48))
        self.pushButton_sampleStepUp.setMaximumSize(QSize(48, 48))

        self.gridLayout_3.addWidget(self.pushButton_sampleStepUp, 0, 1, 1, 1)

        self.pushButton_sampleStepBackward = QPushButton(self.groupBox_SampleMovement)
        self.pushButton_sampleStepBackward.setObjectName(u"pushButton_sampleStepBackward")
        sizePolicy2.setHeightForWidth(self.pushButton_sampleStepBackward.sizePolicy().hasHeightForWidth())
        self.pushButton_sampleStepBackward.setSizePolicy(sizePolicy2)
        self.pushButton_sampleStepBackward.setMinimumSize(QSize(48, 48))
        self.pushButton_sampleStepBackward.setMaximumSize(QSize(48, 48))

        self.gridLayout_3.addWidget(self.pushButton_sampleStepBackward, 1, 0, 1, 1)

        self.pushButton_sampleGotoOrigin = QPushButton(self.groupBox_SampleMovement)
        self.pushButton_sampleGotoOrigin.setObjectName(u"pushButton_sampleGotoOrigin")
        sizePolicy2.setHeightForWidth(self.pushButton_sampleGotoOrigin.sizePolicy().hasHeightForWidth())
        self.pushButton_sampleGotoOrigin.setSizePolicy(sizePolicy2)
        self.pushButton_sampleGotoOrigin.setMinimumSize(QSize(48, 48))
        self.pushButton_sampleGotoOrigin.setMaximumSize(QSize(48, 48))

        self.gridLayout_3.addWidget(self.pushButton_sampleGotoOrigin, 1, 1, 1, 1)

        self.pushButton_sampleStepForward = QPushButton(self.groupBox_SampleMovement)
        self.pushButton_sampleStepForward.setObjectName(u"pushButton_sampleStepForward")
        sizePolicy2.setHeightForWidth(self.pushButton_sampleStepForward.sizePolicy().hasHeightForWidth())
        self.pushButton_sampleStepForward.setSizePolicy(sizePolicy2)
        self.pushButton_sampleStepForward.setMinimumSize(QSize(48, 48))
        self.pushButton_sampleStepForward.setMaximumSize(QSize(48, 48))

        self.gridLayout_3.addWidget(self.pushButton_sampleStepForward, 1, 2, 1, 1)

        self.pushButton_sampleStepDown = QPushButton(self.groupBox_SampleMovement)
        self.pushButton_sampleStepDown.setObjectName(u"pushButton_sampleStepDown")
        sizePolicy2.setHeightForWidth(self.pushButton_sampleStepDown.sizePolicy().hasHeightForWidth())
        self.pushButton_sampleStepDown.setSizePolicy(sizePolicy2)
        self.pushButton_sampleStepDown.setMinimumSize(QSize(48, 48))
        self.pushButton_sampleStepDown.setMaximumSize(QSize(48, 48))

        self.gridLayout_3.addWidget(self.pushButton_sampleStepDown, 2, 1, 1, 1)


        self.stepButtonsAndFields.addLayout(self.gridLayout_3)

        self.horizontalLayout_55 = QGridLayout()
        self.horizontalLayout_55.setObjectName(u"horizontalLayout_55")
        self.label_25 = QLabel(self.groupBox_SampleMovement)
        self.label_25.setObjectName(u"label_25")
        sizePolicy1.setHeightForWidth(self.label_25.sizePolicy().hasHeightForWidth())
        self.label_25.setSizePolicy(sizePolicy1)

        self.horizontalLayout_55.addWidget(self.label_25, 0, 0, 1, 1)

        self.doubleSpinBox_sampleHStepSize = FieldSpecSpinBox(self.groupBox_SampleMovement)
        self.doubleSpinBox_sampleHStepSize.setObjectName(u"doubleSpinBox_sampleHStepSize")
        sizePolicy2.setHeightForWidth(self.doubleSpinBox_sampleHStepSize.sizePolicy().hasHeightForWidth())
        self.doubleSpinBox_sampleHStepSize.setSizePolicy(sizePolicy2)
        self.doubleSpinBox_sampleHStepSize.setMinimumSize(QSize(110, 0))
        self.doubleSpinBox_sampleHStepSize.setMaximumSize(QSize(110, 16777215))
        self.doubleSpinBox_sampleHStepSize.setDecimals(3)

        self.horizontalLayout_55.addWidget(self.doubleSpinBox_sampleHStepSize, 0, 1, 1, 1)

        self.label_26 = QLabel(self.groupBox_SampleMovement)
        self.label_26.setObjectName(u"label_26")
        sizePolicy1.setHeightForWidth(self.label_26.sizePolicy().hasHeightForWidth())
        self.label_26.setSizePolicy(sizePolicy1)

        self.horizontalLayout_55.addWidget(self.label_26, 1, 0, 1, 1)

        self.doubleSpinBox_sampleVStepSize = FieldSpecSpinBox(self.groupBox_SampleMovement)
        self.doubleSpinBox_sampleVStepSize.setObjectName(u"doubleSpinBox_sampleVStepSize")
        sizePolicy2.setHeightForWidth(self.doubleSpinBox_sampleVStepSize.sizePolicy().hasHeightForWidth())
        self.doubleSpinBox_sampleVStepSize.setSizePolicy(sizePolicy2)
        self.doubleSpinBox_sampleVStepSize.setMinimumSize(QSize(110, 0))
        self.doubleSpinBox_sampleVStepSize.setMaximumSize(QSize(110, 16777215))
        self.doubleSpinBox_sampleVStepSize.setDecimals(3)

        self.horizontalLayout_55.addWidget(self.doubleSpinBox_sampleVStepSize, 1, 1, 1, 1)


        self.stepButtonsAndFields.addLayout(self.horizontalLayout_55)


        self.verticalLayout_32.addLayout(self.stepButtonsAndFields)

        self.line_3 = QFrame(self.groupBox_SampleMovement)
        self.line_3.setObjectName(u"line_3")
        self.line_3.setFrameShape(QFrame.Shape.HLine)
        self.line_3.setFrameShadow(QFrame.Shadow.Sunken)

        self.verticalLayout_32.addWidget(self.line_3)

        self.horizontalLayout_53 = QGridLayout()
        self.horizontalLayout_53.setObjectName(u"horizontalLayout_53")
        self.label_23 = QLabel(self.groupBox_SampleMovement)
        self.label_23.setObjectName(u"label_23")
        sizePolicy1.setHeightForWidth(self.label_23.sizePolicy().hasHeightForWidth())
        self.label_23.setSizePolicy(sizePolicy1)
        self.label_23.setMinimumSize(QSize(170, 0))

        self.horizontalLayout_53.addWidget(self.label_23, 0, 0, 1, 1)

        self.doubleSpinBox_sampleSetHPosition = FieldSpecSpinBox(self.groupBox_SampleMovement)
        self.doubleSpinBox_sampleSetHPosition.setObjectName(u"doubleSpinBox_sampleSetHPosition")
        sizePolicy2.setHeightForWidth(self.doubleSpinBox_sampleSetHPosition.sizePolicy().hasHeightForWidth())
        self.doubleSpinBox_sampleSetHPosition.setSizePolicy(sizePolicy2)
        self.doubleSpinBox_sampleSetHPosition.setMinimumSize(QSize(110, 0))
        self.doubleSpinBox_sampleSetHPosition.setMaximumSize(QSize(110, 16777215))
        self.doubleSpinBox_sampleSetHPosition.setDecimals(3)

        self.horizontalLayout_53.addWidget(self.doubleSpinBox_sampleSetHPosition, 0, 1, 1, 1)

        self.pushButton_sampleGotoHPosition = QPushButton(self.groupBox_SampleMovement)
        self.pushButton_sampleGotoHPosition.setObjectName(u"pushButton_sampleGotoHPosition")
        sizePolicy2.setHeightForWidth(self.pushButton_sampleGotoHPosition.sizePolicy().hasHeightForWidth())
        self.pushButton_sampleGotoHPosition.setSizePolicy(sizePolicy2)
        self.pushButton_sampleGotoHPosition.setMinimumSize(QSize(110, 0))

        self.horizontalLayout_53.addWidget(self.pushButton_sampleGotoHPosition, 0, 2, 1, 1)

        self.label_24 = QLabel(self.groupBox_SampleMovement)
        self.label_24.setObjectName(u"label_24")
        sizePolicy1.setHeightForWidth(self.label_24.sizePolicy().hasHeightForWidth())
        self.label_24.setSizePolicy(sizePolicy1)
        self.label_24.setMinimumSize(QSize(170, 0))

        self.horizontalLayout_53.addWidget(self.label_24, 1, 0, 1, 1)

        self.doubleSpinBox_sampleSetVPosition = FieldSpecSpinBox(self.groupBox_SampleMovement)
        self.doubleSpinBox_sampleSetVPosition.setObjectName(u"doubleSpinBox_sampleSetVPosition")
        sizePolicy2.setHeightForWidth(self.doubleSpinBox_sampleSetVPosition.sizePolicy().hasHeightForWidth())
        self.doubleSpinBox_sampleSetVPosition.setSizePolicy(sizePolicy2)
        self.doubleSpinBox_sampleSetVPosition.setMinimumSize(QSize(110, 0))
        self.doubleSpinBox_sampleSetVPosition.setMaximumSize(QSize(110, 16777215))
        self.doubleSpinBox_sampleSetVPosition.setDecimals(3)

        self.horizontalLayout_53.addWidget(self.doubleSpinBox_sampleSetVPosition, 1, 1, 1, 1)

        self.pushButton_sampleGotoVPosition = QPushButton(self.groupBox_SampleMovement)
        self.pushButton_sampleGotoVPosition.setObjectName(u"pushButton_sampleGotoVPosition")
        sizePolicy2.setHeightForWidth(self.pushButton_sampleGotoVPosition.sizePolicy().hasHeightForWidth())
        self.pushButton_sampleGotoVPosition.setSizePolicy(sizePolicy2)
        self.pushButton_sampleGotoVPosition.setMinimumSize(QSize(110, 0))

        self.horizontalLayout_53.addWidget(self.pushButton_sampleGotoVPosition, 1, 2, 1, 1)


        self.verticalLayout_32.addLayout(self.horizontalLayout_53)


        self.gridLayout_7.addLayout(self.verticalLayout_32, 0, 0, 1, 1)


        self.verticalLayout_panel.addWidget(self.groupBox_SampleMovement)

        self.groupBox_CameraMovement = QGroupBox(motorPanel)
        self.groupBox_CameraMovement.setObjectName(u"groupBox_CameraMovement")
        sizePolicy.setHeightForWidth(self.groupBox_CameraMovement.sizePolicy().hasHeightForWidth())
        self.groupBox_CameraMovement.setSizePolicy(sizePolicy)
        self.groupBox_CameraMovement.setMinimumSize(QSize(300, 0))
        self.verticalLayout_34 = QVBoxLayout(self.groupBox_CameraMovement)
        self.verticalLayout_34.setSpacing(10)
        self.verticalLayout_34.setObjectName(u"verticalLayout_34")
        self.horizontalLayout_58 = QHBoxLayout()
        self.horizontalLayout_58.setObjectName(u"horizontalLayout_58")
        self.label_31 = QLabel(self.groupBox_CameraMovement)
        self.label_31.setObjectName(u"label_31")
        sizePolicy1.setHeightForWidth(self.label_31.sizePolicy().hasHeightForWidth())
        self.label_31.setSizePolicy(sizePolicy1)
        self.label_31.setMinimumSize(QSize(170, 0))

        self.horizontalLayout_58.addWidget(self.label_31)

        self.label_cameraCurrentPosition = QLabel(self.groupBox_CameraMovement)
        self.label_cameraCurrentPosition.setObjectName(u"label_cameraCurrentPosition")
        self.label_cameraCurrentPosition.setMinimumSize(QSize(80, 0))

        self.horizontalLayout_58.addWidget(self.label_cameraCurrentPosition)

        self.pushButton_cameraSetFocus = QPushButton(self.groupBox_CameraMovement)
        self.pushButton_cameraSetFocus.setObjectName(u"pushButton_cameraSetFocus")
        sizePolicy2.setHeightForWidth(self.pushButton_cameraSetFocus.sizePolicy().hasHeightForWidth())
        self.pushButton_cameraSetFocus.setSizePolicy(sizePolicy2)
        self.pushButton_cameraSetFocus.setMinimumSize(QSize(100, 0))

        self.horizontalLayout_58.addWidget(self.pushButton_cameraSetFocus)


        self.verticalLayout_34.addLayout(self.horizontalLayout_58)

        self.line_2 = QFrame(self.groupBox_CameraMovement)
        self.line_2.setObjectName(u"line_2")
        self.line_2.setFrameShape(QFrame.Shape.HLine)
        self.line_2.setFrameShadow(QFrame.Shadow.Sunken)

        self.verticalLayout_34.addWidget(self.line_2)

        self.gridLayout_8 = QHBoxLayout()
        self.gridLayout_8.setObjectName(u"gridLayout_8")
        self.horizontalSpacer_4 = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.gridLayout_8.addItem(self.horizontalSpacer_4)

        self.pushButton_cameraStepBackward = QPushButton(self.groupBox_CameraMovement)
        self.pushButton_cameraStepBackward.setObjectName(u"pushButton_cameraStepBackward")
        sizePolicy3 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        sizePolicy3.setHorizontalStretch(0)
        sizePolicy3.setVerticalStretch(0)
        sizePolicy3.setHeightForWidth(self.pushButton_cameraStepBackward.sizePolicy().hasHeightForWidth())
        self.pushButton_cameraStepBackward.setSizePolicy(sizePolicy3)
        self.pushButton_cameraStepBackward.setMinimumSize(QSize(70, 32))

        self.gridLayout_8.addWidget(self.pushButton_cameraStepBackward)

        self.pushButton_cameraGotoFocus = QPushButton(self.groupBox_CameraMovement)
        self.pushButton_cameraGotoFocus.setObjectName(u"pushButton_cameraGotoFocus")
        sizePolicy3.setHeightForWidth(self.pushButton_cameraGotoFocus.sizePolicy().hasHeightForWidth())
        self.pushButton_cameraGotoFocus.setSizePolicy(sizePolicy3)
        self.pushButton_cameraGotoFocus.setMinimumSize(QSize(70, 32))

        self.gridLayout_8.addWidget(self.pushButton_cameraGotoFocus)

        self.pushButton_cameraStepForward = QPushButton(self.groupBox_CameraMovement)
        self.pushButton_cameraStepForward.setObjectName(u"pushButton_cameraStepForward")
        sizePolicy3.setHeightForWidth(self.pushButton_cameraStepForward.sizePolicy().hasHeightForWidth())
        self.pushButton_cameraStepForward.setSizePolicy(sizePolicy3)
        self.pushButton_cameraStepForward.setMinimumSize(QSize(70, 32))

        self.gridLayout_8.addWidget(self.pushButton_cameraStepForward)

        self.horizontalSpacer_5 = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.gridLayout_8.addItem(self.horizontalSpacer_5)


        self.verticalLayout_34.addLayout(self.gridLayout_8)

        self.line_4 = QFrame(self.groupBox_CameraMovement)
        self.line_4.setObjectName(u"line_4")
        self.line_4.setFrameShape(QFrame.Shape.HLine)
        self.line_4.setFrameShadow(QFrame.Shadow.Sunken)

        self.verticalLayout_34.addWidget(self.line_4)

        self.horizontalLayout_59 = QGridLayout()
        self.horizontalLayout_59.setObjectName(u"horizontalLayout_59")
        self.label_33 = QLabel(self.groupBox_CameraMovement)
        self.label_33.setObjectName(u"label_33")
        sizePolicy1.setHeightForWidth(self.label_33.sizePolicy().hasHeightForWidth())
        self.label_33.setSizePolicy(sizePolicy1)
        self.label_33.setMinimumSize(QSize(170, 0))

        self.horizontalLayout_59.addWidget(self.label_33, 0, 0, 1, 1)

        self.doubleSpinBox_cameraStepSize = FieldSpecSpinBox(self.groupBox_CameraMovement)
        self.doubleSpinBox_cameraStepSize.setObjectName(u"doubleSpinBox_cameraStepSize")
        sizePolicy2.setHeightForWidth(self.doubleSpinBox_cameraStepSize.sizePolicy().hasHeightForWidth())
        self.doubleSpinBox_cameraStepSize.setSizePolicy(sizePolicy2)
        self.doubleSpinBox_cameraStepSize.setMinimumSize(QSize(110, 0))
        self.doubleSpinBox_cameraStepSize.setMaximumSize(QSize(110, 16777215))
        self.doubleSpinBox_cameraStepSize.setDecimals(3)

        self.horizontalLayout_59.addWidget(self.doubleSpinBox_cameraStepSize, 0, 1, 1, 1)

        self.label_32 = QLabel(self.groupBox_CameraMovement)
        self.label_32.setObjectName(u"label_32")
        sizePolicy1.setHeightForWidth(self.label_32.sizePolicy().hasHeightForWidth())
        self.label_32.setSizePolicy(sizePolicy1)
        self.label_32.setMinimumSize(QSize(170, 0))

        self.horizontalLayout_59.addWidget(self.label_32, 1, 0, 1, 1)

        self.doubleSpinBox_cameraSetPosition = FieldSpecSpinBox(self.groupBox_CameraMovement)
        self.doubleSpinBox_cameraSetPosition.setObjectName(u"doubleSpinBox_cameraSetPosition")
        sizePolicy2.setHeightForWidth(self.doubleSpinBox_cameraSetPosition.sizePolicy().hasHeightForWidth())
        self.doubleSpinBox_cameraSetPosition.setSizePolicy(sizePolicy2)
        self.doubleSpinBox_cameraSetPosition.setMinimumSize(QSize(110, 0))
        self.doubleSpinBox_cameraSetPosition.setMaximumSize(QSize(110, 16777215))
        self.doubleSpinBox_cameraSetPosition.setDecimals(3)

        self.horizontalLayout_59.addWidget(self.doubleSpinBox_cameraSetPosition, 1, 1, 1, 1)

        self.pushButton_cameraGotoPosition = QPushButton(self.groupBox_CameraMovement)
        self.pushButton_cameraGotoPosition.setObjectName(u"pushButton_cameraGotoPosition")
        sizePolicy2.setHeightForWidth(self.pushButton_cameraGotoPosition.sizePolicy().hasHeightForWidth())
        self.pushButton_cameraGotoPosition.setSizePolicy(sizePolicy2)
        self.pushButton_cameraGotoPosition.setMinimumSize(QSize(110, 0))

        self.horizontalLayout_59.addWidget(self.pushButton_cameraGotoPosition, 1, 2, 1, 1)


        self.verticalLayout_34.addLayout(self.horizontalLayout_59)


        self.verticalLayout_panel.addWidget(self.groupBox_CameraMovement)


        self.retranslateUi(motorPanel)

        QMetaObject.connectSlotsByName(motorPanel)
    # setupUi

    def retranslateUi(self, motorPanel):
        self.groupBox_SampleMovement.setTitle(QCoreApplication.translate("MotorPanel", u"Sample Movement", None))
        self.label_21.setText(QCoreApplication.translate("MotorPanel", u"Current Horizontal Position:", None))
        self.label_sampleCurrentHPosition.setText(QCoreApplication.translate("MotorPanel", u"0", None))
#if QT_CONFIG(tooltip)
        self.pushButton_sampleSetOrigin.setToolTip(QCoreApplication.translate("MotorPanel", u"Set the current sample position as the origin", None))
#endif // QT_CONFIG(tooltip)
        self.pushButton_sampleSetOrigin.setText(QCoreApplication.translate("MotorPanel", u"Set Origin", None))
        self.label_22.setText(QCoreApplication.translate("MotorPanel", u"Current Vertical Position:", None))
        self.label_sampleCurrentVPosition.setText(QCoreApplication.translate("MotorPanel", u"0", None))
#if QT_CONFIG(tooltip)
        self.pushButton_sampleStepUp.setToolTip(QCoreApplication.translate("MotorPanel", u"Move the sample up", None))
#endif // QT_CONFIG(tooltip)
        self.pushButton_sampleStepUp.setText(QCoreApplication.translate("MotorPanel", u"Up", None))
#if QT_CONFIG(shortcut)
        self.pushButton_sampleStepUp.setShortcut(QCoreApplication.translate("MotorPanel", u"Ctrl+Up", None))
#endif // QT_CONFIG(shortcut)
#if QT_CONFIG(tooltip)
        self.pushButton_sampleStepBackward.setToolTip(QCoreApplication.translate("MotorPanel", u"Move the sample backward", None))
#endif // QT_CONFIG(tooltip)
        self.pushButton_sampleStepBackward.setText(QCoreApplication.translate("MotorPanel", u"Back", None))
#if QT_CONFIG(shortcut)
        self.pushButton_sampleStepBackward.setShortcut(QCoreApplication.translate("MotorPanel", u"Ctrl+Left", None))
#endif // QT_CONFIG(shortcut)
#if QT_CONFIG(tooltip)
        self.pushButton_sampleGotoOrigin.setToolTip(QCoreApplication.translate("MotorPanel", u"Move the sample to origin", None))
#endif // QT_CONFIG(tooltip)
        self.pushButton_sampleGotoOrigin.setText(QCoreApplication.translate("MotorPanel", u"Origin", None))
#if QT_CONFIG(tooltip)
        self.pushButton_sampleStepForward.setToolTip(QCoreApplication.translate("MotorPanel", u"Move the sample forward", None))
#endif // QT_CONFIG(tooltip)
        self.pushButton_sampleStepForward.setText(QCoreApplication.translate("MotorPanel", u"Fwd", None))
#if QT_CONFIG(shortcut)
        self.pushButton_sampleStepForward.setShortcut(QCoreApplication.translate("MotorPanel", u"Ctrl+Right", None))
#endif // QT_CONFIG(shortcut)
#if QT_CONFIG(tooltip)
        self.pushButton_sampleStepDown.setToolTip(QCoreApplication.translate("MotorPanel", u"Move the sample down", None))
#endif // QT_CONFIG(tooltip)
        self.pushButton_sampleStepDown.setText(QCoreApplication.translate("MotorPanel", u"Down", None))
        self.label_25.setText(QCoreApplication.translate("MotorPanel", u"H Step:", None))
#if QT_CONFIG(tooltip)
        self.doubleSpinBox_sampleHStepSize.setToolTip(QCoreApplication.translate("MotorPanel", u"Horizontal sample stage jog step. Unit: the active unit (\u03bcm/mm/steps, set on the E-stop toolbar). Valid range: >0. Effect: the step arrows move the stage by this amount.", None))
#endif // QT_CONFIG(tooltip)
        self.doubleSpinBox_sampleHStepSize.setSuffix("")
        self.label_26.setText(QCoreApplication.translate("MotorPanel", u"V Step:", None))
#if QT_CONFIG(tooltip)
        self.doubleSpinBox_sampleVStepSize.setToolTip(QCoreApplication.translate("MotorPanel", u"Vertical sample stage jog step. Unit: the active unit (\u03bcm/mm/steps). Valid range: >0. Effect: the step arrows move the stage by this amount.", None))
#endif // QT_CONFIG(tooltip)
        self.label_23.setText(QCoreApplication.translate("MotorPanel", u"Horizontal Position:", None))
#if QT_CONFIG(tooltip)
        self.doubleSpinBox_sampleSetHPosition.setToolTip(QCoreApplication.translate("MotorPanel", u"Horizontal sample target position for the Go-To button. Unit: the active unit (\u03bcm/mm/steps). Valid range: the stage travel limits (reject-and-beep if out of range). Effect: Go-To moves the stage to this position.", None))
#endif // QT_CONFIG(tooltip)
#if QT_CONFIG(tooltip)
        self.pushButton_sampleGotoHPosition.setToolTip(QCoreApplication.translate("MotorPanel", u"Move the sample to the specified horizontal position", None))
#endif // QT_CONFIG(tooltip)
        self.pushButton_sampleGotoHPosition.setText(QCoreApplication.translate("MotorPanel", u"Move Horizontal", None))
        self.label_24.setText(QCoreApplication.translate("MotorPanel", u"Vertical Position:", None))
#if QT_CONFIG(tooltip)
        self.doubleSpinBox_sampleSetVPosition.setToolTip(QCoreApplication.translate("MotorPanel", u"Vertical sample target position for the Go-To button. Unit: the active unit (\u03bcm/mm/steps). Valid range: the stage travel limits (reject-and-beep if out of range). Effect: Go-To moves the stage to this position.", None))
#endif // QT_CONFIG(tooltip)
#if QT_CONFIG(tooltip)
        self.pushButton_sampleGotoVPosition.setToolTip(QCoreApplication.translate("MotorPanel", u"Move the sample to the specified vertical position", None))
#endif // QT_CONFIG(tooltip)
        self.pushButton_sampleGotoVPosition.setText(QCoreApplication.translate("MotorPanel", u"Move Vertical", None))
        self.groupBox_CameraMovement.setTitle(QCoreApplication.translate("MotorPanel", u"Camera Movement", None))
        self.label_31.setText(QCoreApplication.translate("MotorPanel", u"Current Camera Position:", None))
        self.label_cameraCurrentPosition.setText(QCoreApplication.translate("MotorPanel", u"0", None))
#if QT_CONFIG(tooltip)
        self.pushButton_cameraSetFocus.setToolTip(QCoreApplication.translate("MotorPanel", u"Set the current camera position as focus position", None))
#endif // QT_CONFIG(tooltip)
        self.pushButton_cameraSetFocus.setText(QCoreApplication.translate("MotorPanel", u"Set Focus", None))
        self.pushButton_cameraStepBackward.setText(QCoreApplication.translate("MotorPanel", u"Back", None))
        self.pushButton_cameraGotoFocus.setText(QCoreApplication.translate("MotorPanel", u"Focus", None))
        self.pushButton_cameraStepForward.setText(QCoreApplication.translate("MotorPanel", u"Fwd", None))
        self.label_33.setText(QCoreApplication.translate("MotorPanel", u"Camera Step:", None))
#if QT_CONFIG(tooltip)
        self.doubleSpinBox_cameraStepSize.setToolTip(QCoreApplication.translate("MotorPanel", u"Camera (focus) stage jog step. Unit: the active unit (\u03bcm/mm/steps). Valid range: >0. Effect: the step arrows move the focus stage by this amount.", None))
#endif // QT_CONFIG(tooltip)
        self.label_32.setText(QCoreApplication.translate("MotorPanel", u"Camera Position:", None))
#if QT_CONFIG(tooltip)
        self.doubleSpinBox_cameraSetPosition.setToolTip(QCoreApplication.translate("MotorPanel", u"Camera (focus) target position for the Go-To button. Unit: the active unit (\u03bcm/mm/steps). Valid range: the stage travel limits (reject-and-beep if out of range). Effect: Go-To moves the focus stage to this position.", None))
#endif // QT_CONFIG(tooltip)
#if QT_CONFIG(tooltip)
        self.pushButton_cameraGotoPosition.setToolTip(QCoreApplication.translate("MotorPanel", u"Move the camera to the specified position", None))
#endif // QT_CONFIG(tooltip)
        self.pushButton_cameraGotoPosition.setText(QCoreApplication.translate("MotorPanel", u"Move Camera", None))
        pass
    # retranslateUi


# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'ui_calibration_panel.ui'
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
from PySide6.QtWidgets import (QApplication, QFormLayout, QGroupBox, QLabel,
    QPushButton, QSizePolicy, QSpacerItem, QVBoxLayout,
    QWidget)
from lightsheet.gui.styles import spacing as _s

from lightsheet.gui.widgets.field_spec_spinbox import FieldSpecSpinBox

class Ui_CalibrationPanel(object):
    def setupUi(self, calibrationPanel):
        if not calibrationPanel.objectName():
            calibrationPanel.setObjectName(u"calibrationPanel")
        self.verticalLayout_panel = QVBoxLayout(calibrationPanel)
        self.verticalLayout_panel.setObjectName(u"verticalLayout_panel")
        self.groupBox_2 = QGroupBox(calibrationPanel)
        self.groupBox_2.setObjectName(u"groupBox_2")
        self.verticalLayout_5 = QVBoxLayout(self.groupBox_2)
        self.verticalLayout_5.setObjectName(u"verticalLayout_5")
        self.formLayout_2 = QFormLayout()
        self.formLayout_2.setObjectName(u"formLayout_2")
        self.label_28 = QLabel(self.groupBox_2)
        self.label_28.setObjectName(u"label_28")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.label_28.sizePolicy().hasHeightForWidth())
        self.label_28.setSizePolicy(sizePolicy)

        self.formLayout_2.setWidget(0, QFormLayout.ItemRole.LabelRole, self.label_28)

        self.doubleSpinBox_calNumberOfPlanes = FieldSpecSpinBox(self.groupBox_2)
        self.doubleSpinBox_calNumberOfPlanes.setObjectName(u"doubleSpinBox_calNumberOfPlanes")
        sizePolicy1 = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.doubleSpinBox_calNumberOfPlanes.sizePolicy().hasHeightForWidth())
        self.doubleSpinBox_calNumberOfPlanes.setSizePolicy(sizePolicy1)
        self.doubleSpinBox_calNumberOfPlanes.setDecimals(0)
        self.doubleSpinBox_calNumberOfPlanes.setMinimum(3.000000000000000)
        self.doubleSpinBox_calNumberOfPlanes.setMaximum(1000.000000000000000)
        self.doubleSpinBox_calNumberOfPlanes.setValue(10.000000000000000)

        self.formLayout_2.setWidget(0, QFormLayout.ItemRole.FieldRole, self.doubleSpinBox_calNumberOfPlanes)

        self.label_43 = QLabel(self.groupBox_2)
        self.label_43.setObjectName(u"label_43")
        sizePolicy.setHeightForWidth(self.label_43.sizePolicy().hasHeightForWidth())
        self.label_43.setSizePolicy(sizePolicy)

        self.formLayout_2.setWidget(1, QFormLayout.ItemRole.LabelRole, self.label_43)

        self.doubleSpinBox_calNumberOfCameraPositions = FieldSpecSpinBox(self.groupBox_2)
        self.doubleSpinBox_calNumberOfCameraPositions.setObjectName(u"doubleSpinBox_calNumberOfCameraPositions")
        sizePolicy1.setHeightForWidth(self.doubleSpinBox_calNumberOfCameraPositions.sizePolicy().hasHeightForWidth())
        self.doubleSpinBox_calNumberOfCameraPositions.setSizePolicy(sizePolicy1)
        self.doubleSpinBox_calNumberOfCameraPositions.setDecimals(0)
        self.doubleSpinBox_calNumberOfCameraPositions.setMinimum(1.000000000000000)
        self.doubleSpinBox_calNumberOfCameraPositions.setMaximum(1000.000000000000000)
        self.doubleSpinBox_calNumberOfCameraPositions.setValue(15.000000000000000)

        self.formLayout_2.setWidget(1, QFormLayout.ItemRole.FieldRole, self.doubleSpinBox_calNumberOfCameraPositions)


        self.verticalLayout_5.addLayout(self.formLayout_2)

        self.verticalSpacer_3 = QSpacerItem(_s.LG + _s.XS, _s.XXL + _s.SM, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.verticalLayout_5.addItem(self.verticalSpacer_3)

        self.pushButton_calCameraShowInterpolation = QPushButton(self.groupBox_2)
        self.pushButton_calCameraShowInterpolation.setObjectName(u"pushButton_calCameraShowInterpolation")
        sizePolicy1.setHeightForWidth(self.pushButton_calCameraShowInterpolation.sizePolicy().hasHeightForWidth())
        self.pushButton_calCameraShowInterpolation.setSizePolicy(sizePolicy1)

        self.verticalLayout_5.addWidget(self.pushButton_calCameraShowInterpolation)

        self.pushButton_calCameraComputeFocus = QPushButton(self.groupBox_2)
        self.pushButton_calCameraComputeFocus.setObjectName(u"pushButton_calCameraComputeFocus")
        sizePolicy1.setHeightForWidth(self.pushButton_calCameraComputeFocus.sizePolicy().hasHeightForWidth())
        self.pushButton_calCameraComputeFocus.setSizePolicy(sizePolicy1)

        self.verticalLayout_5.addWidget(self.pushButton_calCameraComputeFocus)


        self.verticalLayout_panel.addWidget(self.groupBox_2)

        self.groupBox_3 = QGroupBox(calibrationPanel)
        self.groupBox_3.setObjectName(u"groupBox_3")
        self.verticalLayout_6 = QVBoxLayout(self.groupBox_3)
        self.verticalLayout_6.setObjectName(u"verticalLayout_6")
        self.formLayout_3 = QFormLayout()
        self.formLayout_3.setObjectName(u"formLayout_3")
        self.label_47 = QLabel(self.groupBox_3)
        self.label_47.setObjectName(u"label_47")
        sizePolicy.setHeightForWidth(self.label_47.sizePolicy().hasHeightForWidth())
        self.label_47.setSizePolicy(sizePolicy)

        self.formLayout_3.setWidget(0, QFormLayout.ItemRole.LabelRole, self.label_47)

        self.doubleSpinBox_calNumberOfEtlVoltages = FieldSpecSpinBox(self.groupBox_3)
        self.doubleSpinBox_calNumberOfEtlVoltages.setObjectName(u"doubleSpinBox_calNumberOfEtlVoltages")
        sizePolicy1.setHeightForWidth(self.doubleSpinBox_calNumberOfEtlVoltages.sizePolicy().hasHeightForWidth())
        self.doubleSpinBox_calNumberOfEtlVoltages.setSizePolicy(sizePolicy1)
        self.doubleSpinBox_calNumberOfEtlVoltages.setDecimals(0)
        self.doubleSpinBox_calNumberOfEtlVoltages.setMinimum(1.000000000000000)
        self.doubleSpinBox_calNumberOfEtlVoltages.setMaximum(1000.000000000000000)
        self.doubleSpinBox_calNumberOfEtlVoltages.setValue(10.000000000000000)

        self.formLayout_3.setWidget(0, QFormLayout.ItemRole.FieldRole, self.doubleSpinBox_calNumberOfEtlVoltages)


        self.verticalLayout_6.addLayout(self.formLayout_3)

        self.verticalSpacer_5 = QSpacerItem(_s.LG + _s.XS, _s.XXL + _s.SM, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.verticalLayout_6.addItem(self.verticalSpacer_5)

        self.pushButton_calEtlShowInterpolation = QPushButton(self.groupBox_3)
        self.pushButton_calEtlShowInterpolation.setObjectName(u"pushButton_calEtlShowInterpolation")
        sizePolicy1.setHeightForWidth(self.pushButton_calEtlShowInterpolation.sizePolicy().hasHeightForWidth())
        self.pushButton_calEtlShowInterpolation.setSizePolicy(sizePolicy1)

        self.verticalLayout_6.addWidget(self.pushButton_calEtlShowInterpolation)


        self.verticalLayout_panel.addWidget(self.groupBox_3)

        self.groupBox = QGroupBox(calibrationPanel)
        self.groupBox.setObjectName(u"groupBox")
        self.verticalLayout_12 = QVBoxLayout(self.groupBox)
        self.verticalLayout_12.setObjectName(u"verticalLayout_12")
        self.pushButton_calHorizontalStartRangeSelection = QPushButton(self.groupBox)
        self.pushButton_calHorizontalStartRangeSelection.setObjectName(u"pushButton_calHorizontalStartRangeSelection")
        sizePolicy1.setHeightForWidth(self.pushButton_calHorizontalStartRangeSelection.sizePolicy().hasHeightForWidth())
        self.pushButton_calHorizontalStartRangeSelection.setSizePolicy(sizePolicy1)

        self.verticalLayout_12.addWidget(self.pushButton_calHorizontalStartRangeSelection)

        self.label_calibrateRange = QLabel(self.groupBox)
        self.label_calibrateRange.setObjectName(u"label_calibrateRange")

        self.verticalLayout_12.addWidget(self.label_calibrateRange)

        self.pushButton_calHorizontalSetForwardLimit = QPushButton(self.groupBox)
        self.pushButton_calHorizontalSetForwardLimit.setObjectName(u"pushButton_calHorizontalSetForwardLimit")
        sizePolicy1.setHeightForWidth(self.pushButton_calHorizontalSetForwardLimit.sizePolicy().hasHeightForWidth())
        self.pushButton_calHorizontalSetForwardLimit.setSizePolicy(sizePolicy1)

        self.verticalLayout_12.addWidget(self.pushButton_calHorizontalSetForwardLimit)

        self.pushButton_calHorizontalSetBackwardLimit = QPushButton(self.groupBox)
        self.pushButton_calHorizontalSetBackwardLimit.setObjectName(u"pushButton_calHorizontalSetBackwardLimit")
        sizePolicy1.setHeightForWidth(self.pushButton_calHorizontalSetBackwardLimit.sizePolicy().hasHeightForWidth())
        self.pushButton_calHorizontalSetBackwardLimit.setSizePolicy(sizePolicy1)

        self.verticalLayout_12.addWidget(self.pushButton_calHorizontalSetBackwardLimit)


        self.verticalLayout_panel.addWidget(self.groupBox)


        self.retranslateUi(calibrationPanel)

        QMetaObject.connectSlotsByName(calibrationPanel)
    # setupUi

    def retranslateUi(self, calibrationPanel):
        self.groupBox_2.setTitle(QCoreApplication.translate("CalibrationPanel", u"Camera Focus Calibration", None))
        self.label_28.setText(QCoreApplication.translate("CalibrationPanel", u"Number of planes for calibration:", None))
#if QT_CONFIG(tooltip)
        self.doubleSpinBox_calNumberOfPlanes.setToolTip(QCoreApplication.translate("CalibrationPanel", u"Number of z-planes per camera position used by the camera-focus calibration. Unit: planes. Valid range: 3\u20131000. Effect: more planes give a finer focus curve but a longer calibration sweep.", None))
#endif // QT_CONFIG(tooltip)
        self.doubleSpinBox_calNumberOfPlanes.setSuffix(QCoreApplication.translate("CalibrationPanel", u" planes", None))
        self.label_43.setText(QCoreApplication.translate("CalibrationPanel", u"Number of camera positions:", None))
#if QT_CONFIG(tooltip)
        self.doubleSpinBox_calNumberOfCameraPositions.setToolTip(QCoreApplication.translate("CalibrationPanel", u"Number of camera (focus) positions sampled across the horizontal range. Unit: positions. Valid range: 1\u20131000. Effect: more positions improve the focus-vs-position regression fit.", None))
#endif // QT_CONFIG(tooltip)
        self.doubleSpinBox_calNumberOfCameraPositions.setSuffix(QCoreApplication.translate("CalibrationPanel", u" planes", None))
#if QT_CONFIG(tooltip)
        self.pushButton_calCameraShowInterpolation.setToolTip(QCoreApplication.translate("CalibrationPanel", u"Show the results of the last camera calibration", None))
#endif // QT_CONFIG(tooltip)
        self.pushButton_calCameraShowInterpolation.setText(QCoreApplication.translate("CalibrationPanel", u"Show Camera Focus Interpolation", None))
#if QT_CONFIG(tooltip)
        self.pushButton_calCameraComputeFocus.setToolTip(QCoreApplication.translate("CalibrationPanel", u"Calculate the camera position of focus", None))
#endif // QT_CONFIG(tooltip)
        self.pushButton_calCameraComputeFocus.setText(QCoreApplication.translate("CalibrationPanel", u"Compute Camera Focus", None))
        self.groupBox_3.setTitle(QCoreApplication.translate("CalibrationPanel", u"ETL Focus Calibration", None))
        self.label_47.setText(QCoreApplication.translate("CalibrationPanel", u"Number of ETL voltages:", None))
#if QT_CONFIG(tooltip)
        self.doubleSpinBox_calNumberOfEtlVoltages.setToolTip(QCoreApplication.translate("CalibrationPanel", u"Number of ETL drive voltages sampled by the ETL-focus calibration. Unit: points. Valid range: 1\u20131000. Effect: more points give a finer ETL-focus curve but a longer calibration sweep.", None))
#endif // QT_CONFIG(tooltip)
        self.doubleSpinBox_calNumberOfEtlVoltages.setSuffix(QCoreApplication.translate("CalibrationPanel", u" points", None))
#if QT_CONFIG(tooltip)
        self.pushButton_calEtlShowInterpolation.setToolTip(QCoreApplication.translate("CalibrationPanel", u"Show the results of the last ETLs calibration", None))
#endif // QT_CONFIG(tooltip)
        self.pushButton_calEtlShowInterpolation.setText(QCoreApplication.translate("CalibrationPanel", u"Show ETL Focus Interpolation", None))
        self.groupBox.setTitle(QCoreApplication.translate("CalibrationPanel", u"Horizontal Movement Calibration", None))
#if QT_CONFIG(tooltip)
        self.pushButton_calHorizontalStartRangeSelection.setToolTip(QCoreApplication.translate("CalibrationPanel", u"Reset the horizontal boundaries of sample motion", None))
#endif // QT_CONFIG(tooltip)
        self.pushButton_calHorizontalStartRangeSelection.setText(QCoreApplication.translate("CalibrationPanel", u"Start Horizontal Range Selection", None))
        self.label_calibrateRange.setText(QCoreApplication.translate("CalibrationPanel", u"Press Calibrate Horizontal Range", None))
#if QT_CONFIG(tooltip)
        self.pushButton_calHorizontalSetForwardLimit.setToolTip(QCoreApplication.translate("CalibrationPanel", u"Set the current horizontal position as the forward boundary", None))
#endif // QT_CONFIG(tooltip)
        self.pushButton_calHorizontalSetForwardLimit.setText(QCoreApplication.translate("CalibrationPanel", u"Set Forward Limit", None))
#if QT_CONFIG(tooltip)
        self.pushButton_calHorizontalSetBackwardLimit.setToolTip(QCoreApplication.translate("CalibrationPanel", u"Set the current horizontal position as the backward boundary", None))
#endif // QT_CONFIG(tooltip)
        self.pushButton_calHorizontalSetBackwardLimit.setText(QCoreApplication.translate("CalibrationPanel", u"Set Backward Limit", None))
        pass
    # retranslateUi


# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'ui_scan_panel.ui'
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
    QGroupBox, QHBoxLayout, QLabel, QSizePolicy,
    QSlider, QVBoxLayout, QWidget)

from lightsheet.gui.widgets.field_spec_spinbox import FieldSpecSpinBox

class Ui_ScanPanel(object):
    def setupUi(self, scanPanel):
        if not scanPanel.objectName():
            scanPanel.setObjectName(u"scanPanel")
        self.verticalLayout_panel = QVBoxLayout(scanPanel)
        self.verticalLayout_panel.setObjectName(u"verticalLayout_panel")
        self.groupBox_13 = QGroupBox(scanPanel)
        self.groupBox_13.setObjectName(u"groupBox_13")
        self.verticalLayout_45 = QVBoxLayout(self.groupBox_13)
        self.verticalLayout_45.setObjectName(u"verticalLayout_45")
        self.horizontalLayout_69 = QHBoxLayout()
        self.horizontalLayout_69.setObjectName(u"horizontalLayout_69")
        self.verticalLayout_46 = QVBoxLayout()
        self.verticalLayout_46.setObjectName(u"verticalLayout_46")
        self.label_76 = QLabel(self.groupBox_13)
        self.label_76.setObjectName(u"label_76")

        self.verticalLayout_46.addWidget(self.label_76)

        self.line_23 = QFrame(self.groupBox_13)
        self.line_23.setObjectName(u"line_23")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.line_23.sizePolicy().hasHeightForWidth())
        self.line_23.setSizePolicy(sizePolicy)
        self.line_23.setFrameShape(QFrame.Shape.HLine)
        self.line_23.setFrameShadow(QFrame.Shadow.Sunken)

        self.verticalLayout_46.addWidget(self.line_23)

        self.formLayout_16 = QFormLayout()
        self.formLayout_16.setObjectName(u"formLayout_16")
        self.label_78 = QLabel(self.groupBox_13)
        self.label_78.setObjectName(u"label_78")
        sizePolicy1 = QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.label_78.sizePolicy().hasHeightForWidth())
        self.label_78.setSizePolicy(sizePolicy1)

        self.formLayout_16.setWidget(0, QFormLayout.ItemRole.LabelRole, self.label_78)

        self.doubleSpinBox_etlLeftAmplitude = FieldSpecSpinBox(self.groupBox_13)
        self.doubleSpinBox_etlLeftAmplitude.setObjectName(u"doubleSpinBox_etlLeftAmplitude")
        sizePolicy2 = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        sizePolicy2.setHorizontalStretch(0)
        sizePolicy2.setVerticalStretch(0)
        sizePolicy2.setHeightForWidth(self.doubleSpinBox_etlLeftAmplitude.sizePolicy().hasHeightForWidth())
        self.doubleSpinBox_etlLeftAmplitude.setSizePolicy(sizePolicy2)
        self.doubleSpinBox_etlLeftAmplitude.setMinimum(0.000000000000000)
        self.doubleSpinBox_etlLeftAmplitude.setMaximum(5.000000000000000)
        self.doubleSpinBox_etlLeftAmplitude.setSingleStep(0.100000000000000)

        self.formLayout_16.setWidget(0, QFormLayout.ItemRole.FieldRole, self.doubleSpinBox_etlLeftAmplitude)

        self.slider_doubleSpinBox_etlLeftAmplitude = QSlider(self.groupBox_13)
        self.slider_doubleSpinBox_etlLeftAmplitude.setObjectName(u"slider_doubleSpinBox_etlLeftAmplitude")
        self.slider_doubleSpinBox_etlLeftAmplitude.setOrientation(Qt.Horizontal)
        self.slider_doubleSpinBox_etlLeftAmplitude.setMinimumSize(QSize(120, 0))

        self.formLayout_16.setWidget(0, QFormLayout.ItemRole.LabelRole, self.slider_doubleSpinBox_etlLeftAmplitude)

        self.label_79 = QLabel(self.groupBox_13)
        self.label_79.setObjectName(u"label_79")
        sizePolicy1.setHeightForWidth(self.label_79.sizePolicy().hasHeightForWidth())
        self.label_79.setSizePolicy(sizePolicy1)

        self.formLayout_16.setWidget(1, QFormLayout.ItemRole.LabelRole, self.label_79)

        self.doubleSpinBox_etlLeftOffset = FieldSpecSpinBox(self.groupBox_13)
        self.doubleSpinBox_etlLeftOffset.setObjectName(u"doubleSpinBox_etlLeftOffset")
        sizePolicy2.setHeightForWidth(self.doubleSpinBox_etlLeftOffset.sizePolicy().hasHeightForWidth())
        self.doubleSpinBox_etlLeftOffset.setSizePolicy(sizePolicy2)
        self.doubleSpinBox_etlLeftOffset.setMinimum(-5.000000000000000)
        self.doubleSpinBox_etlLeftOffset.setMaximum(5.000000000000000)
        self.doubleSpinBox_etlLeftOffset.setSingleStep(0.100000000000000)

        self.formLayout_16.setWidget(1, QFormLayout.ItemRole.FieldRole, self.doubleSpinBox_etlLeftOffset)


        self.verticalLayout_46.addLayout(self.formLayout_16)


        self.horizontalLayout_69.addLayout(self.verticalLayout_46)

        self.line_24 = QFrame(self.groupBox_13)
        self.line_24.setObjectName(u"line_24")
        sizePolicy.setHeightForWidth(self.line_24.sizePolicy().hasHeightForWidth())
        self.line_24.setSizePolicy(sizePolicy)
        self.line_24.setMinimumSize(QSize(3, 0))
        self.line_24.setMaximumSize(QSize(3, 16777215))
        self.line_24.setFrameShape(QFrame.Shape.VLine)
        self.line_24.setFrameShadow(QFrame.Shadow.Sunken)

        self.horizontalLayout_69.addWidget(self.line_24)

        self.verticalLayout_47 = QVBoxLayout()
        self.verticalLayout_47.setObjectName(u"verticalLayout_47")
        self.label_80 = QLabel(self.groupBox_13)
        self.label_80.setObjectName(u"label_80")

        self.verticalLayout_47.addWidget(self.label_80)

        self.line_25 = QFrame(self.groupBox_13)
        self.line_25.setObjectName(u"line_25")
        sizePolicy.setHeightForWidth(self.line_25.sizePolicy().hasHeightForWidth())
        self.line_25.setSizePolicy(sizePolicy)
        self.line_25.setFrameShape(QFrame.Shape.HLine)
        self.line_25.setFrameShadow(QFrame.Shadow.Sunken)

        self.verticalLayout_47.addWidget(self.line_25)

        self.formLayout_17 = QFormLayout()
        self.formLayout_17.setObjectName(u"formLayout_17")
        self.label_81 = QLabel(self.groupBox_13)
        self.label_81.setObjectName(u"label_81")
        sizePolicy1.setHeightForWidth(self.label_81.sizePolicy().hasHeightForWidth())
        self.label_81.setSizePolicy(sizePolicy1)

        self.formLayout_17.setWidget(0, QFormLayout.ItemRole.LabelRole, self.label_81)

        self.doubleSpinBox_etlRightAmplitude = FieldSpecSpinBox(self.groupBox_13)
        self.doubleSpinBox_etlRightAmplitude.setObjectName(u"doubleSpinBox_etlRightAmplitude")
        sizePolicy2.setHeightForWidth(self.doubleSpinBox_etlRightAmplitude.sizePolicy().hasHeightForWidth())
        self.doubleSpinBox_etlRightAmplitude.setSizePolicy(sizePolicy2)
        self.doubleSpinBox_etlRightAmplitude.setMinimum(0.000000000000000)
        self.doubleSpinBox_etlRightAmplitude.setMaximum(5.000000000000000)
        self.doubleSpinBox_etlRightAmplitude.setSingleStep(0.100000000000000)

        self.formLayout_17.setWidget(0, QFormLayout.ItemRole.FieldRole, self.doubleSpinBox_etlRightAmplitude)

        self.slider_doubleSpinBox_etlRightAmplitude = QSlider(self.groupBox_13)
        self.slider_doubleSpinBox_etlRightAmplitude.setObjectName(u"slider_doubleSpinBox_etlRightAmplitude")
        self.slider_doubleSpinBox_etlRightAmplitude.setOrientation(Qt.Horizontal)
        self.slider_doubleSpinBox_etlRightAmplitude.setMinimumSize(QSize(120, 0))

        self.formLayout_17.setWidget(0, QFormLayout.ItemRole.LabelRole, self.slider_doubleSpinBox_etlRightAmplitude)

        self.label_82 = QLabel(self.groupBox_13)
        self.label_82.setObjectName(u"label_82")
        sizePolicy1.setHeightForWidth(self.label_82.sizePolicy().hasHeightForWidth())
        self.label_82.setSizePolicy(sizePolicy1)

        self.formLayout_17.setWidget(1, QFormLayout.ItemRole.LabelRole, self.label_82)

        self.doubleSpinBox_etlRightOffset = FieldSpecSpinBox(self.groupBox_13)
        self.doubleSpinBox_etlRightOffset.setObjectName(u"doubleSpinBox_etlRightOffset")
        sizePolicy2.setHeightForWidth(self.doubleSpinBox_etlRightOffset.sizePolicy().hasHeightForWidth())
        self.doubleSpinBox_etlRightOffset.setSizePolicy(sizePolicy2)
        self.doubleSpinBox_etlRightOffset.setMinimum(-5.000000000000000)
        self.doubleSpinBox_etlRightOffset.setMaximum(5.000000000000000)
        self.doubleSpinBox_etlRightOffset.setSingleStep(0.100000000000000)
        self.doubleSpinBox_etlRightOffset.setValue(0.000000000000000)

        self.formLayout_17.setWidget(1, QFormLayout.ItemRole.FieldRole, self.doubleSpinBox_etlRightOffset)


        self.verticalLayout_47.addLayout(self.formLayout_17)


        self.horizontalLayout_69.addLayout(self.verticalLayout_47)


        self.verticalLayout_45.addLayout(self.horizontalLayout_69)

        self.checkBox_etlSync = QCheckBox(self.groupBox_13)
        self.checkBox_etlSync.setObjectName(u"checkBox_etlSync")
        sizePolicy.setHeightForWidth(self.checkBox_etlSync.sizePolicy().hasHeightForWidth())
        self.checkBox_etlSync.setSizePolicy(sizePolicy)
        self.checkBox_etlSync.setMinimumSize(QSize(0, 20))
        self.checkBox_etlSync.setMaximumSize(QSize(16777215, 20))
        self.checkBox_etlSync.setLayoutDirection(Qt.LeftToRight)

        self.verticalLayout_45.addWidget(self.checkBox_etlSync)

        self.horizontalLayout_70 = QHBoxLayout()
        self.horizontalLayout_70.setObjectName(u"horizontalLayout_70")
        self.checkBox_etlActivate = QCheckBox(self.groupBox_13)
        self.checkBox_etlActivate.setObjectName(u"checkBox_etlActivate")
        sizePolicy.setHeightForWidth(self.checkBox_etlActivate.sizePolicy().hasHeightForWidth())
        self.checkBox_etlActivate.setSizePolicy(sizePolicy)

        self.horizontalLayout_70.addWidget(self.checkBox_etlActivate)

        self.label_35 = QLabel(self.groupBox_13)
        self.label_35.setObjectName(u"label_35")
        sizePolicy3 = QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        sizePolicy3.setHorizontalStretch(0)
        sizePolicy3.setVerticalStretch(0)
        sizePolicy3.setHeightForWidth(self.label_35.sizePolicy().hasHeightForWidth())
        self.label_35.setSizePolicy(sizePolicy3)

        self.horizontalLayout_70.addWidget(self.label_35)

        self.doubleSpinBox_etlSteps = FieldSpecSpinBox(self.groupBox_13)
        self.doubleSpinBox_etlSteps.setObjectName(u"doubleSpinBox_etlSteps")
        sizePolicy.setHeightForWidth(self.doubleSpinBox_etlSteps.sizePolicy().hasHeightForWidth())
        self.doubleSpinBox_etlSteps.setSizePolicy(sizePolicy)
        self.doubleSpinBox_etlSteps.setDecimals(0)
        self.doubleSpinBox_etlSteps.setMinimum(1.000000000000000)

        self.horizontalLayout_70.addWidget(self.doubleSpinBox_etlSteps)


        self.verticalLayout_45.addLayout(self.horizontalLayout_70)


        self.verticalLayout_panel.addWidget(self.groupBox_13)

        self.groupBox_11 = QGroupBox(scanPanel)
        self.groupBox_11.setObjectName(u"groupBox_11")
        self.verticalLayout_39 = QVBoxLayout(self.groupBox_11)
        self.verticalLayout_39.setObjectName(u"verticalLayout_39")
        self.horizontalLayout_67 = QHBoxLayout()
        self.horizontalLayout_67.setObjectName(u"horizontalLayout_67")
        self.verticalLayout_40 = QVBoxLayout()
        self.verticalLayout_40.setObjectName(u"verticalLayout_40")
        self.label_69 = QLabel(self.groupBox_11)
        self.label_69.setObjectName(u"label_69")

        self.verticalLayout_40.addWidget(self.label_69)

        self.line_8 = QFrame(self.groupBox_11)
        self.line_8.setObjectName(u"line_8")
        sizePolicy.setHeightForWidth(self.line_8.sizePolicy().hasHeightForWidth())
        self.line_8.setSizePolicy(sizePolicy)
        self.line_8.setFrameShape(QFrame.Shape.HLine)
        self.line_8.setFrameShadow(QFrame.Shadow.Sunken)

        self.verticalLayout_40.addWidget(self.line_8)

        self.formLayout_10 = QFormLayout()
        self.formLayout_10.setObjectName(u"formLayout_10")
        self.label_61 = QLabel(self.groupBox_11)
        self.label_61.setObjectName(u"label_61")
        sizePolicy1.setHeightForWidth(self.label_61.sizePolicy().hasHeightForWidth())
        self.label_61.setSizePolicy(sizePolicy1)

        self.formLayout_10.setWidget(0, QFormLayout.ItemRole.LabelRole, self.label_61)

        self.doubleSpinBox_galvoLeftAmplitude = FieldSpecSpinBox(self.groupBox_11)
        self.doubleSpinBox_galvoLeftAmplitude.setObjectName(u"doubleSpinBox_galvoLeftAmplitude")
        sizePolicy2.setHeightForWidth(self.doubleSpinBox_galvoLeftAmplitude.sizePolicy().hasHeightForWidth())
        self.doubleSpinBox_galvoLeftAmplitude.setSizePolicy(sizePolicy2)
        self.doubleSpinBox_galvoLeftAmplitude.setMaximum(10.000000000000000)
        self.doubleSpinBox_galvoLeftAmplitude.setSingleStep(0.100000000000000)

        self.formLayout_10.setWidget(0, QFormLayout.ItemRole.FieldRole, self.doubleSpinBox_galvoLeftAmplitude)

        self.slider_doubleSpinBox_galvoLeftAmplitude = QSlider(self.groupBox_11)
        self.slider_doubleSpinBox_galvoLeftAmplitude.setObjectName(u"slider_doubleSpinBox_galvoLeftAmplitude")
        self.slider_doubleSpinBox_galvoLeftAmplitude.setOrientation(Qt.Horizontal)
        self.slider_doubleSpinBox_galvoLeftAmplitude.setMinimumSize(QSize(120, 0))

        self.formLayout_10.setWidget(0, QFormLayout.ItemRole.LabelRole, self.slider_doubleSpinBox_galvoLeftAmplitude)

        self.label_62 = QLabel(self.groupBox_11)
        self.label_62.setObjectName(u"label_62")
        sizePolicy1.setHeightForWidth(self.label_62.sizePolicy().hasHeightForWidth())
        self.label_62.setSizePolicy(sizePolicy1)

        self.formLayout_10.setWidget(1, QFormLayout.ItemRole.LabelRole, self.label_62)

        self.doubleSpinBox_galvoLeftOffset = FieldSpecSpinBox(self.groupBox_11)
        self.doubleSpinBox_galvoLeftOffset.setObjectName(u"doubleSpinBox_galvoLeftOffset")
        sizePolicy2.setHeightForWidth(self.doubleSpinBox_galvoLeftOffset.sizePolicy().hasHeightForWidth())
        self.doubleSpinBox_galvoLeftOffset.setSizePolicy(sizePolicy2)
        self.doubleSpinBox_galvoLeftOffset.setMinimum(-10.000000000000000)
        self.doubleSpinBox_galvoLeftOffset.setMaximum(10.000000000000000)
        self.doubleSpinBox_galvoLeftOffset.setSingleStep(0.100000000000000)

        self.formLayout_10.setWidget(1, QFormLayout.ItemRole.FieldRole, self.doubleSpinBox_galvoLeftOffset)


        self.verticalLayout_40.addLayout(self.formLayout_10)


        self.horizontalLayout_67.addLayout(self.verticalLayout_40)

        self.line_9 = QFrame(self.groupBox_11)
        self.line_9.setObjectName(u"line_9")
        self.line_9.setMinimumSize(QSize(3, 0))
        self.line_9.setMaximumSize(QSize(3, 16777215))
        self.line_9.setFrameShape(QFrame.Shape.VLine)
        self.line_9.setFrameShadow(QFrame.Shadow.Sunken)

        self.horizontalLayout_67.addWidget(self.line_9)

        self.verticalLayout_41 = QVBoxLayout()
        self.verticalLayout_41.setObjectName(u"verticalLayout_41")
        self.label_70 = QLabel(self.groupBox_11)
        self.label_70.setObjectName(u"label_70")

        self.verticalLayout_41.addWidget(self.label_70)

        self.line_10 = QFrame(self.groupBox_11)
        self.line_10.setObjectName(u"line_10")
        sizePolicy.setHeightForWidth(self.line_10.sizePolicy().hasHeightForWidth())
        self.line_10.setSizePolicy(sizePolicy)
        self.line_10.setFrameShape(QFrame.Shape.HLine)
        self.line_10.setFrameShadow(QFrame.Shadow.Sunken)

        self.verticalLayout_41.addWidget(self.line_10)

        self.formLayout_11 = QFormLayout()
        self.formLayout_11.setObjectName(u"formLayout_11")
        self.label_65 = QLabel(self.groupBox_11)
        self.label_65.setObjectName(u"label_65")
        sizePolicy1.setHeightForWidth(self.label_65.sizePolicy().hasHeightForWidth())
        self.label_65.setSizePolicy(sizePolicy1)

        self.formLayout_11.setWidget(0, QFormLayout.ItemRole.LabelRole, self.label_65)

        self.doubleSpinBox_galvoRightAmplitude = FieldSpecSpinBox(self.groupBox_11)
        self.doubleSpinBox_galvoRightAmplitude.setObjectName(u"doubleSpinBox_galvoRightAmplitude")
        sizePolicy2.setHeightForWidth(self.doubleSpinBox_galvoRightAmplitude.sizePolicy().hasHeightForWidth())
        self.doubleSpinBox_galvoRightAmplitude.setSizePolicy(sizePolicy2)
        self.doubleSpinBox_galvoRightAmplitude.setMaximum(10.000000000000000)
        self.doubleSpinBox_galvoRightAmplitude.setSingleStep(0.100000000000000)

        self.formLayout_11.setWidget(0, QFormLayout.ItemRole.FieldRole, self.doubleSpinBox_galvoRightAmplitude)

        self.slider_doubleSpinBox_galvoRightAmplitude = QSlider(self.groupBox_11)
        self.slider_doubleSpinBox_galvoRightAmplitude.setObjectName(u"slider_doubleSpinBox_galvoRightAmplitude")
        self.slider_doubleSpinBox_galvoRightAmplitude.setOrientation(Qt.Horizontal)
        self.slider_doubleSpinBox_galvoRightAmplitude.setMinimumSize(QSize(120, 0))

        self.formLayout_11.setWidget(0, QFormLayout.ItemRole.LabelRole, self.slider_doubleSpinBox_galvoRightAmplitude)

        self.label_66 = QLabel(self.groupBox_11)
        self.label_66.setObjectName(u"label_66")
        sizePolicy1.setHeightForWidth(self.label_66.sizePolicy().hasHeightForWidth())
        self.label_66.setSizePolicy(sizePolicy1)

        self.formLayout_11.setWidget(1, QFormLayout.ItemRole.LabelRole, self.label_66)

        self.doubleSpinBox_galvoRightOffset = FieldSpecSpinBox(self.groupBox_11)
        self.doubleSpinBox_galvoRightOffset.setObjectName(u"doubleSpinBox_galvoRightOffset")
        sizePolicy2.setHeightForWidth(self.doubleSpinBox_galvoRightOffset.sizePolicy().hasHeightForWidth())
        self.doubleSpinBox_galvoRightOffset.setSizePolicy(sizePolicy2)
        self.doubleSpinBox_galvoRightOffset.setMinimum(-10.000000000000000)
        self.doubleSpinBox_galvoRightOffset.setMaximum(10.000000000000000)
        self.doubleSpinBox_galvoRightOffset.setSingleStep(0.100000000000000)

        self.formLayout_11.setWidget(1, QFormLayout.ItemRole.FieldRole, self.doubleSpinBox_galvoRightOffset)


        self.verticalLayout_41.addLayout(self.formLayout_11)


        self.horizontalLayout_67.addLayout(self.verticalLayout_41)


        self.verticalLayout_39.addLayout(self.horizontalLayout_67)

        self.checkBox_galvoSync = QCheckBox(self.groupBox_11)
        self.checkBox_galvoSync.setObjectName(u"checkBox_galvoSync")
        sizePolicy.setHeightForWidth(self.checkBox_galvoSync.sizePolicy().hasHeightForWidth())
        self.checkBox_galvoSync.setSizePolicy(sizePolicy)
        self.checkBox_galvoSync.setMinimumSize(QSize(0, 20))
        self.checkBox_galvoSync.setMaximumSize(QSize(16777215, 20))
        self.checkBox_galvoSync.setLayoutDirection(Qt.LeftToRight)

        self.verticalLayout_39.addWidget(self.checkBox_galvoSync)

        self.horizontalLayout_4 = QHBoxLayout()
        self.horizontalLayout_4.setObjectName(u"horizontalLayout_4")
        self.checkBox_galvoActivate = QCheckBox(self.groupBox_11)
        self.checkBox_galvoActivate.setObjectName(u"checkBox_galvoActivate")
        sizePolicy.setHeightForWidth(self.checkBox_galvoActivate.sizePolicy().hasHeightForWidth())
        self.checkBox_galvoActivate.setSizePolicy(sizePolicy)
        self.checkBox_galvoActivate.setChecked(True)

        self.horizontalLayout_4.addWidget(self.checkBox_galvoActivate)

        self.checkBox_galvoInvert = QCheckBox(self.groupBox_11)
        self.checkBox_galvoInvert.setObjectName(u"checkBox_galvoInvert")
        sizePolicy.setHeightForWidth(self.checkBox_galvoInvert.sizePolicy().hasHeightForWidth())
        self.checkBox_galvoInvert.setSizePolicy(sizePolicy)

        self.horizontalLayout_4.addWidget(self.checkBox_galvoInvert)


        self.verticalLayout_39.addLayout(self.horizontalLayout_4)


        self.verticalLayout_panel.addWidget(self.groupBox_11)


        self.retranslateUi(scanPanel)

        QMetaObject.connectSlotsByName(scanPanel)
    # setupUi

    def retranslateUi(self, scanPanel):
        self.groupBox_13.setTitle(QCoreApplication.translate("ScanPanel", u"ETLs Settings", None))
        self.label_76.setText(QCoreApplication.translate("ScanPanel", u"<html><head/><body><p><span style=\" font-weight:600;\">Left ETL</span></p></body></html>", None))
        self.label_78.setText(QCoreApplication.translate("ScanPanel", u"Amplitude:", None))
#if QT_CONFIG(tooltip)
        self.doubleSpinBox_etlLeftAmplitude.setToolTip(QCoreApplication.translate("ScanPanel", u"Left ETL sweep amplitude. Unit: V. Valid range: 0\u20135 (clamped by the channel map). Effect: larger amplitude = wider tunable-lens sweep; co-adapt with the laser power when switching wavelength or zoom.", None))
#endif // QT_CONFIG(tooltip)
        self.doubleSpinBox_etlLeftAmplitude.setSuffix(QCoreApplication.translate("ScanPanel", u" V", None))
        self.label_79.setText(QCoreApplication.translate("ScanPanel", u"Offset:", None))
#if QT_CONFIG(tooltip)
        self.doubleSpinBox_etlLeftOffset.setToolTip(QCoreApplication.translate("ScanPanel", u"Left ETL DC offset. Unit: V. Valid range: 0\u20135. Effect: shifts the sweep center; co-adapt with amplitude for the current wavelength/zoom.", None))
#endif // QT_CONFIG(tooltip)
        self.doubleSpinBox_etlLeftOffset.setSuffix(QCoreApplication.translate("ScanPanel", u" V", None))
        self.label_80.setText(QCoreApplication.translate("ScanPanel", u"<html><head/><body><p><span style=\" font-weight:600;\">Right ETL</span></p></body></html>", None))
        self.label_81.setText(QCoreApplication.translate("ScanPanel", u"Amplitude:", None))
#if QT_CONFIG(tooltip)
        self.doubleSpinBox_etlRightAmplitude.setToolTip(QCoreApplication.translate("ScanPanel", u"Right ETL sweep amplitude. Unit: V. Valid range: 0\u20135 (clamped by the channel map). Effect: larger amplitude = wider tunable-lens sweep; co-adapt with the laser power.", None))
#endif // QT_CONFIG(tooltip)
        self.doubleSpinBox_etlRightAmplitude.setSuffix(QCoreApplication.translate("ScanPanel", u" V", None))
        self.label_82.setText(QCoreApplication.translate("ScanPanel", u"Offset:", None))
#if QT_CONFIG(tooltip)
        self.doubleSpinBox_etlRightOffset.setToolTip(QCoreApplication.translate("ScanPanel", u"Right ETL DC offset. Unit: V. Valid range: 0\u20135. Effect: shifts the sweep center; co-adapt with amplitude for the current wavelength/zoom.", None))
#endif // QT_CONFIG(tooltip)
        self.doubleSpinBox_etlRightOffset.setSuffix(QCoreApplication.translate("ScanPanel", u" V", None))
#if QT_CONFIG(tooltip)
        self.checkBox_etlSync.setToolTip(QCoreApplication.translate("ScanPanel", u"Sync Left/Right ETL: when checked, the right ETL mirrors the left. Effect: enable for symmetric light-sheet; disable to tune each ETL independently.", None))
#endif // QT_CONFIG(tooltip)
        self.checkBox_etlSync.setText(QCoreApplication.translate("ScanPanel", u"Sync Left/Right", None))
#if QT_CONFIG(tooltip)
        self.checkBox_etlActivate.setToolTip(QCoreApplication.translate("ScanPanel", u"Activate ETLs: when checked, the ETL sweep is generated on acquisition start. Effect: disable to run the galvo/camera without the tunable lenses.", None))
#endif // QT_CONFIG(tooltip)
        self.checkBox_etlActivate.setText(QCoreApplication.translate("ScanPanel", u"Activate ETLs", None))
        self.label_35.setText(QCoreApplication.translate("ScanPanel", u"ETL Steps:", None))
#if QT_CONFIG(tooltip)
        self.doubleSpinBox_etlSteps.setToolTip(QCoreApplication.translate("ScanPanel", u"Number of ETL voltage steps per sweep. Unit: steps. Valid range: >0. Effect: more steps = smoother sweep but higher DAQ update rate.", None))
#endif // QT_CONFIG(tooltip)
        self.groupBox_11.setTitle(QCoreApplication.translate("ScanPanel", u"Galvanometers Settings", None))
        self.label_69.setText(QCoreApplication.translate("ScanPanel", u"<html><head/><body><p><span style=\" font-weight:600;\">Left Galvo</span></p></body></html>", None))
        self.label_61.setText(QCoreApplication.translate("ScanPanel", u"Amplitude:", None))
#if QT_CONFIG(tooltip)
        self.doubleSpinBox_galvoLeftAmplitude.setToolTip(QCoreApplication.translate("ScanPanel", u"Left galvo scan amplitude. Unit: V. Valid range: \u00b110 (clamped by the channel map). Effect: larger amplitude = wider scan; co-adapt with the ETL amplitude for the current zoom.", None))
#endif // QT_CONFIG(tooltip)
        self.doubleSpinBox_galvoLeftAmplitude.setSuffix(QCoreApplication.translate("ScanPanel", u" V", None))
        self.label_62.setText(QCoreApplication.translate("ScanPanel", u"Offset:", None))
#if QT_CONFIG(tooltip)
        self.doubleSpinBox_galvoLeftOffset.setToolTip(QCoreApplication.translate("ScanPanel", u"Left galvo DC offset. Unit: V. Valid range: \u00b110. Effect: shifts the scan center.", None))
#endif // QT_CONFIG(tooltip)
        self.doubleSpinBox_galvoLeftOffset.setSuffix(QCoreApplication.translate("ScanPanel", u" V", None))
        self.label_70.setText(QCoreApplication.translate("ScanPanel", u"<html><head/><body><p><span style=\" font-weight:600;\">Right Galvo</span></p></body></html>", None))
        self.label_65.setText(QCoreApplication.translate("ScanPanel", u"Amplitude:", None))
#if QT_CONFIG(tooltip)
        self.doubleSpinBox_galvoRightAmplitude.setToolTip(QCoreApplication.translate("ScanPanel", u"Right galvo scan amplitude. Unit: V. Valid range: \u00b110 (clamped by the channel map). Effect: larger amplitude = wider scan.", None))
#endif // QT_CONFIG(tooltip)
        self.doubleSpinBox_galvoRightAmplitude.setSuffix(QCoreApplication.translate("ScanPanel", u" V", None))
        self.label_66.setText(QCoreApplication.translate("ScanPanel", u"Offset:", None))
#if QT_CONFIG(tooltip)
        self.doubleSpinBox_galvoRightOffset.setToolTip(QCoreApplication.translate("ScanPanel", u"Right galvo DC offset. Unit: V. Valid range: \u00b110. Effect: shifts the scan center.", None))
#endif // QT_CONFIG(tooltip)
        self.doubleSpinBox_galvoRightOffset.setSuffix(QCoreApplication.translate("ScanPanel", u" V", None))
#if QT_CONFIG(tooltip)
        self.checkBox_galvoSync.setToolTip(QCoreApplication.translate("ScanPanel", u"Sync Left/Right galvo: when checked, the right galvo mirrors the left. Effect: enable for symmetric scanning; disable to tune each galvo independently.", None))
#endif // QT_CONFIG(tooltip)
        self.checkBox_galvoSync.setText(QCoreApplication.translate("ScanPanel", u"Sync Left/Right", None))
#if QT_CONFIG(tooltip)
        self.checkBox_galvoActivate.setToolTip(QCoreApplication.translate("ScanPanel", u"Activate galvanometers: when checked, the galvo scan is generated on acquisition start. Effect: disable to run the ETL/camera without the galvo scan.", None))
#endif // QT_CONFIG(tooltip)
        self.checkBox_galvoActivate.setText(QCoreApplication.translate("ScanPanel", u"Activate Galvanometers", None))
#if QT_CONFIG(tooltip)
        self.checkBox_galvoInvert.setToolTip(QCoreApplication.translate("ScanPanel", u"Invert scan: when checked, the galvo scan direction is reversed. Effect: use to correct the left/right wiring without re-cabling (verify on the rig first).", None))
#endif // QT_CONFIG(tooltip)
        self.checkBox_galvoInvert.setText(QCoreApplication.translate("ScanPanel", u"Invert scan", None))
        pass
    # retranslateUi


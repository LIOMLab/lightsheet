# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'ui_laser_panel.ui'
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
from PySide6.QtWidgets import (QApplication, QCheckBox, QDoubleSpinBox, QFormLayout,
    QFrame, QGroupBox, QHBoxLayout, QLabel,
    QPushButton, QSizePolicy, QSpacerItem, QVBoxLayout,
    QWidget)

class Ui_LaserPanel(object):
    def setupUi(self, laserPanel):
        if not laserPanel.objectName():
            laserPanel.setObjectName(u"laserPanel")
        self.verticalLayout_panel = QVBoxLayout(laserPanel)
        self.verticalLayout_panel.setObjectName(u"verticalLayout_panel")
        self.groupBox_15 = QGroupBox(laserPanel)
        self.groupBox_15.setObjectName(u"groupBox_15")
        self.horizontalLayout_68 = QHBoxLayout(self.groupBox_15)
        self.horizontalLayout_68.setObjectName(u"horizontalLayout_68")
        self.verticalLayout_43 = QVBoxLayout()
        self.verticalLayout_43.setObjectName(u"verticalLayout_43")
        self.label_72 = QLabel(self.groupBox_15)
        self.label_72.setObjectName(u"label_72")

        self.verticalLayout_43.addWidget(self.label_72)

        self.line_20 = QFrame(self.groupBox_15)
        self.line_20.setObjectName(u"line_20")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.line_20.sizePolicy().hasHeightForWidth())
        self.line_20.setSizePolicy(sizePolicy)
        self.line_20.setFrameShape(QFrame.Shape.HLine)
        self.line_20.setFrameShadow(QFrame.Shadow.Sunken)

        self.verticalLayout_43.addWidget(self.line_20)

        self.formLayout_14 = QFormLayout()
        self.formLayout_14.setObjectName(u"formLayout_14")
        self.label_50 = QLabel(self.groupBox_15)
        self.label_50.setObjectName(u"label_50")
        sizePolicy1 = QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.label_50.sizePolicy().hasHeightForWidth())
        self.label_50.setSizePolicy(sizePolicy1)

        self.formLayout_14.setWidget(0, QFormLayout.ItemRole.LabelRole, self.label_50)

        self.doubleSpinBox_laserOneAmplitude = QDoubleSpinBox(self.groupBox_15)
        self.doubleSpinBox_laserOneAmplitude.setObjectName(u"doubleSpinBox_laserOneAmplitude")
        sizePolicy2 = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        sizePolicy2.setHorizontalStretch(0)
        sizePolicy2.setVerticalStretch(0)
        sizePolicy2.setHeightForWidth(self.doubleSpinBox_laserOneAmplitude.sizePolicy().hasHeightForWidth())
        self.doubleSpinBox_laserOneAmplitude.setSizePolicy(sizePolicy2)
        self.doubleSpinBox_laserOneAmplitude.setDecimals(0)
        self.doubleSpinBox_laserOneAmplitude.setMinimum(0.000000000000000)
        self.doubleSpinBox_laserOneAmplitude.setMaximum(100.000000000000000)
        self.doubleSpinBox_laserOneAmplitude.setSingleStep(1.000000000000000)
        self.doubleSpinBox_laserOneAmplitude.setValue(0.000000000000000)

        self.formLayout_14.setWidget(0, QFormLayout.ItemRole.FieldRole, self.doubleSpinBox_laserOneAmplitude)


        self.verticalLayout_43.addLayout(self.formLayout_14)

        self.checkBox_laserOneAutomatic = QCheckBox(self.groupBox_15)
        self.checkBox_laserOneAutomatic.setObjectName(u"checkBox_laserOneAutomatic")

        self.verticalLayout_43.addWidget(self.checkBox_laserOneAutomatic)

        self.label_laserOneStatus = QLabel(self.groupBox_15)
        self.label_laserOneStatus.setObjectName(u"label_laserOneStatus")
        self.label_laserOneStatus.setMinimumSize(QSize(140, 0))
        self.label_laserOneStatus.setStyleSheet(u"color: #8E8E93; font-weight: bold;")

        self.verticalLayout_43.addWidget(self.label_laserOneStatus)

        self.label_laserOneReadback = QLabel(self.groupBox_15)
        self.label_laserOneReadback.setObjectName(u"label_laserOneReadback")
        self.label_laserOneReadback.setMinimumSize(QSize(80, 0))

        self.verticalLayout_43.addWidget(self.label_laserOneReadback)

        self.verticalSpacer_8 = QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.verticalLayout_43.addItem(self.verticalSpacer_8)


        self.horizontalLayout_68.addLayout(self.verticalLayout_43)

        self.line_21 = QFrame(self.groupBox_15)
        self.line_21.setObjectName(u"line_21")
        self.line_21.setFrameShape(QFrame.Shape.VLine)
        self.line_21.setFrameShadow(QFrame.Shadow.Sunken)

        self.horizontalLayout_68.addWidget(self.line_21)

        self.verticalLayout_44 = QVBoxLayout()
        self.verticalLayout_44.setObjectName(u"verticalLayout_44")
        self.label_73 = QLabel(self.groupBox_15)
        self.label_73.setObjectName(u"label_73")

        self.verticalLayout_44.addWidget(self.label_73)

        self.line_22 = QFrame(self.groupBox_15)
        self.line_22.setObjectName(u"line_22")
        sizePolicy.setHeightForWidth(self.line_22.sizePolicy().hasHeightForWidth())
        self.line_22.setSizePolicy(sizePolicy)
        self.line_22.setFrameShape(QFrame.Shape.HLine)
        self.line_22.setFrameShadow(QFrame.Shadow.Sunken)

        self.verticalLayout_44.addWidget(self.line_22)

        self.formLayout_15 = QFormLayout()
        self.formLayout_15.setObjectName(u"formLayout_15")
        self.label_74 = QLabel(self.groupBox_15)
        self.label_74.setObjectName(u"label_74")
        sizePolicy1.setHeightForWidth(self.label_74.sizePolicy().hasHeightForWidth())
        self.label_74.setSizePolicy(sizePolicy1)

        self.formLayout_15.setWidget(0, QFormLayout.ItemRole.LabelRole, self.label_74)

        self.doubleSpinBox_laserTwoAmplitude = QDoubleSpinBox(self.groupBox_15)
        self.doubleSpinBox_laserTwoAmplitude.setObjectName(u"doubleSpinBox_laserTwoAmplitude")
        sizePolicy2.setHeightForWidth(self.doubleSpinBox_laserTwoAmplitude.sizePolicy().hasHeightForWidth())
        self.doubleSpinBox_laserTwoAmplitude.setSizePolicy(sizePolicy2)
        self.doubleSpinBox_laserTwoAmplitude.setDecimals(0)
        self.doubleSpinBox_laserTwoAmplitude.setMaximum(100.000000000000000)
        self.doubleSpinBox_laserTwoAmplitude.setSingleStep(1.000000000000000)

        self.formLayout_15.setWidget(0, QFormLayout.ItemRole.FieldRole, self.doubleSpinBox_laserTwoAmplitude)


        self.verticalLayout_44.addLayout(self.formLayout_15)

        self.checkBox_laserTwoAutomatic = QCheckBox(self.groupBox_15)
        self.checkBox_laserTwoAutomatic.setObjectName(u"checkBox_laserTwoAutomatic")

        self.verticalLayout_44.addWidget(self.checkBox_laserTwoAutomatic)

        self.label_laserTwoStatus = QLabel(self.groupBox_15)
        self.label_laserTwoStatus.setObjectName(u"label_laserTwoStatus")
        self.label_laserTwoStatus.setMinimumSize(QSize(140, 0))
        self.label_laserTwoStatus.setStyleSheet(u"color: #8E8E93; font-weight: bold;")

        self.verticalLayout_44.addWidget(self.label_laserTwoStatus)

        self.label_laserTwoReadback = QLabel(self.groupBox_15)
        self.label_laserTwoReadback.setObjectName(u"label_laserTwoReadback")
        self.label_laserTwoReadback.setMinimumSize(QSize(80, 0))

        self.verticalLayout_44.addWidget(self.label_laserTwoReadback)

        self.pushButton_laserTwoRefresh = QPushButton(self.groupBox_15)
        self.pushButton_laserTwoRefresh.setObjectName(u"pushButton_laserTwoRefresh")

        self.verticalLayout_44.addWidget(self.pushButton_laserTwoRefresh)

        self.verticalSpacer_15 = QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.verticalLayout_44.addItem(self.verticalSpacer_15)


        self.horizontalLayout_68.addLayout(self.verticalLayout_44)


        self.verticalLayout_panel.addWidget(self.groupBox_15)

        self.groupBox_4 = QGroupBox(laserPanel)
        self.groupBox_4.setObjectName(u"groupBox_4")
        sizePolicy2.setHeightForWidth(self.groupBox_4.sizePolicy().hasHeightForWidth())
        self.groupBox_4.setSizePolicy(sizePolicy2)
        self.groupBox_4.setMinimumSize(QSize(140, 126))
        self.verticalLayout_7 = QVBoxLayout(self.groupBox_4)
        self.verticalLayout_7.setObjectName(u"verticalLayout_7")
        self.verticalLayout_17 = QVBoxLayout()
        self.verticalLayout_17.setObjectName(u"verticalLayout_17")
        self.pushButton_laserOneToggle = QPushButton(self.groupBox_4)
        self.pushButton_laserOneToggle.setObjectName(u"pushButton_laserOneToggle")
        sizePolicy2.setHeightForWidth(self.pushButton_laserOneToggle.sizePolicy().hasHeightForWidth())
        self.pushButton_laserOneToggle.setSizePolicy(sizePolicy2)
        self.pushButton_laserOneToggle.setCheckable(True)

        self.verticalLayout_17.addWidget(self.pushButton_laserOneToggle)

        self.pushButton_laserTwoToggle = QPushButton(self.groupBox_4)
        self.pushButton_laserTwoToggle.setObjectName(u"pushButton_laserTwoToggle")
        sizePolicy2.setHeightForWidth(self.pushButton_laserTwoToggle.sizePolicy().hasHeightForWidth())
        self.pushButton_laserTwoToggle.setSizePolicy(sizePolicy2)
        self.pushButton_laserTwoToggle.setCheckable(True)

        self.verticalLayout_17.addWidget(self.pushButton_laserTwoToggle)

        self.verticalSpacer_12 = QSpacerItem(20, 1, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.verticalLayout_17.addItem(self.verticalSpacer_12)


        self.verticalLayout_7.addLayout(self.verticalLayout_17)


        self.verticalLayout_panel.addWidget(self.groupBox_4)


        self.retranslateUi(laserPanel)

        QMetaObject.connectSlotsByName(laserPanel)
    # setupUi

    def retranslateUi(self, laserPanel):
        self.groupBox_15.setTitle(QCoreApplication.translate("LaserPanel", u"Lasers Settings", None))
        self.label_72.setText(QCoreApplication.translate("LaserPanel", u"<html><head/><body><p><span style=\" font-weight:600;\">Laser1</span></p></body></html>", None))
        self.label_50.setText(QCoreApplication.translate("LaserPanel", u"Power:", None))
        self.doubleSpinBox_laserOneAmplitude.setSuffix(QCoreApplication.translate("LaserPanel", u" %", None))
        self.checkBox_laserOneAutomatic.setText(QCoreApplication.translate("LaserPanel", u"Auto On/Off", None))
#if QT_CONFIG(tooltip)
        self.label_laserOneStatus.setToolTip(QCoreApplication.translate("LaserPanel", u"Laser 1 emission state (ON / OFF / ERR)", None))
#endif // QT_CONFIG(tooltip)
        self.label_laserOneStatus.setText(QCoreApplication.translate("LaserPanel", u"\u25cf OFF", None))
#if QT_CONFIG(tooltip)
        self.label_laserOneReadback.setToolTip(QCoreApplication.translate("LaserPanel", u"Linear-through-origin estimate (mW = V * mW_per_volt). Unverified \u2014 the linear model predicts 300 mW at 5V, but the rig-measured output is ~107.5 mW at 5V (DPSS threshold knee + free-space measurement geometry). Run the rig calibration sweep to load a measured V->mW curve.", None))
#endif // QT_CONFIG(tooltip)
        self.label_laserOneReadback.setText(QCoreApplication.translate("LaserPanel", u"0.0 mW (est.)", None))
        self.label_73.setText(QCoreApplication.translate("LaserPanel", u"<html><head/><body><p><span style=\" font-weight:600;\">Laser2</span></p></body></html>", None))
        self.label_74.setText(QCoreApplication.translate("LaserPanel", u"Power:", None))
        self.doubleSpinBox_laserTwoAmplitude.setSuffix(QCoreApplication.translate("LaserPanel", u" %", None))
        self.checkBox_laserTwoAutomatic.setText(QCoreApplication.translate("LaserPanel", u"Auto On/Off", None))
#if QT_CONFIG(tooltip)
        self.label_laserTwoStatus.setToolTip(QCoreApplication.translate("LaserPanel", u"Laser 2 emission state (ON / OFF / ERR)", None))
#endif // QT_CONFIG(tooltip)
        self.label_laserTwoStatus.setText(QCoreApplication.translate("LaserPanel", u"\u25cf OFF", None))
#if QT_CONFIG(tooltip)
        self.label_laserTwoReadback.setToolTip(QCoreApplication.translate("LaserPanel", u"iBeam power readback \u2014 click Refresh Power to re-query", None))
#endif // QT_CONFIG(tooltip)
        self.label_laserTwoReadback.setText(QCoreApplication.translate("LaserPanel", u"N/A", None))
#if QT_CONFIG(tooltip)
        self.pushButton_laserTwoRefresh.setToolTip(QCoreApplication.translate("LaserPanel", u"Re-query iBeam status and power readback now (skipped while a power write is in progress)", None))
#endif // QT_CONFIG(tooltip)
        self.pushButton_laserTwoRefresh.setText(QCoreApplication.translate("LaserPanel", u"Refresh Power", None))
        self.groupBox_4.setTitle(QCoreApplication.translate("LaserPanel", u"Lasers", None))
#if QT_CONFIG(tooltip)
        self.pushButton_laserOneToggle.setToolTip(QCoreApplication.translate("LaserPanel", u"Activate left laser", None))
#endif // QT_CONFIG(tooltip)
        self.pushButton_laserOneToggle.setText(QCoreApplication.translate("LaserPanel", u"Toggle Laser1", None))
#if QT_CONFIG(tooltip)
        self.pushButton_laserTwoToggle.setToolTip(QCoreApplication.translate("LaserPanel", u"Activate right laser", None))
#endif // QT_CONFIG(tooltip)
        self.pushButton_laserTwoToggle.setText(QCoreApplication.translate("LaserPanel", u"Toggle Laser2", None))
        pass
    # retranslateUi


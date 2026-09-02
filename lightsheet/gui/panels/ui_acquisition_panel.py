# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'ui_acquisition_panel.ui'
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
from PySide6.QtWidgets import (QApplication, QComboBox, QFormLayout, QFrame,
    QGroupBox, QLabel, QPushButton, QSizePolicy,
    QSpacerItem, QVBoxLayout, QWidget)

from lightsheet.gui.styles import spacing as _s
from lightsheet.gui.widgets.field_spec_spinbox import FieldSpecSpinBox

class Ui_AcquisitionPanel(object):
    def setupUi(self, acquisitionPanel):
        if not acquisitionPanel.objectName():
            acquisitionPanel.setObjectName(u"acquisitionPanel")
        self.verticalLayout_panel = QVBoxLayout(acquisitionPanel)
        self.verticalLayout_panel.setObjectName(u"verticalLayout_panel")
        self.groupBox_17 = QGroupBox(acquisitionPanel)
        self.groupBox_17.setObjectName(u"groupBox_17")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.groupBox_17.sizePolicy().hasHeightForWidth())
        self.groupBox_17.setSizePolicy(sizePolicy)
        self.groupBox_17.setMinimumSize(QSize(_s.ZERO, _s.PANEL_FLOOR))
        self.verticalLayout_53 = QVBoxLayout(self.groupBox_17)
        self.verticalLayout_53.setObjectName(u"verticalLayout_53")
        self.verticalLayout_15 = QVBoxLayout()
        self.verticalLayout_15.setObjectName(u"verticalLayout_15")
        self.pushButton_acqGetSingleImage = QPushButton(self.groupBox_17)
        self.pushButton_acqGetSingleImage.setObjectName(u"pushButton_acqGetSingleImage")
        sizePolicy1 = QSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.pushButton_acqGetSingleImage.sizePolicy().hasHeightForWidth())
        self.pushButton_acqGetSingleImage.setSizePolicy(sizePolicy1)

        self.verticalLayout_15.addWidget(self.pushButton_acqGetSingleImage)

        self.pushButton_acqStartLiveMode = QPushButton(self.groupBox_17)
        self.pushButton_acqStartLiveMode.setObjectName(u"pushButton_acqStartLiveMode")
        sizePolicy.setHeightForWidth(self.pushButton_acqStartLiveMode.sizePolicy().hasHeightForWidth())
        self.pushButton_acqStartLiveMode.setSizePolicy(sizePolicy)

        self.verticalLayout_15.addWidget(self.pushButton_acqStartLiveMode)

        self.verticalSpacer_13 = QSpacerItem(_s.LG + _s.XS, _s.XS, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.verticalLayout_15.addItem(self.verticalSpacer_13)

        self.line_7 = QFrame(self.groupBox_17)
        self.line_7.setObjectName(u"line_7")
        self.line_7.setFrameShape(QFrame.Shape.HLine)
        self.line_7.setFrameShadow(QFrame.Shadow.Sunken)

        self.verticalLayout_15.addWidget(self.line_7)

        self.pushButton_acqStartPreviewMode = QPushButton(self.groupBox_17)
        self.pushButton_acqStartPreviewMode.setObjectName(u"pushButton_acqStartPreviewMode")
        sizePolicy.setHeightForWidth(self.pushButton_acqStartPreviewMode.sizePolicy().hasHeightForWidth())
        self.pushButton_acqStartPreviewMode.setSizePolicy(sizePolicy)

        self.verticalLayout_15.addWidget(self.pushButton_acqStartPreviewMode)


        self.verticalLayout_53.addLayout(self.verticalLayout_15)


        self.verticalLayout_panel.addWidget(self.groupBox_17)

        self.groupBox_12 = QGroupBox(acquisitionPanel)
        self.groupBox_12.setObjectName(u"groupBox_12")
        self.formLayout = QFormLayout(self.groupBox_12)
        self.formLayout.setObjectName(u"formLayout")
        self.formLayout.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)  # ty: ignore[unresolved-attribute]
        self.label_9 = QLabel(self.groupBox_12)
        self.label_9.setObjectName(u"label_9")

        self.formLayout.setWidget(1, QFormLayout.ItemRole.LabelRole, self.label_9)

        self.comboBox_cameraShutterMode = QComboBox(self.groupBox_12)
        self.comboBox_cameraShutterMode.setObjectName(u"comboBox_cameraShutterMode")
        self.comboBox_cameraShutterMode.setSizeAdjustPolicy(QComboBox.AdjustToContents)  # ty: ignore[unresolved-attribute]
        self.comboBox_cameraShutterMode.setMinimumContentsLength(12)

        self.formLayout.setWidget(1, QFormLayout.ItemRole.FieldRole, self.comboBox_cameraShutterMode)

        self.label_doubleSpinBox_cameraExposureTime = QLabel(self.groupBox_12)
        self.label_doubleSpinBox_cameraExposureTime.setObjectName(u"label_doubleSpinBox_cameraExposureTime")

        self.formLayout.setWidget(2, QFormLayout.ItemRole.LabelRole, self.label_doubleSpinBox_cameraExposureTime)

        self.doubleSpinBox_cameraExposureTime = FieldSpecSpinBox(self.groupBox_12)
        self.doubleSpinBox_cameraExposureTime.setObjectName(u"doubleSpinBox_cameraExposureTime")
        self.doubleSpinBox_cameraExposureTime.setDecimals(0)
        self.doubleSpinBox_cameraExposureTime.setMinimum(25.000000000000000)
        self.doubleSpinBox_cameraExposureTime.setMaximum(1000.000000000000000)
        self.doubleSpinBox_cameraExposureTime.setSingleStep(5.000000000000000)
        self.doubleSpinBox_cameraExposureTime.setValue(25.000000000000000)

        self.formLayout.setWidget(2, QFormLayout.ItemRole.FieldRole, self.doubleSpinBox_cameraExposureTime)

        self.label_doubleSpinBox_cameraLineTime = QLabel(self.groupBox_12)
        self.label_doubleSpinBox_cameraLineTime.setObjectName(u"label_doubleSpinBox_cameraLineTime")

        self.formLayout.setWidget(3, QFormLayout.ItemRole.LabelRole, self.label_doubleSpinBox_cameraLineTime)

        self.doubleSpinBox_cameraLineTime = FieldSpecSpinBox(self.groupBox_12)
        self.doubleSpinBox_cameraLineTime.setObjectName(u"doubleSpinBox_cameraLineTime")
        self.doubleSpinBox_cameraLineTime.setDecimals(3)
        self.doubleSpinBox_cameraLineTime.setMinimum(12.175000000000001)
        self.doubleSpinBox_cameraLineTime.setMaximum(500.000000000000000)

        self.formLayout.setWidget(3, QFormLayout.ItemRole.FieldRole, self.doubleSpinBox_cameraLineTime)

        self.label_doubleSpinBox_cameraExposedLines = QLabel(self.groupBox_12)
        self.label_doubleSpinBox_cameraExposedLines.setObjectName(u"label_doubleSpinBox_cameraExposedLines")

        self.formLayout.setWidget(4, QFormLayout.ItemRole.LabelRole, self.label_doubleSpinBox_cameraExposedLines)

        self.doubleSpinBox_cameraExposedLines = FieldSpecSpinBox(self.groupBox_12)
        self.doubleSpinBox_cameraExposedLines.setObjectName(u"doubleSpinBox_cameraExposedLines")
        self.doubleSpinBox_cameraExposedLines.setDecimals(0)
        self.doubleSpinBox_cameraExposedLines.setMinimum(1.000000000000000)
        self.doubleSpinBox_cameraExposedLines.setMaximum(1024.000000000000000)

        self.formLayout.setWidget(4, QFormLayout.ItemRole.FieldRole, self.doubleSpinBox_cameraExposedLines)

        self.label_doubleSpinBox_cameraDelayLines = QLabel(self.groupBox_12)
        self.label_doubleSpinBox_cameraDelayLines.setObjectName(u"label_doubleSpinBox_cameraDelayLines")

        self.formLayout.setWidget(5, QFormLayout.ItemRole.LabelRole, self.label_doubleSpinBox_cameraDelayLines)

        self.doubleSpinBox_cameraDelayLines = FieldSpecSpinBox(self.groupBox_12)
        self.doubleSpinBox_cameraDelayLines.setObjectName(u"doubleSpinBox_cameraDelayLines")
        self.doubleSpinBox_cameraDelayLines.setDecimals(0)
        self.doubleSpinBox_cameraDelayLines.setMaximum(1024.000000000000000)

        self.formLayout.setWidget(5, QFormLayout.ItemRole.FieldRole, self.doubleSpinBox_cameraDelayLines)


        self.verticalLayout_panel.addWidget(self.groupBox_12)


        self.retranslateUi(acquisitionPanel)

        QMetaObject.connectSlotsByName(acquisitionPanel)
    # setupUi

    def retranslateUi(self, acquisitionPanel):
        self.groupBox_17.setTitle(QCoreApplication.translate("AcquisitionPanel", u"Manual Acquisition", None))
#if QT_CONFIG(tooltip)
        self.pushButton_acqGetSingleImage.setToolTip(QCoreApplication.translate("AcquisitionPanel", u"Start single image acquisition", None))
#endif // QT_CONFIG(tooltip)
        self.pushButton_acqGetSingleImage.setText(QCoreApplication.translate("AcquisitionPanel", u"Get Single Image", None))
#if QT_CONFIG(shortcut)
        self.pushButton_acqGetSingleImage.setShortcut(QCoreApplication.translate("AcquisitionPanel", u"Ctrl+I", None))
#endif // QT_CONFIG(shortcut)
#if QT_CONFIG(tooltip)
        self.pushButton_acqStartLiveMode.setToolTip(QCoreApplication.translate("AcquisitionPanel", u"Start live mode", None))
#endif // QT_CONFIG(tooltip)
        self.pushButton_acqStartLiveMode.setText(QCoreApplication.translate("AcquisitionPanel", u"Start Live Mode", None))
#if QT_CONFIG(shortcut)
        self.pushButton_acqStartLiveMode.setShortcut(QCoreApplication.translate("AcquisitionPanel", u"Ctrl+L", None))
#endif // QT_CONFIG(shortcut)
#if QT_CONFIG(tooltip)
        self.pushButton_acqStartPreviewMode.setToolTip(QCoreApplication.translate("AcquisitionPanel", u"Start preview mode", None))
#endif // QT_CONFIG(tooltip)
        self.pushButton_acqStartPreviewMode.setText(QCoreApplication.translate("AcquisitionPanel", u"Camera Preview Mode", None))
#if QT_CONFIG(shortcut)
        self.pushButton_acqStartPreviewMode.setShortcut(QCoreApplication.translate("AcquisitionPanel", u"Ctrl+P", None))
#endif // QT_CONFIG(shortcut)
        self.groupBox_12.setTitle(QCoreApplication.translate("AcquisitionPanel", u"Camera Settings", None))
        self.label_9.setText(QCoreApplication.translate("AcquisitionPanel", u"Shutter Mode:", None))
        self.label_doubleSpinBox_cameraExposureTime.setText(QCoreApplication.translate("AcquisitionPanel", u"Exposure Time:", None))
#if QT_CONFIG(tooltip)
        self.doubleSpinBox_cameraExposureTime.setToolTip(QCoreApplication.translate("AcquisitionPanel", u"Camera exposure time per line. Unit: ms. Valid range: per the PCO camera limits. Effect: longer exposure = brighter image but slower acquisition.", None))
#endif // QT_CONFIG(tooltip)
        self.doubleSpinBox_cameraExposureTime.setPrefix("")
        self.doubleSpinBox_cameraExposureTime.setSuffix(QCoreApplication.translate("AcquisitionPanel", u" ms", None))
        self.label_doubleSpinBox_cameraLineTime.setText(QCoreApplication.translate("AcquisitionPanel", u"Line Time:", None))
#if QT_CONFIG(tooltip)
        self.doubleSpinBox_cameraLineTime.setToolTip(QCoreApplication.translate("AcquisitionPanel", u"Camera line time (exposure + readout). Unit: ms. Valid range: per the PCO camera limits. Effect: sets the line period; must be >= exposure time.", None))
#endif // QT_CONFIG(tooltip)
        self.doubleSpinBox_cameraLineTime.setSuffix(QCoreApplication.translate("AcquisitionPanel", u" \u03bcs", None))
        self.label_doubleSpinBox_cameraExposedLines.setText(QCoreApplication.translate("AcquisitionPanel", u"Exposed Lines:", None))
#if QT_CONFIG(tooltip)
        self.doubleSpinBox_cameraExposedLines.setToolTip(QCoreApplication.translate("AcquisitionPanel", u"Number of exposed lines per frame. Unit: lines. Valid range: >0. Effect: sets the frame height in lines.", None))
#endif // QT_CONFIG(tooltip)
        self.label_doubleSpinBox_cameraDelayLines.setText(QCoreApplication.translate("AcquisitionPanel", u"Delay Lines:", None))
#if QT_CONFIG(tooltip)
        self.doubleSpinBox_cameraDelayLines.setToolTip(QCoreApplication.translate("AcquisitionPanel", u"Number of delay (non-exposed) lines before the exposed region. Unit: lines. Valid range: >=0. Effect: shifts the trigger timing relative to the galvo/ETL sweep.", None))
#endif // QT_CONFIG(tooltip)
        pass
    # retranslateUi


# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'ui_properties.ui'
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
from PySide6.QtWidgets import (QApplication, QDialog, QFormLayout, QGroupBox,
    QLabel, QPushButton, QSizePolicy, QSpacerItem,
    QVBoxLayout, QWidget)

from lightsheet.gui.styles import spacing as _s

class Ui_Properties(object):
    def setupUi(self, Properties):
        if not Properties.objectName():
            Properties.setObjectName(u"Properties")
        Properties.resize(223, 403)
        self.verticalLayout = QVBoxLayout(Properties)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.groupBox_2 = QGroupBox(Properties)
        self.groupBox_2.setObjectName(u"groupBox_2")
        self.formLayout = QFormLayout(self.groupBox_2)
        self.formLayout.setObjectName(u"formLayout")
        self.label = QLabel(self.groupBox_2)
        self.label.setObjectName(u"label")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.label.sizePolicy().hasHeightForWidth())
        self.label.setSizePolicy(sizePolicy)

        self.formLayout.setWidget(1, QFormLayout.ItemRole.LabelRole, self.label)

        self.label_cameraName = QLabel(self.groupBox_2)
        self.label_cameraName.setObjectName(u"label_cameraName")

        self.formLayout.setWidget(1, QFormLayout.ItemRole.FieldRole, self.label_cameraName)

        self.label_4 = QLabel(self.groupBox_2)
        self.label_4.setObjectName(u"label_4")

        self.formLayout.setWidget(4, QFormLayout.ItemRole.LabelRole, self.label_4)

        self.label_cameraTemperature = QLabel(self.groupBox_2)
        self.label_cameraTemperature.setObjectName(u"label_cameraTemperature")

        self.formLayout.setWidget(4, QFormLayout.ItemRole.FieldRole, self.label_cameraTemperature)

        self.label_5 = QLabel(self.groupBox_2)
        self.label_5.setObjectName(u"label_5")

        self.formLayout.setWidget(5, QFormLayout.ItemRole.LabelRole, self.label_5)

        self.label_sensorTemperature = QLabel(self.groupBox_2)
        self.label_sensorTemperature.setObjectName(u"label_sensorTemperature")

        self.formLayout.setWidget(5, QFormLayout.ItemRole.FieldRole, self.label_sensorTemperature)

        self.label_7 = QLabel(self.groupBox_2)
        self.label_7.setObjectName(u"label_7")

        self.formLayout.setWidget(8, QFormLayout.ItemRole.LabelRole, self.label_7)

        self.label_triggerMode = QLabel(self.groupBox_2)
        self.label_triggerMode.setObjectName(u"label_triggerMode")

        self.formLayout.setWidget(8, QFormLayout.ItemRole.FieldRole, self.label_triggerMode)

        self.verticalSpacer = QSpacerItem(_s.LG + _s.XS, _s.XL + _s.LG, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.formLayout.setItem(3, QFormLayout.ItemRole.LabelRole, self.verticalSpacer)

        self.verticalSpacer_2 = QSpacerItem(_s.LG + _s.XS, _s.XL + _s.LG, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.formLayout.setItem(7, QFormLayout.ItemRole.LabelRole, self.verticalSpacer_2)

        self.label_8 = QLabel(self.groupBox_2)
        self.label_8.setObjectName(u"label_8")

        self.formLayout.setWidget(6, QFormLayout.ItemRole.LabelRole, self.label_8)

        self.label_powerTemperature = QLabel(self.groupBox_2)
        self.label_powerTemperature.setObjectName(u"label_powerTemperature")

        self.formLayout.setWidget(6, QFormLayout.ItemRole.FieldRole, self.label_powerTemperature)

        self.label_9 = QLabel(self.groupBox_2)
        self.label_9.setObjectName(u"label_9")

        self.formLayout.setWidget(9, QFormLayout.ItemRole.LabelRole, self.label_9)

        self.label_delayTime = QLabel(self.groupBox_2)
        self.label_delayTime.setObjectName(u"label_delayTime")

        self.formLayout.setWidget(9, QFormLayout.ItemRole.FieldRole, self.label_delayTime)

        self.label_11 = QLabel(self.groupBox_2)
        self.label_11.setObjectName(u"label_11")

        self.formLayout.setWidget(10, QFormLayout.ItemRole.LabelRole, self.label_11)

        self.label_exposureTime = QLabel(self.groupBox_2)
        self.label_exposureTime.setObjectName(u"label_exposureTime")

        self.formLayout.setWidget(10, QFormLayout.ItemRole.FieldRole, self.label_exposureTime)

        self.verticalSpacer_3 = QSpacerItem(_s.LG + _s.XS, _s.XL + _s.LG, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.formLayout.setItem(11, QFormLayout.ItemRole.LabelRole, self.verticalSpacer_3)

        self.label_10 = QLabel(self.groupBox_2)
        self.label_10.setObjectName(u"label_10")

        self.formLayout.setWidget(12, QFormLayout.ItemRole.LabelRole, self.label_10)

        self.label_acquireMode = QLabel(self.groupBox_2)
        self.label_acquireMode.setObjectName(u"label_acquireMode")

        self.formLayout.setWidget(12, QFormLayout.ItemRole.FieldRole, self.label_acquireMode)

        self.label_12 = QLabel(self.groupBox_2)
        self.label_12.setObjectName(u"label_12")

        self.formLayout.setWidget(13, QFormLayout.ItemRole.LabelRole, self.label_12)

        self.label_storageMode = QLabel(self.groupBox_2)
        self.label_storageMode.setObjectName(u"label_storageMode")

        self.formLayout.setWidget(13, QFormLayout.ItemRole.FieldRole, self.label_storageMode)

        self.label_13 = QLabel(self.groupBox_2)
        self.label_13.setObjectName(u"label_13")

        self.formLayout.setWidget(14, QFormLayout.ItemRole.LabelRole, self.label_13)

        self.label_recorderMode = QLabel(self.groupBox_2)
        self.label_recorderMode.setObjectName(u"label_recorderMode")

        self.formLayout.setWidget(14, QFormLayout.ItemRole.FieldRole, self.label_recorderMode)

        self.label_14 = QLabel(self.groupBox_2)
        self.label_14.setObjectName(u"label_14")

        self.formLayout.setWidget(2, QFormLayout.ItemRole.LabelRole, self.label_14)

        self.label_imageSize = QLabel(self.groupBox_2)
        self.label_imageSize.setObjectName(u"label_imageSize")

        self.formLayout.setWidget(2, QFormLayout.ItemRole.FieldRole, self.label_imageSize)


        self.verticalLayout.addWidget(self.groupBox_2)

        self.groupBox_3 = QGroupBox(Properties)
        self.groupBox_3.setObjectName(u"groupBox_3")
        self.formLayout_2 = QFormLayout(self.groupBox_3)
        self.formLayout_2.setObjectName(u"formLayout_2")
        self.label_3 = QLabel(self.groupBox_3)
        self.label_3.setObjectName(u"label_3")

        self.formLayout_2.setWidget(1, QFormLayout.ItemRole.LabelRole, self.label_3)

        self.label_horizontalMotorName = QLabel(self.groupBox_3)
        self.label_horizontalMotorName.setObjectName(u"label_horizontalMotorName")

        self.formLayout_2.setWidget(1, QFormLayout.ItemRole.FieldRole, self.label_horizontalMotorName)

        self.label_2 = QLabel(self.groupBox_3)
        self.label_2.setObjectName(u"label_2")
        sizePolicy.setHeightForWidth(self.label_2.sizePolicy().hasHeightForWidth())
        self.label_2.setSizePolicy(sizePolicy)

        self.formLayout_2.setWidget(2, QFormLayout.ItemRole.LabelRole, self.label_2)

        self.label_verticalMotorName = QLabel(self.groupBox_3)
        self.label_verticalMotorName.setObjectName(u"label_verticalMotorName")

        self.formLayout_2.setWidget(2, QFormLayout.ItemRole.FieldRole, self.label_verticalMotorName)

        self.label_6 = QLabel(self.groupBox_3)
        self.label_6.setObjectName(u"label_6")

        self.formLayout_2.setWidget(3, QFormLayout.ItemRole.LabelRole, self.label_6)

        self.label_cameraMotorName = QLabel(self.groupBox_3)
        self.label_cameraMotorName.setObjectName(u"label_cameraMotorName")

        self.formLayout_2.setWidget(3, QFormLayout.ItemRole.FieldRole, self.label_cameraMotorName)


        self.verticalLayout.addWidget(self.groupBox_3)

        self.pushButton_refresh = QPushButton(Properties)
        self.pushButton_refresh.setObjectName(u"pushButton_refresh")

        self.verticalLayout.addWidget(self.pushButton_refresh)


        self.retranslateUi(Properties)

        QMetaObject.connectSlotsByName(Properties)
    # setupUi

    def retranslateUi(self, Properties):
        Properties.setWindowTitle(QCoreApplication.translate("Properties", u"System Properties", None))
        self.groupBox_2.setTitle(QCoreApplication.translate("Properties", u"Camera Properties", None))
        self.label.setText(QCoreApplication.translate("Properties", u"Camera Model:", None))
        self.label_cameraName.setText(QCoreApplication.translate("Properties", u"None", None))
        self.label_4.setText(QCoreApplication.translate("Properties", u"Internal Temperature:", None))
        self.label_cameraTemperature.setText(QCoreApplication.translate("Properties", u"None", None))
        self.label_5.setText(QCoreApplication.translate("Properties", u"Image Sensor Temperature:", None))
        self.label_sensorTemperature.setText(QCoreApplication.translate("Properties", u"None", None))
        self.label_7.setText(QCoreApplication.translate("Properties", u"Trigger Mode:", None))
#if QT_CONFIG(whatsthis)
        self.label_triggerMode.setWhatsThis(QCoreApplication.translate("Properties", u"<html><head/><body><p><span style=\" text-decoration: underline;\">Autosequence</span></p><p>An exposure of a new image is started automatically best possible compared to the readout of an image and the current timing parameters. If a CCD is used and images are taken in a sequence, exposure and sensor readout are started simultaneously. Signals at the trigger input line are irrelevant.</p><p><span style=\" text-decoration: underline;\">External Exposure Start</span></p><p>A delay / exposure sequence is started depending on the HW signal at the trigger input line or by a force trigger command.</p><p><span style=\" text-decoration: underline;\">External Exposure Control</span></p><p>An exposure sequence is started depending on the HW signal at the trigger input line. The exposure time is defined by the pulse length of the HW signal. The delay and exposure time values defined by the set / request delay and exposure command are ineffective. In double image mode exposure time length of the first image is controlled"
                        " through the HW signal, exposure time of the second image is given by the readout time of the first image.</p><p>...</p></body></html>", None))
#endif // QT_CONFIG(whatsthis)
        self.label_triggerMode.setText(QCoreApplication.translate("Properties", u"None", None))
        self.label_8.setText(QCoreApplication.translate("Properties", u"Power Supply Temperature:", None))
        self.label_powerTemperature.setText(QCoreApplication.translate("Properties", u"None", None))
        self.label_9.setText(QCoreApplication.translate("Properties", u"Delay Time:", None))
#if QT_CONFIG(whatsthis)
        self.label_delayTime.setWhatsThis("")
#endif // QT_CONFIG(whatsthis)
        self.label_delayTime.setText(QCoreApplication.translate("Properties", u"None", None))
        self.label_11.setText(QCoreApplication.translate("Properties", u"Exposure Time:", None))
        self.label_exposureTime.setText(QCoreApplication.translate("Properties", u"None", None))
        self.label_10.setText(QCoreApplication.translate("Properties", u"Acquire Mode:", None))
#if QT_CONFIG(whatsthis)
        self.label_acquireMode.setWhatsThis(QCoreApplication.translate("Properties", u"<html><head/><body><p><span style=\" text-decoration: underline;\">Auto</span></p><p>All images will be acquired and stored.</p><p><span style=\" text-decoration: underline;\">External</span></p><p>The external control input is a static enable signal for image acquisition. Depending on the I/O configuration a high or low level at the external input does set the acquire enable state to TRUE. If the acquire enable state is TRUE exposure triggers are accepted and images are acquired. If the acquire enable state is FALSE, all exposure triggers are ignored and no images will be acquired and stored.</p><p><span style=\" text-decoration: underline;\">External modulate</span></p><p>The external control input is a dynamic frame start signal. Depending on the I/O configuration a rising or falling edge at the input will start a single frame in modulation mode.</p></body></html>", None))
#endif // QT_CONFIG(whatsthis)
        self.label_acquireMode.setText(QCoreApplication.translate("Properties", u"None", None))
        self.label_12.setText(QCoreApplication.translate("Properties", u"Storage Mode:", None))
#if QT_CONFIG(whatsthis)
        self.label_storageMode.setWhatsThis(QCoreApplication.translate("Properties", u"<html><head/><body><p><span style=\" text-decoration: underline;\">Recorder</span></p><p>Images are recorded and stored in the current selected segment of the camera internal memory (CamRAM).</p><p><span style=\" text-decoration: underline;\">FIFO buffer</span></p><p>Camera internal memory (CamRAM) is used as huge FIFO buffer to bypass short bottlenecks in data transmission. If buffer overflows, the oldest images are overwritten.</p></body></html>", None))
#endif // QT_CONFIG(whatsthis)
        self.label_storageMode.setText(QCoreApplication.translate("Properties", u"None", None))
        self.label_13.setText(QCoreApplication.translate("Properties", u"Recorder Mode:", None))
#if QT_CONFIG(tooltip)
        self.label_recorderMode.setToolTip(QCoreApplication.translate("Properties", u"Recorder Mode only valid if Storage Mode is Recorder", None))
#endif // QT_CONFIG(tooltip)
#if QT_CONFIG(whatsthis)
        self.label_recorderMode.setWhatsThis(QCoreApplication.translate("Properties", u"<html><head/><body><p><span style=\" text-decoration: underline;\">Sequence</span></p><p>Recording is stopped, when the last buffer in the segment is reached. No images are overwritten. Recording can be stopped by software.</p><p><span style=\" text-decoration: underline;\">Ring buffer</span></p><p>Camera records continuously into ring buffer. The oldest images are overwritten, if a buffer overflows occures due to long recording times. Recording must be stopped by software or with an stop event. The oldest image is overwritten, when the segment is full.</p></body></html>", None))
#endif // QT_CONFIG(whatsthis)
        self.label_recorderMode.setText(QCoreApplication.translate("Properties", u"None", None))
        self.label_14.setText(QCoreApplication.translate("Properties", u"Image Size:", None))
        self.label_imageSize.setText(QCoreApplication.translate("Properties", u"None", None))
        self.groupBox_3.setTitle(QCoreApplication.translate("Properties", u"Motor Properties", None))
        self.label_3.setText(QCoreApplication.translate("Properties", u"Horizontal Sample Motor Model:", None))
        self.label_horizontalMotorName.setText(QCoreApplication.translate("Properties", u"None", None))
        self.label_2.setText(QCoreApplication.translate("Properties", u"Vertical Sample Motor Model:", None))
        self.label_verticalMotorName.setText(QCoreApplication.translate("Properties", u"None", None))
        self.label_6.setText(QCoreApplication.translate("Properties", u"Horizontal Camera Motor Model:", None))
        self.label_cameraMotorName.setText(QCoreApplication.translate("Properties", u"None", None))
        self.pushButton_refresh.setText(QCoreApplication.translate("Properties", u"Refresh Properties", None))
    # retranslateUi


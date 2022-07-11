# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file '.\properties.ui'
#
# Created by: PyQt5 UI code generator 5.15.6
#
# WARNING: Any manual changes made to this file will be lost when pyuic5 is
# run again.  Do not edit this file unless you know what you are doing.


from PyQt5 import QtCore, QtGui, QtWidgets


class Ui_Properties(object):
    def setupUi(self, Properties):
        Properties.setObjectName("Properties")
        Properties.resize(223, 403)
        self.verticalLayout = QtWidgets.QVBoxLayout(Properties)
        self.verticalLayout.setObjectName("verticalLayout")
        self.groupBox_2 = QtWidgets.QGroupBox(Properties)
        self.groupBox_2.setObjectName("groupBox_2")
        self.formLayout = QtWidgets.QFormLayout(self.groupBox_2)
        self.formLayout.setObjectName("formLayout")
        self.label = QtWidgets.QLabel(self.groupBox_2)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.label.sizePolicy().hasHeightForWidth())
        self.label.setSizePolicy(sizePolicy)
        self.label.setObjectName("label")
        self.formLayout.setWidget(1, QtWidgets.QFormLayout.LabelRole, self.label)
        self.label_cameraName = QtWidgets.QLabel(self.groupBox_2)
        self.label_cameraName.setObjectName("label_cameraName")
        self.formLayout.setWidget(1, QtWidgets.QFormLayout.FieldRole, self.label_cameraName)
        self.label_4 = QtWidgets.QLabel(self.groupBox_2)
        self.label_4.setObjectName("label_4")
        self.formLayout.setWidget(4, QtWidgets.QFormLayout.LabelRole, self.label_4)
        self.label_cameraTemperature = QtWidgets.QLabel(self.groupBox_2)
        self.label_cameraTemperature.setObjectName("label_cameraTemperature")
        self.formLayout.setWidget(4, QtWidgets.QFormLayout.FieldRole, self.label_cameraTemperature)
        self.label_5 = QtWidgets.QLabel(self.groupBox_2)
        self.label_5.setObjectName("label_5")
        self.formLayout.setWidget(5, QtWidgets.QFormLayout.LabelRole, self.label_5)
        self.label_sensorTemperature = QtWidgets.QLabel(self.groupBox_2)
        self.label_sensorTemperature.setObjectName("label_sensorTemperature")
        self.formLayout.setWidget(5, QtWidgets.QFormLayout.FieldRole, self.label_sensorTemperature)
        self.label_7 = QtWidgets.QLabel(self.groupBox_2)
        self.label_7.setObjectName("label_7")
        self.formLayout.setWidget(8, QtWidgets.QFormLayout.LabelRole, self.label_7)
        self.label_triggerMode = QtWidgets.QLabel(self.groupBox_2)
        self.label_triggerMode.setObjectName("label_triggerMode")
        self.formLayout.setWidget(8, QtWidgets.QFormLayout.FieldRole, self.label_triggerMode)
        spacerItem = QtWidgets.QSpacerItem(20, 40, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding)
        self.formLayout.setItem(3, QtWidgets.QFormLayout.LabelRole, spacerItem)
        spacerItem1 = QtWidgets.QSpacerItem(20, 40, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding)
        self.formLayout.setItem(7, QtWidgets.QFormLayout.LabelRole, spacerItem1)
        self.label_8 = QtWidgets.QLabel(self.groupBox_2)
        self.label_8.setObjectName("label_8")
        self.formLayout.setWidget(6, QtWidgets.QFormLayout.LabelRole, self.label_8)
        self.label_powerTemperature = QtWidgets.QLabel(self.groupBox_2)
        self.label_powerTemperature.setObjectName("label_powerTemperature")
        self.formLayout.setWidget(6, QtWidgets.QFormLayout.FieldRole, self.label_powerTemperature)
        self.label_9 = QtWidgets.QLabel(self.groupBox_2)
        self.label_9.setObjectName("label_9")
        self.formLayout.setWidget(9, QtWidgets.QFormLayout.LabelRole, self.label_9)
        self.label_delayTime = QtWidgets.QLabel(self.groupBox_2)
        self.label_delayTime.setWhatsThis("")
        self.label_delayTime.setObjectName("label_delayTime")
        self.formLayout.setWidget(9, QtWidgets.QFormLayout.FieldRole, self.label_delayTime)
        self.label_11 = QtWidgets.QLabel(self.groupBox_2)
        self.label_11.setObjectName("label_11")
        self.formLayout.setWidget(10, QtWidgets.QFormLayout.LabelRole, self.label_11)
        self.label_exposureTime = QtWidgets.QLabel(self.groupBox_2)
        self.label_exposureTime.setObjectName("label_exposureTime")
        self.formLayout.setWidget(10, QtWidgets.QFormLayout.FieldRole, self.label_exposureTime)
        spacerItem2 = QtWidgets.QSpacerItem(20, 40, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding)
        self.formLayout.setItem(11, QtWidgets.QFormLayout.LabelRole, spacerItem2)
        self.label_10 = QtWidgets.QLabel(self.groupBox_2)
        self.label_10.setObjectName("label_10")
        self.formLayout.setWidget(12, QtWidgets.QFormLayout.LabelRole, self.label_10)
        self.label_acquireMode = QtWidgets.QLabel(self.groupBox_2)
        self.label_acquireMode.setObjectName("label_acquireMode")
        self.formLayout.setWidget(12, QtWidgets.QFormLayout.FieldRole, self.label_acquireMode)
        self.label_12 = QtWidgets.QLabel(self.groupBox_2)
        self.label_12.setObjectName("label_12")
        self.formLayout.setWidget(13, QtWidgets.QFormLayout.LabelRole, self.label_12)
        self.label_storageMode = QtWidgets.QLabel(self.groupBox_2)
        self.label_storageMode.setObjectName("label_storageMode")
        self.formLayout.setWidget(13, QtWidgets.QFormLayout.FieldRole, self.label_storageMode)
        self.label_13 = QtWidgets.QLabel(self.groupBox_2)
        self.label_13.setObjectName("label_13")
        self.formLayout.setWidget(14, QtWidgets.QFormLayout.LabelRole, self.label_13)
        self.label_recorderMode = QtWidgets.QLabel(self.groupBox_2)
        self.label_recorderMode.setObjectName("label_recorderMode")
        self.formLayout.setWidget(14, QtWidgets.QFormLayout.FieldRole, self.label_recorderMode)
        self.label_14 = QtWidgets.QLabel(self.groupBox_2)
        self.label_14.setObjectName("label_14")
        self.formLayout.setWidget(2, QtWidgets.QFormLayout.LabelRole, self.label_14)
        self.label_imageSize = QtWidgets.QLabel(self.groupBox_2)
        self.label_imageSize.setObjectName("label_imageSize")
        self.formLayout.setWidget(2, QtWidgets.QFormLayout.FieldRole, self.label_imageSize)
        self.verticalLayout.addWidget(self.groupBox_2)
        self.groupBox_3 = QtWidgets.QGroupBox(Properties)
        self.groupBox_3.setObjectName("groupBox_3")
        self.formLayout_2 = QtWidgets.QFormLayout(self.groupBox_3)
        self.formLayout_2.setObjectName("formLayout_2")
        self.label_3 = QtWidgets.QLabel(self.groupBox_3)
        self.label_3.setObjectName("label_3")
        self.formLayout_2.setWidget(1, QtWidgets.QFormLayout.LabelRole, self.label_3)
        self.label_horizontalMotorName = QtWidgets.QLabel(self.groupBox_3)
        self.label_horizontalMotorName.setObjectName("label_horizontalMotorName")
        self.formLayout_2.setWidget(1, QtWidgets.QFormLayout.FieldRole, self.label_horizontalMotorName)
        self.label_2 = QtWidgets.QLabel(self.groupBox_3)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.label_2.sizePolicy().hasHeightForWidth())
        self.label_2.setSizePolicy(sizePolicy)
        self.label_2.setObjectName("label_2")
        self.formLayout_2.setWidget(2, QtWidgets.QFormLayout.LabelRole, self.label_2)
        self.label_verticalMotorName = QtWidgets.QLabel(self.groupBox_3)
        self.label_verticalMotorName.setObjectName("label_verticalMotorName")
        self.formLayout_2.setWidget(2, QtWidgets.QFormLayout.FieldRole, self.label_verticalMotorName)
        self.label_6 = QtWidgets.QLabel(self.groupBox_3)
        self.label_6.setObjectName("label_6")
        self.formLayout_2.setWidget(3, QtWidgets.QFormLayout.LabelRole, self.label_6)
        self.label_cameraMotorName = QtWidgets.QLabel(self.groupBox_3)
        self.label_cameraMotorName.setObjectName("label_cameraMotorName")
        self.formLayout_2.setWidget(3, QtWidgets.QFormLayout.FieldRole, self.label_cameraMotorName)
        self.verticalLayout.addWidget(self.groupBox_3)
        self.pushButton_refresh = QtWidgets.QPushButton(Properties)
        self.pushButton_refresh.setObjectName("pushButton_refresh")
        self.verticalLayout.addWidget(self.pushButton_refresh)

        self.retranslateUi(Properties)
        QtCore.QMetaObject.connectSlotsByName(Properties)

    def retranslateUi(self, Properties):
        _translate = QtCore.QCoreApplication.translate
        Properties.setWindowTitle(_translate("Properties", "System Properties"))
        self.groupBox_2.setTitle(_translate("Properties", "Camera Properties"))
        self.label.setText(_translate("Properties", "Camera Model:"))
        self.label_cameraName.setText(_translate("Properties", "None"))
        self.label_4.setText(_translate("Properties", "Internal Temperature:"))
        self.label_cameraTemperature.setText(_translate("Properties", "None"))
        self.label_5.setText(_translate("Properties", "Image Sensor Temperature:"))
        self.label_sensorTemperature.setText(_translate("Properties", "None"))
        self.label_7.setText(_translate("Properties", "Trigger Mode:"))
        self.label_triggerMode.setWhatsThis(_translate("Properties", "<html><head/><body><p><span style=\" text-decoration: underline;\">Autosequence</span></p><p>An exposure of a new image is started automatically best possible compared to the readout of an image and the current timing parameters. If a CCD is used and images are taken in a sequence, exposure and sensor readout are started simultaneously. Signals at the trigger input line are irrelevant.</p><p><span style=\" text-decoration: underline;\">External Exposure Start</span></p><p>A delay / exposure sequence is started depending on the HW signal at the trigger input line or by a force trigger command.</p><p><span style=\" text-decoration: underline;\">External Exposure Control</span></p><p>An exposure sequence is started depending on the HW signal at the trigger input line. The exposure time is defined by the pulse length of the HW signal. The delay and exposure time values defined by the set / request delay and exposure command are ineffective. In double image mode exposure time length of the first image is controlled through the HW signal, exposure time of the second image is given by the readout time of the first image.</p><p>...</p></body></html>"))
        self.label_triggerMode.setText(_translate("Properties", "None"))
        self.label_8.setText(_translate("Properties", "Power Supply Temperature:"))
        self.label_powerTemperature.setText(_translate("Properties", "None"))
        self.label_9.setText(_translate("Properties", "Delay Time:"))
        self.label_delayTime.setText(_translate("Properties", "None"))
        self.label_11.setText(_translate("Properties", "Exposure Time:"))
        self.label_exposureTime.setText(_translate("Properties", "None"))
        self.label_10.setText(_translate("Properties", "Acquire Mode:"))
        self.label_acquireMode.setWhatsThis(_translate("Properties", "<html><head/><body><p><span style=\" text-decoration: underline;\">Auto</span></p><p>All images will be acquired and stored.</p><p><span style=\" text-decoration: underline;\">External</span></p><p>The external control input is a static enable signal for image acquisition. Depending on the I/O configuration a high or low level at the external input does set the acquire enable state to TRUE. If the acquire enable state is TRUE exposure triggers are accepted and images are acquired. If the acquire enable state is FALSE, all exposure triggers are ignored and no images will be acquired and stored.</p><p><span style=\" text-decoration: underline;\">External modulate</span></p><p>The external control input is a dynamic frame start signal. Depending on the I/O configuration a rising or falling edge at the input will start a single frame in modulation mode.</p></body></html>"))
        self.label_acquireMode.setText(_translate("Properties", "None"))
        self.label_12.setText(_translate("Properties", "Storage Mode:"))
        self.label_storageMode.setWhatsThis(_translate("Properties", "<html><head/><body><p><span style=\" text-decoration: underline;\">Recorder</span></p><p>Images are recorded and stored in the current selected segment of the camera internal memory (CamRAM).</p><p><span style=\" text-decoration: underline;\">FIFO buffer</span></p><p>Camera internal memory (CamRAM) is used as huge FIFO buffer to bypass short bottlenecks in data transmission. If buffer overflows, the oldest images are overwritten.</p></body></html>"))
        self.label_storageMode.setText(_translate("Properties", "None"))
        self.label_13.setText(_translate("Properties", "Recorder Mode:"))
        self.label_recorderMode.setToolTip(_translate("Properties", "Recorder Mode only valid if Storage Mode is Recorder"))
        self.label_recorderMode.setWhatsThis(_translate("Properties", "<html><head/><body><p><span style=\" text-decoration: underline;\">Sequence</span></p><p>Recording is stopped, when the last buffer in the segment is reached. No images are overwritten. Recording can be stopped by software.</p><p><span style=\" text-decoration: underline;\">Ring buffer</span></p><p>Camera records continuously into ring buffer. The oldest images are overwritten, if a buffer overflows occures due to long recording times. Recording must be stopped by software or with an stop event. The oldest image is overwritten, when the segment is full.</p></body></html>"))
        self.label_recorderMode.setText(_translate("Properties", "None"))
        self.label_14.setText(_translate("Properties", "Image Size:"))
        self.label_imageSize.setText(_translate("Properties", "None"))
        self.groupBox_3.setTitle(_translate("Properties", "Motor Properties"))
        self.label_3.setText(_translate("Properties", "Horizontal Sample Motor Model:"))
        self.label_horizontalMotorName.setText(_translate("Properties", "None"))
        self.label_2.setText(_translate("Properties", "Vertical Sample Motor Model:"))
        self.label_verticalMotorName.setText(_translate("Properties", "None"))
        self.label_6.setText(_translate("Properties", "Horizontal Camera Motor Model:"))
        self.label_cameraMotorName.setText(_translate("Properties", "None"))
        self.pushButton_refresh.setText(_translate("Properties", "Refresh Properties"))
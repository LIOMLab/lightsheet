# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'ui_save_panel.ui'
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
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QFrame, QGridLayout,
    QGroupBox, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QPushButton,
    QRadioButton, QSizePolicy, QSpacerItem, QSplitter,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

class Ui_SavePanel(object):
    def setupUi(self, savePanel):
        if not savePanel.objectName():
            savePanel.setObjectName(u"savePanel")
        self.verticalLayout_panel = QVBoxLayout(savePanel)
        self.verticalLayout_panel.setObjectName(u"verticalLayout_panel")
        self.groupBox_5 = QGroupBox(savePanel)
        self.groupBox_5.setObjectName(u"groupBox_5")
        self.horizontalLayout_8 = QHBoxLayout(self.groupBox_5)
        self.horizontalLayout_8.setObjectName(u"horizontalLayout_8")
        self.verticalLayout_8 = QVBoxLayout()
        self.verticalLayout_8.setObjectName(u"verticalLayout_8")
        self.horizontalLayout_92 = QHBoxLayout()
        self.horizontalLayout_92.setObjectName(u"horizontalLayout_92")
        self.pushButton_saveSelectDirectory = QPushButton(self.groupBox_5)
        self.pushButton_saveSelectDirectory.setObjectName(u"pushButton_saveSelectDirectory")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.pushButton_saveSelectDirectory.sizePolicy().hasHeightForWidth())
        self.pushButton_saveSelectDirectory.setSizePolicy(sizePolicy)

        self.horizontalLayout_92.addWidget(self.pushButton_saveSelectDirectory)

        self.horizontalSpacer_2 = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayout_92.addItem(self.horizontalSpacer_2)

        self.pushButton_saveCurrentImage = QPushButton(self.groupBox_5)
        self.pushButton_saveCurrentImage.setObjectName(u"pushButton_saveCurrentImage")
        sizePolicy1 = QSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.pushButton_saveCurrentImage.sizePolicy().hasHeightForWidth())
        self.pushButton_saveCurrentImage.setSizePolicy(sizePolicy1)

        self.horizontalLayout_92.addWidget(self.pushButton_saveCurrentImage)


        self.verticalLayout_8.addLayout(self.horizontalLayout_92)

        self.gridLayout_9 = QGridLayout()
        self.gridLayout_9.setObjectName(u"gridLayout_9")
        self.lineEdit_saveDescription = QLineEdit(self.groupBox_5)
        self.lineEdit_saveDescription.setObjectName(u"lineEdit_saveDescription")

        self.gridLayout_9.addWidget(self.lineEdit_saveDescription, 2, 1, 1, 1)

        self.lineEdit_saveFilename = QLineEdit(self.groupBox_5)
        self.lineEdit_saveFilename.setObjectName(u"lineEdit_saveFilename")

        self.gridLayout_9.addWidget(self.lineEdit_saveFilename, 1, 1, 1, 1)

        self.label_45 = QLabel(self.groupBox_5)
        self.label_45.setObjectName(u"label_45")

        self.gridLayout_9.addWidget(self.label_45, 1, 0, 1, 1)

        self.lineEdit_saveDirectory = QLineEdit(self.groupBox_5)
        self.lineEdit_saveDirectory.setObjectName(u"lineEdit_saveDirectory")
        self.lineEdit_saveDirectory.setEnabled(True)
        self.lineEdit_saveDirectory.setFrame(False)
        self.lineEdit_saveDirectory.setReadOnly(True)

        self.gridLayout_9.addWidget(self.lineEdit_saveDirectory, 0, 1, 1, 1)

        self.label_8 = QLabel(self.groupBox_5)
        self.label_8.setObjectName(u"label_8")

        self.gridLayout_9.addWidget(self.label_8, 0, 0, 1, 1)

        self.label_46 = QLabel(self.groupBox_5)
        self.label_46.setObjectName(u"label_46")

        self.gridLayout_9.addWidget(self.label_46, 2, 0, 1, 1)


        self.verticalLayout_8.addLayout(self.gridLayout_9)


        self.horizontalLayout_8.addLayout(self.verticalLayout_8)

        self.line_5 = QFrame(self.groupBox_5)
        self.line_5.setObjectName(u"line_5")
        self.line_5.setFrameShadow(QFrame.Raised)
        self.line_5.setFrameShape(QFrame.Shape.VLine)

        self.horizontalLayout_8.addWidget(self.line_5)

        self.verticalLayout_11 = QVBoxLayout()
        self.verticalLayout_11.setObjectName(u"verticalLayout_11")
        self.label_saveFormat = QLabel(self.groupBox_5)
        self.label_saveFormat.setObjectName(u"label_saveFormat")

        self.verticalLayout_11.addWidget(self.label_saveFormat)

        self.radioButton_saveFormat_hdf5 = QRadioButton(self.groupBox_5)
        self.radioButton_saveFormat_hdf5.setObjectName(u"radioButton_saveFormat_hdf5")
        sizePolicy2 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        sizePolicy2.setHorizontalStretch(0)
        sizePolicy2.setVerticalStretch(0)
        sizePolicy2.setHeightForWidth(self.radioButton_saveFormat_hdf5.sizePolicy().hasHeightForWidth())
        self.radioButton_saveFormat_hdf5.setSizePolicy(sizePolicy2)

        self.verticalLayout_11.addWidget(self.radioButton_saveFormat_hdf5)

        self.radioButton_saveFormat_zarr = QRadioButton(self.groupBox_5)
        self.radioButton_saveFormat_zarr.setObjectName(u"radioButton_saveFormat_zarr")
        sizePolicy2.setHeightForWidth(self.radioButton_saveFormat_zarr.sizePolicy().hasHeightForWidth())
        self.radioButton_saveFormat_zarr.setSizePolicy(sizePolicy2)

        self.verticalLayout_11.addWidget(self.radioButton_saveFormat_zarr)

        self.radioButton_saveFormat_both = QRadioButton(self.groupBox_5)
        self.radioButton_saveFormat_both.setObjectName(u"radioButton_saveFormat_both")
        sizePolicy2.setHeightForWidth(self.radioButton_saveFormat_both.sizePolicy().hasHeightForWidth())
        self.radioButton_saveFormat_both.setSizePolicy(sizePolicy2)

        self.verticalLayout_11.addWidget(self.radioButton_saveFormat_both)

        self.label_7 = QLabel(self.groupBox_5)
        self.label_7.setObjectName(u"label_7")

        self.verticalLayout_11.addWidget(self.label_7)

        self.radioButton_saveStitch = QRadioButton(self.groupBox_5)
        self.radioButton_saveStitch.setObjectName(u"radioButton_saveStitch")
        sizePolicy2.setHeightForWidth(self.radioButton_saveStitch.sizePolicy().hasHeightForWidth())
        self.radioButton_saveStitch.setSizePolicy(sizePolicy2)
        self.radioButton_saveStitch.setChecked(True)

        self.verticalLayout_11.addWidget(self.radioButton_saveStitch)

        self.radioButton_saveStitchBlend = QRadioButton(self.groupBox_5)
        self.radioButton_saveStitchBlend.setObjectName(u"radioButton_saveStitchBlend")
        sizePolicy2.setHeightForWidth(self.radioButton_saveStitchBlend.sizePolicy().hasHeightForWidth())
        self.radioButton_saveStitchBlend.setSizePolicy(sizePolicy2)

        self.verticalLayout_11.addWidget(self.radioButton_saveStitchBlend)

        self.radioButton_saveAllCrop = QRadioButton(self.groupBox_5)
        self.radioButton_saveAllCrop.setObjectName(u"radioButton_saveAllCrop")
        sizePolicy2.setHeightForWidth(self.radioButton_saveAllCrop.sizePolicy().hasHeightForWidth())
        self.radioButton_saveAllCrop.setSizePolicy(sizePolicy2)

        self.verticalLayout_11.addWidget(self.radioButton_saveAllCrop)

        self.radioButton_saveAllFull = QRadioButton(self.groupBox_5)
        self.radioButton_saveAllFull.setObjectName(u"radioButton_saveAllFull")
        sizePolicy2.setHeightForWidth(self.radioButton_saveAllFull.sizePolicy().hasHeightForWidth())
        self.radioButton_saveAllFull.setSizePolicy(sizePolicy2)

        self.verticalLayout_11.addWidget(self.radioButton_saveAllFull)


        self.horizontalLayout_8.addLayout(self.verticalLayout_11)

        self.horizontalLayout_8.setStretch(0, 1)

        self.verticalLayout_panel.addWidget(self.groupBox_5)

        self.groupBox_16 = QGroupBox(savePanel)
        self.groupBox_16.setObjectName(u"groupBox_16")
        self.verticalLayout_10 = QVBoxLayout(self.groupBox_16)
        self.verticalLayout_10.setObjectName(u"verticalLayout_10")
        self.horizontalLayout_74 = QHBoxLayout()
        self.horizontalLayout_74.setObjectName(u"horizontalLayout_74")
        self.pushButton_selectFile = QPushButton(self.groupBox_16)
        self.pushButton_selectFile.setObjectName(u"pushButton_selectFile")
        sizePolicy.setHeightForWidth(self.pushButton_selectFile.sizePolicy().hasHeightForWidth())
        self.pushButton_selectFile.setSizePolicy(sizePolicy)

        self.horizontalLayout_74.addWidget(self.pushButton_selectFile)

        self.label_37 = QLabel(self.groupBox_16)
        self.label_37.setObjectName(u"label_37")
        sizePolicy.setHeightForWidth(self.label_37.sizePolicy().hasHeightForWidth())
        self.label_37.setSizePolicy(sizePolicy)

        self.horizontalLayout_74.addWidget(self.label_37)

        self.label_currentFileDirectory = QLabel(self.groupBox_16)
        self.label_currentFileDirectory.setObjectName(u"label_currentFileDirectory")
        sizePolicy3 = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        sizePolicy3.setHorizontalStretch(0)
        sizePolicy3.setVerticalStretch(0)
        sizePolicy3.setHeightForWidth(self.label_currentFileDirectory.sizePolicy().hasHeightForWidth())
        self.label_currentFileDirectory.setSizePolicy(sizePolicy3)

        self.horizontalLayout_74.addWidget(self.label_currentFileDirectory)


        self.verticalLayout_10.addLayout(self.horizontalLayout_74)

        self.splitter_3 = QSplitter(self.groupBox_16)
        self.splitter_3.setObjectName(u"splitter_3")
        self.splitter_3.setOrientation(Qt.Horizontal)
        self.splitter_3.setChildrenCollapsible(False)
        self.layoutWidget = QWidget(self.splitter_3)
        self.layoutWidget.setObjectName(u"layoutWidget")
        self.verticalLayout_50 = QVBoxLayout(self.layoutWidget)
        self.verticalLayout_50.setObjectName(u"verticalLayout_50")
        self.verticalLayout_50.setContentsMargins(0, 0, 0, 0)
        self.label_38 = QLabel(self.layoutWidget)
        self.label_38.setObjectName(u"label_38")
        sizePolicy3.setHeightForWidth(self.label_38.sizePolicy().hasHeightForWidth())
        self.label_38.setSizePolicy(sizePolicy3)

        self.verticalLayout_50.addWidget(self.label_38)

        self.listWidget_fileDatasets = QListWidget(self.layoutWidget)
        self.listWidget_fileDatasets.setObjectName(u"listWidget_fileDatasets")
        sizePolicy4 = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        sizePolicy4.setHorizontalStretch(0)
        sizePolicy4.setVerticalStretch(0)
        sizePolicy4.setHeightForWidth(self.listWidget_fileDatasets.sizePolicy().hasHeightForWidth())
        self.listWidget_fileDatasets.setSizePolicy(sizePolicy4)
        self.listWidget_fileDatasets.setSelectionMode(QAbstractItemView.ExtendedSelection)

        self.verticalLayout_50.addWidget(self.listWidget_fileDatasets)

        self.pushButton_selectDataset = QPushButton(self.layoutWidget)
        self.pushButton_selectDataset.setObjectName(u"pushButton_selectDataset")
        sizePolicy3.setHeightForWidth(self.pushButton_selectDataset.sizePolicy().hasHeightForWidth())
        self.pushButton_selectDataset.setSizePolicy(sizePolicy3)

        self.verticalLayout_50.addWidget(self.pushButton_selectDataset)

        self.splitter_3.addWidget(self.layoutWidget)
        self.layoutWidget1 = QWidget(self.splitter_3)
        self.layoutWidget1.setObjectName(u"layoutWidget1")
        self.verticalLayout_51 = QVBoxLayout(self.layoutWidget1)
        self.verticalLayout_51.setObjectName(u"verticalLayout_51")
        self.verticalLayout_51.setContentsMargins(0, 0, 0, 0)
        self.horizontalLayout_76 = QHBoxLayout()
        self.horizontalLayout_76.setObjectName(u"horizontalLayout_76")
        self.label_39 = QLabel(self.layoutWidget1)
        self.label_39.setObjectName(u"label_39")

        self.horizontalLayout_76.addWidget(self.label_39)

        self.label_40 = QLabel(self.layoutWidget1)
        self.label_40.setObjectName(u"label_40")
        sizePolicy.setHeightForWidth(self.label_40.sizePolicy().hasHeightForWidth())
        self.label_40.setSizePolicy(sizePolicy)

        self.horizontalLayout_76.addWidget(self.label_40)

        self.label_currentDataset = QLabel(self.layoutWidget1)
        self.label_currentDataset.setObjectName(u"label_currentDataset")
        sizePolicy3.setHeightForWidth(self.label_currentDataset.sizePolicy().hasHeightForWidth())
        self.label_currentDataset.setSizePolicy(sizePolicy3)

        self.horizontalLayout_76.addWidget(self.label_currentDataset)


        self.verticalLayout_51.addLayout(self.horizontalLayout_76)

        self.tableWidget_fileAttributes = QTableWidget(self.layoutWidget1)
        self.tableWidget_fileAttributes.setObjectName(u"tableWidget_fileAttributes")
        sizePolicy4.setHeightForWidth(self.tableWidget_fileAttributes.sizePolicy().hasHeightForWidth())
        self.tableWidget_fileAttributes.setSizePolicy(sizePolicy4)

        self.verticalLayout_51.addWidget(self.tableWidget_fileAttributes)

        self.splitter_3.addWidget(self.layoutWidget1)

        self.verticalLayout_10.addWidget(self.splitter_3)


        self.verticalLayout_panel.addWidget(self.groupBox_16)


        self.retranslateUi(savePanel)

        QMetaObject.connectSlotsByName(savePanel)
    # setupUi

    def retranslateUi(self, savePanel):
        self.groupBox_5.setTitle(QCoreApplication.translate("SavePanel", u"Save Settings", None))
#if QT_CONFIG(tooltip)
        self.pushButton_saveSelectDirectory.setToolTip(QCoreApplication.translate("SavePanel", u"Select a file directory for image saving", None))
#endif // QT_CONFIG(tooltip)
        self.pushButton_saveSelectDirectory.setText(QCoreApplication.translate("SavePanel", u"Select Save Directory", None))
#if QT_CONFIG(tooltip)
        self.pushButton_saveCurrentImage.setToolTip(QCoreApplication.translate("SavePanel", u"Save the current displayed frame as a single image using the selected save option above. (Stack saves are started from the Stack panel and use the stack save path, not these options.)", None))
#endif // QT_CONFIG(tooltip)
        self.pushButton_saveCurrentImage.setText(QCoreApplication.translate("SavePanel", u"Save Current Image", None))
        self.lineEdit_saveDescription.setText("")
        self.lineEdit_saveFilename.setText("")
        self.label_45.setText(QCoreApplication.translate("SavePanel", u"Filename:", None))
        self.lineEdit_saveDirectory.setText("")
        self.label_8.setText(QCoreApplication.translate("SavePanel", u"Save Directory:", None))
        self.label_46.setText(QCoreApplication.translate("SavePanel", u"Description:", None))
        self.label_saveFormat.setText(QCoreApplication.translate("SavePanel", u"Save format:", None))
#if QT_CONFIG(tooltip)
        self.radioButton_saveFormat_hdf5.setToolTip(QCoreApplication.translate("SavePanel", u"Write the existing per-plane HDF5 stack (byte-identical to today's save path).", None))
#endif // QT_CONFIG(tooltip)
        self.radioButton_saveFormat_hdf5.setText(QCoreApplication.translate("SavePanel", u"HDF5", None))
#if QT_CONFIG(tooltip)
        self.radioButton_saveFormat_zarr.setToolTip(QCoreApplication.translate("SavePanel", u"Write a streaming OME-Zarr whole-stack volume with multiscale pyramids (10/25/50/100 \u00b5m) and OME-NGFF channel metadata \u2014 BigStitcher/napari-readable.", None))
#endif // QT_CONFIG(tooltip)
        self.radioButton_saveFormat_zarr.setText(QCoreApplication.translate("SavePanel", u"OME-Zarr", None))
#if QT_CONFIG(tooltip)
        self.radioButton_saveFormat_both.setToolTip(QCoreApplication.translate("SavePanel", u"Write both HDF5 and OME-Zarr \u2014 doubles disk write rate. Use only when disk space and write throughput are not the bottleneck (e.g. short validation stacks). For whole-brain stacks, prefer HDF5 or OME-Zarr alone.", None))
#endif // QT_CONFIG(tooltip)
        self.radioButton_saveFormat_both.setText(QCoreApplication.translate("SavePanel", u"Both", None))
        self.label_7.setText(QCoreApplication.translate("SavePanel", u"Save option (select one):", None))
#if QT_CONFIG(tooltip)
        self.radioButton_saveStitch.setToolTip(QCoreApplication.translate("SavePanel", u"Stitch saved frames into a single tiled image. Effect: enable to produce a stitched overview; disable to save individual frames only.", None))
#endif // QT_CONFIG(tooltip)
        self.radioButton_saveStitch.setText(QCoreApplication.translate("SavePanel", u"Stitched - No blend", None))
#if QT_CONFIG(tooltip)
        self.radioButton_saveStitchBlend.setToolTip(QCoreApplication.translate("SavePanel", u"Blend overlapping regions when stitching. Effect: enable for seamless stitching; disable for hard-edge tiling.", None))
#endif // QT_CONFIG(tooltip)
        self.radioButton_saveStitchBlend.setText(QCoreApplication.translate("SavePanel", u"Stitched - Linear blend (20%)", None))
#if QT_CONFIG(tooltip)
        self.radioButton_saveAllCrop.setToolTip(QCoreApplication.translate("SavePanel", u"Save all cropped frames. Effect: enable to save the cropped region of every frame to the dataset.", None))
#endif // QT_CONFIG(tooltip)
        self.radioButton_saveAllCrop.setText(QCoreApplication.translate("SavePanel", u"All frames - Cropped (20%)", None))
#if QT_CONFIG(tooltip)
        self.radioButton_saveAllFull.setToolTip(QCoreApplication.translate("SavePanel", u"Save all full frames. Effect: enable to save the full-frame data of every frame to the dataset.", None))
#endif // QT_CONFIG(tooltip)
        self.radioButton_saveAllFull.setText(QCoreApplication.translate("SavePanel", u"All frames - Full", None))
        self.groupBox_16.setTitle(QCoreApplication.translate("SavePanel", u"Open File", None))
#if QT_CONFIG(tooltip)
        self.pushButton_selectFile.setToolTip(QCoreApplication.translate("SavePanel", u"Select a HDF5 file to open", None))
#endif // QT_CONFIG(tooltip)
        self.pushButton_selectFile.setText(QCoreApplication.translate("SavePanel", u"Select File", None))
        self.label_37.setText(QCoreApplication.translate("SavePanel", u"Current File:", None))
        self.label_currentFileDirectory.setText(QCoreApplication.translate("SavePanel", u"None Specified", None))
        self.label_38.setText(QCoreApplication.translate("SavePanel", u"File Datasets:", None))
#if QT_CONFIG(tooltip)
        self.pushButton_selectDataset.setToolTip(QCoreApplication.translate("SavePanel", u"Select and show the dataset(s) of the opened file", None))
#endif // QT_CONFIG(tooltip)
        self.pushButton_selectDataset.setText(QCoreApplication.translate("SavePanel", u"Select and Show Dataset(s)", None))
        self.label_39.setText(QCoreApplication.translate("SavePanel", u"Dataset Attributes:", None))
        self.label_40.setText(QCoreApplication.translate("SavePanel", u"Current Dataset:", None))
        self.label_currentDataset.setText(QCoreApplication.translate("SavePanel", u"None Specified", None))
        pass
    # retranslateUi


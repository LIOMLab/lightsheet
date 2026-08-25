# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'ui_controller.ui'
##
## Created by: Qt User Interface Compiler version 6.11.2
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (QCoreApplication, QDate, QDateTime, QLocale,
    QMetaObject, QObject, QPoint, QRect,
    QSize, QTime, QUrl, Qt)
from PySide6.QtGui import (QAction, QBrush, QColor, QConicalGradient,
    QCursor, QFont, QFontDatabase, QGradient,
    QIcon, QImage, QKeySequence, QLinearGradient,
    QPainter, QPalette, QPixmap, QRadialGradient,
    QTransform)
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox,
    QDoubleSpinBox, QFormLayout, QFrame, QGridLayout,
    QGroupBox, QHBoxLayout, QHeaderView, QLabel,
    QLayout, QLineEdit, QListWidget, QListWidgetItem,
    QMainWindow, QMenu, QMenuBar, QPlainTextEdit,
    QPushButton, QSizePolicy, QSpacerItem, QSplitter,
    QStatusBar, QTabWidget, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget)

from lightsheet.gui.image_view import ImageView
from . import ui_controller_rc

class Ui_Controller(object):
    def setupUi(self, Controller):
        if not Controller.objectName():
            Controller.setObjectName(u"Controller")
        Controller.resize(1479, 899)
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(Controller.sizePolicy().hasHeightForWidth())
        Controller.setSizePolicy(sizePolicy)
        icon = QIcon()
        icon.addFile(u":/images/resources/liom_logo.png", QSize(), QIcon.Mode.Normal, QIcon.State.Off)
        Controller.setWindowIcon(icon)
        Controller.setStyleSheet(u"")
        self.action_openDocumentation = QAction(Controller)
        self.action_openDocumentation.setObjectName(u"action_openDocumentation")
        self.action_ShowHideMessageLog = QAction(Controller)
        self.action_ShowHideMessageLog.setObjectName(u"action_ShowHideMessageLog")
        self.action_ShowHideMessageLog.setCheckable(True)
        self.action_ShowHideMessageLog.setChecked(True)
        self.action_showSystemProperties = QAction(Controller)
        self.action_showSystemProperties.setObjectName(u"action_showSystemProperties")
        self.action_lightTheme = QAction(Controller)
        self.action_lightTheme.setObjectName(u"action_lightTheme")
        self.action_darkTheme = QAction(Controller)
        self.action_darkTheme.setObjectName(u"action_darkTheme")
        self.action_ShowHideImagesPane = QAction(Controller)
        self.action_ShowHideImagesPane.setObjectName(u"action_ShowHideImagesPane")
        self.action_ShowHideImagesPane.setCheckable(True)
        self.action_ShowHideImagesPane.setChecked(True)
        self.action_ShowHideControlsPane = QAction(Controller)
        self.action_ShowHideControlsPane.setObjectName(u"action_ShowHideControlsPane")
        self.action_ShowHideControlsPane.setCheckable(True)
        self.action_ShowHideControlsPane.setChecked(True)
        self.action_OpenFile = QAction(Controller)
        self.action_OpenFile.setObjectName(u"action_OpenFile")
        self.action_Exit = QAction(Controller)
        self.action_Exit.setObjectName(u"action_Exit")
        self.centralwidget = QWidget(Controller)
        self.centralwidget.setObjectName(u"centralwidget")
        sizePolicy.setHeightForWidth(self.centralwidget.sizePolicy().hasHeightForWidth())
        self.centralwidget.setSizePolicy(sizePolicy)
        self.horizontalLayout_3 = QHBoxLayout(self.centralwidget)
        self.horizontalLayout_3.setObjectName(u"horizontalLayout_3")
        self.splitter = QSplitter(self.centralwidget)
        self.splitter.setObjectName(u"splitter")
        sizePolicy1 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.splitter.sizePolicy().hasHeightForWidth())
        self.splitter.setSizePolicy(sizePolicy1)
        self.splitter.setOrientation(Qt.Horizontal)
        self.splitter.setHandleWidth(5)
        self.splitter.setChildrenCollapsible(False)
        self.imagesPane = QWidget(self.splitter)
        self.imagesPane.setObjectName(u"imagesPane")
        sizePolicy1.setHeightForWidth(self.imagesPane.sizePolicy().hasHeightForWidth())
        self.imagesPane.setSizePolicy(sizePolicy1)
        self.imagesPane.setMinimumSize(QSize(706, 700))
        self.verticalLayout = QVBoxLayout(self.imagesPane)
        self.verticalLayout.setSpacing(6)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.verticalLayout.setContentsMargins(0, 0, 6, 0)
        self.imageView = ImageView(self.imagesPane)
        self.imageView.setObjectName(u"imageView")
        sizePolicy.setHeightForWidth(self.imageView.sizePolicy().hasHeightForWidth())
        self.imageView.setSizePolicy(sizePolicy)
        self.imageView.setMinimumSize(QSize(700, 700))
        self.imageView.setBaseSize(QSize(700, 0))

        self.verticalLayout.addWidget(self.imageView)

        self.splitter.addWidget(self.imagesPane)
        self.controlsPane = QWidget(self.splitter)
        self.controlsPane.setObjectName(u"controlsPane")
        self.verticalLayout_3 = QVBoxLayout(self.controlsPane)
        self.verticalLayout_3.setObjectName(u"verticalLayout_3")
        self.verticalLayout_3.setContentsMargins(-1, 0, -1, 0)
        self.tabControls = QTabWidget(self.controlsPane)
        self.tabControls.setObjectName(u"tabControls")
        sizePolicy1.setHeightForWidth(self.tabControls.sizePolicy().hasHeightForWidth())
        self.tabControls.setSizePolicy(sizePolicy1)
        self.tabControls.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
        self.tabControls.setTabPosition(QTabWidget.North)
        self.tabControls.setTabShape(QTabWidget.Rounded)
        self.tabMotion = QWidget()
        self.tabMotion.setObjectName(u"tabMotion")
        self.verticalLayout_2 = QVBoxLayout(self.tabMotion)
        self.verticalLayout_2.setObjectName(u"verticalLayout_2")
        self.horizontalLayout_1 = QHBoxLayout()
        self.horizontalLayout_1.setObjectName(u"horizontalLayout_1")
        self.horizontalSpacer_1 = QSpacerItem(40, 10, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayout_1.addItem(self.horizontalSpacer_1)

        self.label_1 = QLabel(self.tabMotion)
        self.label_1.setObjectName(u"label_1")
        sizePolicy2 = QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        sizePolicy2.setHorizontalStretch(0)
        sizePolicy2.setVerticalStretch(0)
        sizePolicy2.setHeightForWidth(self.label_1.sizePolicy().hasHeightForWidth())
        self.label_1.setSizePolicy(sizePolicy2)

        self.horizontalLayout_1.addWidget(self.label_1)

        self.comboBox_units = QComboBox(self.tabMotion)
        self.comboBox_units.setObjectName(u"comboBox_units")
        sizePolicy3 = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        sizePolicy3.setHorizontalStretch(0)
        sizePolicy3.setVerticalStretch(0)
        sizePolicy3.setHeightForWidth(self.comboBox_units.sizePolicy().hasHeightForWidth())
        self.comboBox_units.setSizePolicy(sizePolicy3)
        self.comboBox_units.setMinimumSize(QSize(75, 0))

        self.horizontalLayout_1.addWidget(self.comboBox_units)


        self.verticalLayout_2.addLayout(self.horizontalLayout_1)

        self.horizontalLayout_2 = QHBoxLayout()
        self.horizontalLayout_2.setObjectName(u"horizontalLayout_2")
        self.groupBox_SampleMovement = QGroupBox(self.tabMotion)
        self.groupBox_SampleMovement.setObjectName(u"groupBox_SampleMovement")
        sizePolicy2.setHeightForWidth(self.groupBox_SampleMovement.sizePolicy().hasHeightForWidth())
        self.groupBox_SampleMovement.setSizePolicy(sizePolicy2)
        self.groupBox_SampleMovement.setMinimumSize(QSize(350, 380))
        self.groupBox_SampleMovement.setMaximumSize(QSize(350, 380))
        self.gridLayout_7 = QGridLayout(self.groupBox_SampleMovement)
        self.gridLayout_7.setObjectName(u"gridLayout_7")
        self.verticalLayout_32 = QVBoxLayout()
        self.verticalLayout_32.setObjectName(u"verticalLayout_32")
        self.horizontalLayout_6 = QHBoxLayout()
        self.horizontalLayout_6.setObjectName(u"horizontalLayout_6")
        self.gridLayout_5 = QGridLayout()
        self.gridLayout_5.setObjectName(u"gridLayout_5")
        self.label_sampleCurrentHPosition = QLabel(self.groupBox_SampleMovement)
        self.label_sampleCurrentHPosition.setObjectName(u"label_sampleCurrentHPosition")
        self.label_sampleCurrentHPosition.setMinimumSize(QSize(50, 0))

        self.gridLayout_5.addWidget(self.label_sampleCurrentHPosition, 0, 1, 1, 1)

        self.label_21 = QLabel(self.groupBox_SampleMovement)
        self.label_21.setObjectName(u"label_21")
        sizePolicy4 = QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        sizePolicy4.setHorizontalStretch(0)
        sizePolicy4.setVerticalStretch(0)
        sizePolicy4.setHeightForWidth(self.label_21.sizePolicy().hasHeightForWidth())
        self.label_21.setSizePolicy(sizePolicy4)
        self.label_21.setMinimumSize(QSize(135, 0))

        self.gridLayout_5.addWidget(self.label_21, 0, 0, 1, 1)

        self.label_22 = QLabel(self.groupBox_SampleMovement)
        self.label_22.setObjectName(u"label_22")
        sizePolicy4.setHeightForWidth(self.label_22.sizePolicy().hasHeightForWidth())
        self.label_22.setSizePolicy(sizePolicy4)
        self.label_22.setMinimumSize(QSize(135, 0))
        self.label_22.setAlignment(Qt.AlignLeading|Qt.AlignLeft|Qt.AlignVCenter)

        self.gridLayout_5.addWidget(self.label_22, 1, 0, 1, 1)

        self.label_sampleCurrentVPosition = QLabel(self.groupBox_SampleMovement)
        self.label_sampleCurrentVPosition.setObjectName(u"label_sampleCurrentVPosition")
        self.label_sampleCurrentVPosition.setMinimumSize(QSize(50, 0))

        self.gridLayout_5.addWidget(self.label_sampleCurrentVPosition, 1, 1, 1, 1)


        self.horizontalLayout_6.addLayout(self.gridLayout_5)

        self.pushButton_sampleSetOrigin = QPushButton(self.groupBox_SampleMovement)
        self.pushButton_sampleSetOrigin.setObjectName(u"pushButton_sampleSetOrigin")
        self.pushButton_sampleSetOrigin.setEnabled(True)
        sizePolicy2.setHeightForWidth(self.pushButton_sampleSetOrigin.sizePolicy().hasHeightForWidth())
        self.pushButton_sampleSetOrigin.setSizePolicy(sizePolicy2)
        self.pushButton_sampleSetOrigin.setMinimumSize(QSize(75, 0))

        self.horizontalLayout_6.addWidget(self.pushButton_sampleSetOrigin)


        self.verticalLayout_32.addLayout(self.horizontalLayout_6)

        self.line = QFrame(self.groupBox_SampleMovement)
        self.line.setObjectName(u"line")
        self.line.setFrameShape(QFrame.Shape.HLine)
        self.line.setFrameShadow(QFrame.Shadow.Sunken)

        self.verticalLayout_32.addWidget(self.line)

        self.gridLayout_3 = QGridLayout()
        self.gridLayout_3.setObjectName(u"gridLayout_3")
        self.pushButton_sampleStepForward = QPushButton(self.groupBox_SampleMovement)
        self.pushButton_sampleStepForward.setObjectName(u"pushButton_sampleStepForward")
        sizePolicy2.setHeightForWidth(self.pushButton_sampleStepForward.sizePolicy().hasHeightForWidth())
        self.pushButton_sampleStepForward.setSizePolicy(sizePolicy2)
        self.pushButton_sampleStepForward.setMinimumSize(QSize(60, 60))
        self.pushButton_sampleStepForward.setMaximumSize(QSize(60, 16777215))

        self.gridLayout_3.addWidget(self.pushButton_sampleStepForward, 1, 3, 1, 1)

        self.pushButton_sampleGotoOrigin = QPushButton(self.groupBox_SampleMovement)
        self.pushButton_sampleGotoOrigin.setObjectName(u"pushButton_sampleGotoOrigin")
        sizePolicy2.setHeightForWidth(self.pushButton_sampleGotoOrigin.sizePolicy().hasHeightForWidth())
        self.pushButton_sampleGotoOrigin.setSizePolicy(sizePolicy2)
        self.pushButton_sampleGotoOrigin.setMinimumSize(QSize(60, 60))
        self.pushButton_sampleGotoOrigin.setMaximumSize(QSize(60, 16777215))

        self.gridLayout_3.addWidget(self.pushButton_sampleGotoOrigin, 1, 2, 1, 1)

        self.horizontalSpacer = QSpacerItem(60, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.gridLayout_3.addItem(self.horizontalSpacer, 1, 4, 1, 1)

        self.pushButton_sampleStepUp = QPushButton(self.groupBox_SampleMovement)
        self.pushButton_sampleStepUp.setObjectName(u"pushButton_sampleStepUp")
        sizePolicy2.setHeightForWidth(self.pushButton_sampleStepUp.sizePolicy().hasHeightForWidth())
        self.pushButton_sampleStepUp.setSizePolicy(sizePolicy2)
        self.pushButton_sampleStepUp.setMinimumSize(QSize(60, 60))
        self.pushButton_sampleStepUp.setMaximumSize(QSize(60, 16777215))

        self.gridLayout_3.addWidget(self.pushButton_sampleStepUp, 0, 2, 1, 1)

        self.pushButton_sampleStepBackward = QPushButton(self.groupBox_SampleMovement)
        self.pushButton_sampleStepBackward.setObjectName(u"pushButton_sampleStepBackward")
        sizePolicy2.setHeightForWidth(self.pushButton_sampleStepBackward.sizePolicy().hasHeightForWidth())
        self.pushButton_sampleStepBackward.setSizePolicy(sizePolicy2)
        self.pushButton_sampleStepBackward.setMinimumSize(QSize(60, 60))
        self.pushButton_sampleStepBackward.setMaximumSize(QSize(60, 16777215))

        self.gridLayout_3.addWidget(self.pushButton_sampleStepBackward, 1, 1, 1, 1)

        self.horizontalSpacer_7 = QSpacerItem(60, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.gridLayout_3.addItem(self.horizontalSpacer_7, 1, 0, 1, 1)

        self.pushButton_sampleStepDown = QPushButton(self.groupBox_SampleMovement)
        self.pushButton_sampleStepDown.setObjectName(u"pushButton_sampleStepDown")
        sizePolicy2.setHeightForWidth(self.pushButton_sampleStepDown.sizePolicy().hasHeightForWidth())
        self.pushButton_sampleStepDown.setSizePolicy(sizePolicy2)
        self.pushButton_sampleStepDown.setMinimumSize(QSize(60, 60))
        self.pushButton_sampleStepDown.setMaximumSize(QSize(60, 16777215))

        self.gridLayout_3.addWidget(self.pushButton_sampleStepDown, 2, 2, 1, 1)


        self.verticalLayout_32.addLayout(self.gridLayout_3)

        self.horizontalLayout_55 = QHBoxLayout()
        self.horizontalLayout_55.setObjectName(u"horizontalLayout_55")
        self.label_25 = QLabel(self.groupBox_SampleMovement)
        self.label_25.setObjectName(u"label_25")
        sizePolicy4.setHeightForWidth(self.label_25.sizePolicy().hasHeightForWidth())
        self.label_25.setSizePolicy(sizePolicy4)

        self.horizontalLayout_55.addWidget(self.label_25)

        self.doubleSpinBox_sampleHStepSize = QDoubleSpinBox(self.groupBox_SampleMovement)
        self.doubleSpinBox_sampleHStepSize.setObjectName(u"doubleSpinBox_sampleHStepSize")
        sizePolicy2.setHeightForWidth(self.doubleSpinBox_sampleHStepSize.sizePolicy().hasHeightForWidth())
        self.doubleSpinBox_sampleHStepSize.setSizePolicy(sizePolicy2)
        self.doubleSpinBox_sampleHStepSize.setMinimumSize(QSize(75, 0))
        self.doubleSpinBox_sampleHStepSize.setDecimals(3)

        self.horizontalLayout_55.addWidget(self.doubleSpinBox_sampleHStepSize)

        self.horizontalSpacer_9 = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayout_55.addItem(self.horizontalSpacer_9)

        self.label_26 = QLabel(self.groupBox_SampleMovement)
        self.label_26.setObjectName(u"label_26")
        sizePolicy4.setHeightForWidth(self.label_26.sizePolicy().hasHeightForWidth())
        self.label_26.setSizePolicy(sizePolicy4)

        self.horizontalLayout_55.addWidget(self.label_26)

        self.doubleSpinBox_sampleVStepSize = QDoubleSpinBox(self.groupBox_SampleMovement)
        self.doubleSpinBox_sampleVStepSize.setObjectName(u"doubleSpinBox_sampleVStepSize")
        sizePolicy2.setHeightForWidth(self.doubleSpinBox_sampleVStepSize.sizePolicy().hasHeightForWidth())
        self.doubleSpinBox_sampleVStepSize.setSizePolicy(sizePolicy2)
        self.doubleSpinBox_sampleVStepSize.setMinimumSize(QSize(75, 0))
        self.doubleSpinBox_sampleVStepSize.setDecimals(3)

        self.horizontalLayout_55.addWidget(self.doubleSpinBox_sampleVStepSize)


        self.verticalLayout_32.addLayout(self.horizontalLayout_55)

        self.line_3 = QFrame(self.groupBox_SampleMovement)
        self.line_3.setObjectName(u"line_3")
        self.line_3.setFrameShape(QFrame.Shape.HLine)
        self.line_3.setFrameShadow(QFrame.Shadow.Sunken)

        self.verticalLayout_32.addWidget(self.line_3)

        self.horizontalLayout_53 = QHBoxLayout()
        self.horizontalLayout_53.setObjectName(u"horizontalLayout_53")
        self.label_23 = QLabel(self.groupBox_SampleMovement)
        self.label_23.setObjectName(u"label_23")
        sizePolicy2.setHeightForWidth(self.label_23.sizePolicy().hasHeightForWidth())
        self.label_23.setSizePolicy(sizePolicy2)
        self.label_23.setMinimumSize(QSize(100, 20))

        self.horizontalLayout_53.addWidget(self.label_23)

        self.doubleSpinBox_sampleSetHPosition = QDoubleSpinBox(self.groupBox_SampleMovement)
        self.doubleSpinBox_sampleSetHPosition.setObjectName(u"doubleSpinBox_sampleSetHPosition")
        sizePolicy5 = QSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Fixed)
        sizePolicy5.setHorizontalStretch(0)
        sizePolicy5.setVerticalStretch(0)
        sizePolicy5.setHeightForWidth(self.doubleSpinBox_sampleSetHPosition.sizePolicy().hasHeightForWidth())
        self.doubleSpinBox_sampleSetHPosition.setSizePolicy(sizePolicy5)
        self.doubleSpinBox_sampleSetHPosition.setMinimumSize(QSize(100, 20))
        self.doubleSpinBox_sampleSetHPosition.setMaximumSize(QSize(100, 20))
        self.doubleSpinBox_sampleSetHPosition.setDecimals(3)

        self.horizontalLayout_53.addWidget(self.doubleSpinBox_sampleSetHPosition)

        self.pushButton_sampleGotoHPosition = QPushButton(self.groupBox_SampleMovement)
        self.pushButton_sampleGotoHPosition.setObjectName(u"pushButton_sampleGotoHPosition")
        sizePolicy2.setHeightForWidth(self.pushButton_sampleGotoHPosition.sizePolicy().hasHeightForWidth())
        self.pushButton_sampleGotoHPosition.setSizePolicy(sizePolicy2)
        self.pushButton_sampleGotoHPosition.setMinimumSize(QSize(90, 23))
        self.pushButton_sampleGotoHPosition.setMaximumSize(QSize(90, 23))

        self.horizontalLayout_53.addWidget(self.pushButton_sampleGotoHPosition)


        self.verticalLayout_32.addLayout(self.horizontalLayout_53)

        self.horizontalLayout_54 = QHBoxLayout()
        self.horizontalLayout_54.setObjectName(u"horizontalLayout_54")
        self.label_24 = QLabel(self.groupBox_SampleMovement)
        self.label_24.setObjectName(u"label_24")
        sizePolicy2.setHeightForWidth(self.label_24.sizePolicy().hasHeightForWidth())
        self.label_24.setSizePolicy(sizePolicy2)
        self.label_24.setMinimumSize(QSize(100, 20))

        self.horizontalLayout_54.addWidget(self.label_24)

        self.doubleSpinBox_sampleSetVPosition = QDoubleSpinBox(self.groupBox_SampleMovement)
        self.doubleSpinBox_sampleSetVPosition.setObjectName(u"doubleSpinBox_sampleSetVPosition")
        sizePolicy5.setHeightForWidth(self.doubleSpinBox_sampleSetVPosition.sizePolicy().hasHeightForWidth())
        self.doubleSpinBox_sampleSetVPosition.setSizePolicy(sizePolicy5)
        self.doubleSpinBox_sampleSetVPosition.setMinimumSize(QSize(100, 20))
        self.doubleSpinBox_sampleSetVPosition.setMaximumSize(QSize(100, 20))
        self.doubleSpinBox_sampleSetVPosition.setDecimals(3)

        self.horizontalLayout_54.addWidget(self.doubleSpinBox_sampleSetVPosition)

        self.pushButton_sampleGotoVPosition = QPushButton(self.groupBox_SampleMovement)
        self.pushButton_sampleGotoVPosition.setObjectName(u"pushButton_sampleGotoVPosition")
        sizePolicy2.setHeightForWidth(self.pushButton_sampleGotoVPosition.sizePolicy().hasHeightForWidth())
        self.pushButton_sampleGotoVPosition.setSizePolicy(sizePolicy2)
        self.pushButton_sampleGotoVPosition.setMinimumSize(QSize(90, 23))
        self.pushButton_sampleGotoVPosition.setMaximumSize(QSize(90, 23))

        self.horizontalLayout_54.addWidget(self.pushButton_sampleGotoVPosition)


        self.verticalLayout_32.addLayout(self.horizontalLayout_54)


        self.gridLayout_7.addLayout(self.verticalLayout_32, 0, 0, 1, 1)


        self.horizontalLayout_2.addWidget(self.groupBox_SampleMovement)

        self.groupBox_CameraMovement = QGroupBox(self.tabMotion)
        self.groupBox_CameraMovement.setObjectName(u"groupBox_CameraMovement")
        sizePolicy2.setHeightForWidth(self.groupBox_CameraMovement.sizePolicy().hasHeightForWidth())
        self.groupBox_CameraMovement.setSizePolicy(sizePolicy2)
        self.groupBox_CameraMovement.setMinimumSize(QSize(350, 380))
        self.groupBox_CameraMovement.setMaximumSize(QSize(350, 380))
        self.gridLayout_6 = QGridLayout(self.groupBox_CameraMovement)
        self.gridLayout_6.setObjectName(u"gridLayout_6")
        self.verticalLayout_34 = QVBoxLayout()
        self.verticalLayout_34.setObjectName(u"verticalLayout_34")
        self.horizontalLayout_58 = QHBoxLayout()
        self.horizontalLayout_58.setObjectName(u"horizontalLayout_58")
        self.gridLayout_10 = QGridLayout()
        self.gridLayout_10.setObjectName(u"gridLayout_10")
        self.label_31 = QLabel(self.groupBox_CameraMovement)
        self.label_31.setObjectName(u"label_31")
        sizePolicy4.setHeightForWidth(self.label_31.sizePolicy().hasHeightForWidth())
        self.label_31.setSizePolicy(sizePolicy4)
        self.label_31.setMinimumSize(QSize(135, 0))

        self.gridLayout_10.addWidget(self.label_31, 0, 0, 1, 1)

        self.label_cameraCurrentPosition = QLabel(self.groupBox_CameraMovement)
        self.label_cameraCurrentPosition.setObjectName(u"label_cameraCurrentPosition")
        self.label_cameraCurrentPosition.setMinimumSize(QSize(50, 0))

        self.gridLayout_10.addWidget(self.label_cameraCurrentPosition, 0, 1, 1, 1)

        self.label = QLabel(self.groupBox_CameraMovement)
        self.label.setObjectName(u"label")

        self.gridLayout_10.addWidget(self.label, 1, 0, 1, 1)

        self.label_2 = QLabel(self.groupBox_CameraMovement)
        self.label_2.setObjectName(u"label_2")
        sizePolicy6 = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        sizePolicy6.setHorizontalStretch(50)
        sizePolicy6.setVerticalStretch(0)
        sizePolicy6.setHeightForWidth(self.label_2.sizePolicy().hasHeightForWidth())
        self.label_2.setSizePolicy(sizePolicy6)

        self.gridLayout_10.addWidget(self.label_2, 1, 1, 1, 1)


        self.horizontalLayout_58.addLayout(self.gridLayout_10)

        self.pushButton_cameraSetFocus = QPushButton(self.groupBox_CameraMovement)
        self.pushButton_cameraSetFocus.setObjectName(u"pushButton_cameraSetFocus")
        sizePolicy2.setHeightForWidth(self.pushButton_cameraSetFocus.sizePolicy().hasHeightForWidth())
        self.pushButton_cameraSetFocus.setSizePolicy(sizePolicy2)
        self.pushButton_cameraSetFocus.setMinimumSize(QSize(75, 0))

        self.horizontalLayout_58.addWidget(self.pushButton_cameraSetFocus)


        self.verticalLayout_34.addLayout(self.horizontalLayout_58)

        self.line_2 = QFrame(self.groupBox_CameraMovement)
        self.line_2.setObjectName(u"line_2")
        self.line_2.setFrameShape(QFrame.Shape.HLine)
        self.line_2.setFrameShadow(QFrame.Shadow.Sunken)

        self.verticalLayout_34.addWidget(self.line_2)

        self.gridLayout_8 = QGridLayout()
        self.gridLayout_8.setObjectName(u"gridLayout_8")
        self.horizontalSpacer_4 = QSpacerItem(60, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.gridLayout_8.addItem(self.horizontalSpacer_4, 1, 0, 1, 1)

        self.pushButton_cameraStepForward = QPushButton(self.groupBox_CameraMovement)
        self.pushButton_cameraStepForward.setObjectName(u"pushButton_cameraStepForward")
        sizePolicy2.setHeightForWidth(self.pushButton_cameraStepForward.sizePolicy().hasHeightForWidth())
        self.pushButton_cameraStepForward.setSizePolicy(sizePolicy2)
        self.pushButton_cameraStepForward.setMinimumSize(QSize(60, 60))
        self.pushButton_cameraStepForward.setMaximumSize(QSize(60, 60))

        self.gridLayout_8.addWidget(self.pushButton_cameraStepForward, 1, 3, 1, 1)

        self.horizontalSpacer_5 = QSpacerItem(60, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.gridLayout_8.addItem(self.horizontalSpacer_5, 1, 4, 1, 1)

        self.label_3 = QLabel(self.groupBox_CameraMovement)
        self.label_3.setObjectName(u"label_3")
        sizePolicy2.setHeightForWidth(self.label_3.sizePolicy().hasHeightForWidth())
        self.label_3.setSizePolicy(sizePolicy2)
        self.label_3.setMinimumSize(QSize(60, 60))
        self.label_3.setMaximumSize(QSize(60, 60))

        self.gridLayout_8.addWidget(self.label_3, 0, 2, 1, 1)

        self.pushButton_cameraGotoFocus = QPushButton(self.groupBox_CameraMovement)
        self.pushButton_cameraGotoFocus.setObjectName(u"pushButton_cameraGotoFocus")
        sizePolicy2.setHeightForWidth(self.pushButton_cameraGotoFocus.sizePolicy().hasHeightForWidth())
        self.pushButton_cameraGotoFocus.setSizePolicy(sizePolicy2)
        self.pushButton_cameraGotoFocus.setMinimumSize(QSize(60, 60))
        self.pushButton_cameraGotoFocus.setMaximumSize(QSize(60, 60))

        self.gridLayout_8.addWidget(self.pushButton_cameraGotoFocus, 1, 2, 1, 1)

        self.pushButton_cameraStepBackward = QPushButton(self.groupBox_CameraMovement)
        self.pushButton_cameraStepBackward.setObjectName(u"pushButton_cameraStepBackward")
        sizePolicy2.setHeightForWidth(self.pushButton_cameraStepBackward.sizePolicy().hasHeightForWidth())
        self.pushButton_cameraStepBackward.setSizePolicy(sizePolicy2)
        self.pushButton_cameraStepBackward.setMinimumSize(QSize(60, 60))
        self.pushButton_cameraStepBackward.setMaximumSize(QSize(60, 60))

        self.gridLayout_8.addWidget(self.pushButton_cameraStepBackward, 1, 1, 1, 1)

        self.label_4 = QLabel(self.groupBox_CameraMovement)
        self.label_4.setObjectName(u"label_4")
        sizePolicy2.setHeightForWidth(self.label_4.sizePolicy().hasHeightForWidth())
        self.label_4.setSizePolicy(sizePolicy2)
        self.label_4.setMinimumSize(QSize(60, 60))
        self.label_4.setMaximumSize(QSize(60, 60))

        self.gridLayout_8.addWidget(self.label_4, 2, 2, 1, 1)


        self.verticalLayout_34.addLayout(self.gridLayout_8)

        self.horizontalLayout_62 = QHBoxLayout()
        self.horizontalLayout_62.setObjectName(u"horizontalLayout_62")
        self.horizontalSpacer_3 = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayout_62.addItem(self.horizontalSpacer_3)

        self.label_33 = QLabel(self.groupBox_CameraMovement)
        self.label_33.setObjectName(u"label_33")
        sizePolicy4.setHeightForWidth(self.label_33.sizePolicy().hasHeightForWidth())
        self.label_33.setSizePolicy(sizePolicy4)

        self.horizontalLayout_62.addWidget(self.label_33)

        self.doubleSpinBox_cameraStepSize = QDoubleSpinBox(self.groupBox_CameraMovement)
        self.doubleSpinBox_cameraStepSize.setObjectName(u"doubleSpinBox_cameraStepSize")
        sizePolicy2.setHeightForWidth(self.doubleSpinBox_cameraStepSize.sizePolicy().hasHeightForWidth())
        self.doubleSpinBox_cameraStepSize.setSizePolicy(sizePolicy2)
        self.doubleSpinBox_cameraStepSize.setMinimumSize(QSize(75, 0))
        self.doubleSpinBox_cameraStepSize.setDecimals(3)

        self.horizontalLayout_62.addWidget(self.doubleSpinBox_cameraStepSize)


        self.verticalLayout_34.addLayout(self.horizontalLayout_62)

        self.line_4 = QFrame(self.groupBox_CameraMovement)
        self.line_4.setObjectName(u"line_4")
        self.line_4.setFrameShape(QFrame.Shape.HLine)
        self.line_4.setFrameShadow(QFrame.Shadow.Sunken)

        self.verticalLayout_34.addWidget(self.line_4)

        self.horizontalLayout_59 = QHBoxLayout()
        self.horizontalLayout_59.setObjectName(u"horizontalLayout_59")
        self.label_32 = QLabel(self.groupBox_CameraMovement)
        self.label_32.setObjectName(u"label_32")
        sizePolicy2.setHeightForWidth(self.label_32.sizePolicy().hasHeightForWidth())
        self.label_32.setSizePolicy(sizePolicy2)
        self.label_32.setMinimumSize(QSize(100, 20))
        self.label_32.setMaximumSize(QSize(100, 20))

        self.horizontalLayout_59.addWidget(self.label_32)

        self.doubleSpinBox_cameraSetPosition = QDoubleSpinBox(self.groupBox_CameraMovement)
        self.doubleSpinBox_cameraSetPosition.setObjectName(u"doubleSpinBox_cameraSetPosition")
        sizePolicy5.setHeightForWidth(self.doubleSpinBox_cameraSetPosition.sizePolicy().hasHeightForWidth())
        self.doubleSpinBox_cameraSetPosition.setSizePolicy(sizePolicy5)
        self.doubleSpinBox_cameraSetPosition.setMinimumSize(QSize(100, 20))
        self.doubleSpinBox_cameraSetPosition.setMaximumSize(QSize(100, 20))
        self.doubleSpinBox_cameraSetPosition.setDecimals(3)

        self.horizontalLayout_59.addWidget(self.doubleSpinBox_cameraSetPosition)

        self.pushButton_cameraGotoPosition = QPushButton(self.groupBox_CameraMovement)
        self.pushButton_cameraGotoPosition.setObjectName(u"pushButton_cameraGotoPosition")
        sizePolicy2.setHeightForWidth(self.pushButton_cameraGotoPosition.sizePolicy().hasHeightForWidth())
        self.pushButton_cameraGotoPosition.setSizePolicy(sizePolicy2)
        self.pushButton_cameraGotoPosition.setMinimumSize(QSize(90, 23))
        self.pushButton_cameraGotoPosition.setMaximumSize(QSize(90, 23))

        self.horizontalLayout_59.addWidget(self.pushButton_cameraGotoPosition)


        self.verticalLayout_34.addLayout(self.horizontalLayout_59)

        self.horizontalLayout = QHBoxLayout()
        self.horizontalLayout.setObjectName(u"horizontalLayout")
        self.label_5 = QLabel(self.groupBox_CameraMovement)
        self.label_5.setObjectName(u"label_5")
        self.label_5.setMinimumSize(QSize(0, 23))

        self.horizontalLayout.addWidget(self.label_5)


        self.verticalLayout_34.addLayout(self.horizontalLayout)


        self.gridLayout_6.addLayout(self.verticalLayout_34, 0, 0, 1, 1)


        self.horizontalLayout_2.addWidget(self.groupBox_CameraMovement)

        self.horizontalLayout_2.setStretch(0, 1)
        self.horizontalLayout_2.setStretch(1, 1)

        self.verticalLayout_2.addLayout(self.horizontalLayout_2)

        self.tabControls.addTab(self.tabMotion, "")
        self.tabSettings = QWidget()
        self.tabSettings.setObjectName(u"tabSettings")
        self.verticalLayout_36 = QVBoxLayout(self.tabSettings)
        self.verticalLayout_36.setObjectName(u"verticalLayout_36")
        self.horizontalLayout_66 = QHBoxLayout()
        self.horizontalLayout_66.setObjectName(u"horizontalLayout_66")
        self.horizontalSpacer_6 = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayout_66.addItem(self.horizontalSpacer_6)

        self.pushButton_resetSettings = QPushButton(self.tabSettings)
        self.pushButton_resetSettings.setObjectName(u"pushButton_resetSettings")

        self.horizontalLayout_66.addWidget(self.pushButton_resetSettings)


        self.verticalLayout_36.addLayout(self.horizontalLayout_66)

        self.verticalLayout_37 = QVBoxLayout()
        self.verticalLayout_37.setObjectName(u"verticalLayout_37")
        self.gridLayout_4 = QGridLayout()
        self.gridLayout_4.setObjectName(u"gridLayout_4")
        self.groupBox_13 = QGroupBox(self.tabSettings)
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
        sizePolicy.setHeightForWidth(self.line_23.sizePolicy().hasHeightForWidth())
        self.line_23.setSizePolicy(sizePolicy)
        self.line_23.setFrameShape(QFrame.Shape.HLine)
        self.line_23.setFrameShadow(QFrame.Shadow.Sunken)

        self.verticalLayout_46.addWidget(self.line_23)

        self.formLayout_16 = QFormLayout()
        self.formLayout_16.setObjectName(u"formLayout_16")
        self.label_78 = QLabel(self.groupBox_13)
        self.label_78.setObjectName(u"label_78")
        sizePolicy4.setHeightForWidth(self.label_78.sizePolicy().hasHeightForWidth())
        self.label_78.setSizePolicy(sizePolicy4)

        self.formLayout_16.setWidget(0, QFormLayout.ItemRole.LabelRole, self.label_78)

        self.doubleSpinBox_etlLeftAmplitude = QDoubleSpinBox(self.groupBox_13)
        self.doubleSpinBox_etlLeftAmplitude.setObjectName(u"doubleSpinBox_etlLeftAmplitude")
        sizePolicy3.setHeightForWidth(self.doubleSpinBox_etlLeftAmplitude.sizePolicy().hasHeightForWidth())
        self.doubleSpinBox_etlLeftAmplitude.setSizePolicy(sizePolicy3)
        self.doubleSpinBox_etlLeftAmplitude.setMinimum(0.000000000000000)
        self.doubleSpinBox_etlLeftAmplitude.setMaximum(5.000000000000000)
        self.doubleSpinBox_etlLeftAmplitude.setSingleStep(0.100000000000000)

        self.formLayout_16.setWidget(0, QFormLayout.ItemRole.FieldRole, self.doubleSpinBox_etlLeftAmplitude)

        self.label_79 = QLabel(self.groupBox_13)
        self.label_79.setObjectName(u"label_79")
        sizePolicy4.setHeightForWidth(self.label_79.sizePolicy().hasHeightForWidth())
        self.label_79.setSizePolicy(sizePolicy4)

        self.formLayout_16.setWidget(1, QFormLayout.ItemRole.LabelRole, self.label_79)

        self.doubleSpinBox_etlLeftOffset = QDoubleSpinBox(self.groupBox_13)
        self.doubleSpinBox_etlLeftOffset.setObjectName(u"doubleSpinBox_etlLeftOffset")
        sizePolicy3.setHeightForWidth(self.doubleSpinBox_etlLeftOffset.sizePolicy().hasHeightForWidth())
        self.doubleSpinBox_etlLeftOffset.setSizePolicy(sizePolicy3)
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
        sizePolicy4.setHeightForWidth(self.label_81.sizePolicy().hasHeightForWidth())
        self.label_81.setSizePolicy(sizePolicy4)

        self.formLayout_17.setWidget(0, QFormLayout.ItemRole.LabelRole, self.label_81)

        self.doubleSpinBox_etlRightAmplitude = QDoubleSpinBox(self.groupBox_13)
        self.doubleSpinBox_etlRightAmplitude.setObjectName(u"doubleSpinBox_etlRightAmplitude")
        sizePolicy3.setHeightForWidth(self.doubleSpinBox_etlRightAmplitude.sizePolicy().hasHeightForWidth())
        self.doubleSpinBox_etlRightAmplitude.setSizePolicy(sizePolicy3)
        self.doubleSpinBox_etlRightAmplitude.setMinimum(0.000000000000000)
        self.doubleSpinBox_etlRightAmplitude.setMaximum(5.000000000000000)
        self.doubleSpinBox_etlRightAmplitude.setSingleStep(0.100000000000000)

        self.formLayout_17.setWidget(0, QFormLayout.ItemRole.FieldRole, self.doubleSpinBox_etlRightAmplitude)

        self.label_82 = QLabel(self.groupBox_13)
        self.label_82.setObjectName(u"label_82")
        sizePolicy4.setHeightForWidth(self.label_82.sizePolicy().hasHeightForWidth())
        self.label_82.setSizePolicy(sizePolicy4)

        self.formLayout_17.setWidget(1, QFormLayout.ItemRole.LabelRole, self.label_82)

        self.doubleSpinBox_etlRightOffset = QDoubleSpinBox(self.groupBox_13)
        self.doubleSpinBox_etlRightOffset.setObjectName(u"doubleSpinBox_etlRightOffset")
        sizePolicy3.setHeightForWidth(self.doubleSpinBox_etlRightOffset.sizePolicy().hasHeightForWidth())
        self.doubleSpinBox_etlRightOffset.setSizePolicy(sizePolicy3)
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
        sizePolicy2.setHeightForWidth(self.label_35.sizePolicy().hasHeightForWidth())
        self.label_35.setSizePolicy(sizePolicy2)

        self.horizontalLayout_70.addWidget(self.label_35)

        self.doubleSpinBox_etlSteps = QDoubleSpinBox(self.groupBox_13)
        self.doubleSpinBox_etlSteps.setObjectName(u"doubleSpinBox_etlSteps")
        sizePolicy.setHeightForWidth(self.doubleSpinBox_etlSteps.sizePolicy().hasHeightForWidth())
        self.doubleSpinBox_etlSteps.setSizePolicy(sizePolicy)
        self.doubleSpinBox_etlSteps.setDecimals(0)
        self.doubleSpinBox_etlSteps.setMinimum(1.000000000000000)

        self.horizontalLayout_70.addWidget(self.doubleSpinBox_etlSteps)


        self.verticalLayout_45.addLayout(self.horizontalLayout_70)


        self.gridLayout_4.addWidget(self.groupBox_13, 0, 0, 1, 1)

        self.groupBox_12 = QGroupBox(self.tabSettings)
        self.groupBox_12.setObjectName(u"groupBox_12")
        self.formLayout = QFormLayout(self.groupBox_12)
        self.formLayout.setObjectName(u"formLayout")
        self.label_9 = QLabel(self.groupBox_12)
        self.label_9.setObjectName(u"label_9")

        self.formLayout.setWidget(1, QFormLayout.ItemRole.LabelRole, self.label_9)

        self.comboBox_cameraShutterMode = QComboBox(self.groupBox_12)
        self.comboBox_cameraShutterMode.setObjectName(u"comboBox_cameraShutterMode")

        self.formLayout.setWidget(1, QFormLayout.ItemRole.FieldRole, self.comboBox_cameraShutterMode)

        self.label_doubleSpinBox_cameraExposureTime = QLabel(self.groupBox_12)
        self.label_doubleSpinBox_cameraExposureTime.setObjectName(u"label_doubleSpinBox_cameraExposureTime")

        self.formLayout.setWidget(2, QFormLayout.ItemRole.LabelRole, self.label_doubleSpinBox_cameraExposureTime)

        self.doubleSpinBox_cameraExposureTime = QDoubleSpinBox(self.groupBox_12)
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

        self.doubleSpinBox_cameraLineTime = QDoubleSpinBox(self.groupBox_12)
        self.doubleSpinBox_cameraLineTime.setObjectName(u"doubleSpinBox_cameraLineTime")
        self.doubleSpinBox_cameraLineTime.setDecimals(3)
        self.doubleSpinBox_cameraLineTime.setMinimum(12.175000000000001)
        self.doubleSpinBox_cameraLineTime.setMaximum(500.000000000000000)

        self.formLayout.setWidget(3, QFormLayout.ItemRole.FieldRole, self.doubleSpinBox_cameraLineTime)

        self.label_doubleSpinBox_cameraExposedLines = QLabel(self.groupBox_12)
        self.label_doubleSpinBox_cameraExposedLines.setObjectName(u"label_doubleSpinBox_cameraExposedLines")

        self.formLayout.setWidget(4, QFormLayout.ItemRole.LabelRole, self.label_doubleSpinBox_cameraExposedLines)

        self.doubleSpinBox_cameraExposedLines = QDoubleSpinBox(self.groupBox_12)
        self.doubleSpinBox_cameraExposedLines.setObjectName(u"doubleSpinBox_cameraExposedLines")
        self.doubleSpinBox_cameraExposedLines.setDecimals(0)
        self.doubleSpinBox_cameraExposedLines.setMinimum(1.000000000000000)
        self.doubleSpinBox_cameraExposedLines.setMaximum(1024.000000000000000)

        self.formLayout.setWidget(4, QFormLayout.ItemRole.FieldRole, self.doubleSpinBox_cameraExposedLines)

        self.label_doubleSpinBox_cameraDelayLines = QLabel(self.groupBox_12)
        self.label_doubleSpinBox_cameraDelayLines.setObjectName(u"label_doubleSpinBox_cameraDelayLines")

        self.formLayout.setWidget(5, QFormLayout.ItemRole.LabelRole, self.label_doubleSpinBox_cameraDelayLines)

        self.doubleSpinBox_cameraDelayLines = QDoubleSpinBox(self.groupBox_12)
        self.doubleSpinBox_cameraDelayLines.setObjectName(u"doubleSpinBox_cameraDelayLines")
        self.doubleSpinBox_cameraDelayLines.setDecimals(0)
        self.doubleSpinBox_cameraDelayLines.setMaximum(1024.000000000000000)

        self.formLayout.setWidget(5, QFormLayout.ItemRole.FieldRole, self.doubleSpinBox_cameraDelayLines)


        self.gridLayout_4.addWidget(self.groupBox_12, 1, 1, 1, 1)

        self.groupBox_15 = QGroupBox(self.tabSettings)
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
        sizePolicy.setHeightForWidth(self.line_20.sizePolicy().hasHeightForWidth())
        self.line_20.setSizePolicy(sizePolicy)
        self.line_20.setFrameShape(QFrame.Shape.HLine)
        self.line_20.setFrameShadow(QFrame.Shadow.Sunken)

        self.verticalLayout_43.addWidget(self.line_20)

        self.formLayout_14 = QFormLayout()
        self.formLayout_14.setObjectName(u"formLayout_14")
        self.label_50 = QLabel(self.groupBox_15)
        self.label_50.setObjectName(u"label_50")
        sizePolicy4.setHeightForWidth(self.label_50.sizePolicy().hasHeightForWidth())
        self.label_50.setSizePolicy(sizePolicy4)

        self.formLayout_14.setWidget(0, QFormLayout.ItemRole.LabelRole, self.label_50)

        self.doubleSpinBox_laserOneAmplitude = QDoubleSpinBox(self.groupBox_15)
        self.doubleSpinBox_laserOneAmplitude.setObjectName(u"doubleSpinBox_laserOneAmplitude")
        sizePolicy3.setHeightForWidth(self.doubleSpinBox_laserOneAmplitude.sizePolicy().hasHeightForWidth())
        self.doubleSpinBox_laserOneAmplitude.setSizePolicy(sizePolicy3)
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
        sizePolicy4.setHeightForWidth(self.label_74.sizePolicy().hasHeightForWidth())
        self.label_74.setSizePolicy(sizePolicy4)

        self.formLayout_15.setWidget(0, QFormLayout.ItemRole.LabelRole, self.label_74)

        self.doubleSpinBox_laserTwoAmplitude = QDoubleSpinBox(self.groupBox_15)
        self.doubleSpinBox_laserTwoAmplitude.setObjectName(u"doubleSpinBox_laserTwoAmplitude")
        sizePolicy3.setHeightForWidth(self.doubleSpinBox_laserTwoAmplitude.sizePolicy().hasHeightForWidth())
        self.doubleSpinBox_laserTwoAmplitude.setSizePolicy(sizePolicy3)
        self.doubleSpinBox_laserTwoAmplitude.setDecimals(0)
        self.doubleSpinBox_laserTwoAmplitude.setMaximum(100.000000000000000)
        self.doubleSpinBox_laserTwoAmplitude.setSingleStep(1.000000000000000)

        self.formLayout_15.setWidget(0, QFormLayout.ItemRole.FieldRole, self.doubleSpinBox_laserTwoAmplitude)


        self.verticalLayout_44.addLayout(self.formLayout_15)

        self.checkBox_laserTwoAutomatic = QCheckBox(self.groupBox_15)
        self.checkBox_laserTwoAutomatic.setObjectName(u"checkBox_laserTwoAutomatic")

        self.verticalLayout_44.addWidget(self.checkBox_laserTwoAutomatic)

        self.verticalSpacer_15 = QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.verticalLayout_44.addItem(self.verticalSpacer_15)


        self.horizontalLayout_68.addLayout(self.verticalLayout_44)


        self.gridLayout_4.addWidget(self.groupBox_15, 1, 0, 1, 1)

        self.groupBox_11 = QGroupBox(self.tabSettings)
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
        sizePolicy4.setHeightForWidth(self.label_61.sizePolicy().hasHeightForWidth())
        self.label_61.setSizePolicy(sizePolicy4)

        self.formLayout_10.setWidget(0, QFormLayout.ItemRole.LabelRole, self.label_61)

        self.doubleSpinBox_galvoLeftAmplitude = QDoubleSpinBox(self.groupBox_11)
        self.doubleSpinBox_galvoLeftAmplitude.setObjectName(u"doubleSpinBox_galvoLeftAmplitude")
        sizePolicy3.setHeightForWidth(self.doubleSpinBox_galvoLeftAmplitude.sizePolicy().hasHeightForWidth())
        self.doubleSpinBox_galvoLeftAmplitude.setSizePolicy(sizePolicy3)
        self.doubleSpinBox_galvoLeftAmplitude.setMaximum(10.000000000000000)
        self.doubleSpinBox_galvoLeftAmplitude.setSingleStep(0.100000000000000)

        self.formLayout_10.setWidget(0, QFormLayout.ItemRole.FieldRole, self.doubleSpinBox_galvoLeftAmplitude)

        self.label_62 = QLabel(self.groupBox_11)
        self.label_62.setObjectName(u"label_62")
        sizePolicy4.setHeightForWidth(self.label_62.sizePolicy().hasHeightForWidth())
        self.label_62.setSizePolicy(sizePolicy4)

        self.formLayout_10.setWidget(1, QFormLayout.ItemRole.LabelRole, self.label_62)

        self.doubleSpinBox_galvoLeftOffset = QDoubleSpinBox(self.groupBox_11)
        self.doubleSpinBox_galvoLeftOffset.setObjectName(u"doubleSpinBox_galvoLeftOffset")
        sizePolicy3.setHeightForWidth(self.doubleSpinBox_galvoLeftOffset.sizePolicy().hasHeightForWidth())
        self.doubleSpinBox_galvoLeftOffset.setSizePolicy(sizePolicy3)
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
        sizePolicy4.setHeightForWidth(self.label_65.sizePolicy().hasHeightForWidth())
        self.label_65.setSizePolicy(sizePolicy4)

        self.formLayout_11.setWidget(0, QFormLayout.ItemRole.LabelRole, self.label_65)

        self.doubleSpinBox_galvoRightAmplitude = QDoubleSpinBox(self.groupBox_11)
        self.doubleSpinBox_galvoRightAmplitude.setObjectName(u"doubleSpinBox_galvoRightAmplitude")
        sizePolicy3.setHeightForWidth(self.doubleSpinBox_galvoRightAmplitude.sizePolicy().hasHeightForWidth())
        self.doubleSpinBox_galvoRightAmplitude.setSizePolicy(sizePolicy3)
        self.doubleSpinBox_galvoRightAmplitude.setMaximum(10.000000000000000)
        self.doubleSpinBox_galvoRightAmplitude.setSingleStep(0.100000000000000)

        self.formLayout_11.setWidget(0, QFormLayout.ItemRole.FieldRole, self.doubleSpinBox_galvoRightAmplitude)

        self.label_66 = QLabel(self.groupBox_11)
        self.label_66.setObjectName(u"label_66")
        sizePolicy4.setHeightForWidth(self.label_66.sizePolicy().hasHeightForWidth())
        self.label_66.setSizePolicy(sizePolicy4)

        self.formLayout_11.setWidget(1, QFormLayout.ItemRole.LabelRole, self.label_66)

        self.doubleSpinBox_galvoRightOffset = QDoubleSpinBox(self.groupBox_11)
        self.doubleSpinBox_galvoRightOffset.setObjectName(u"doubleSpinBox_galvoRightOffset")
        sizePolicy3.setHeightForWidth(self.doubleSpinBox_galvoRightOffset.sizePolicy().hasHeightForWidth())
        self.doubleSpinBox_galvoRightOffset.setSizePolicy(sizePolicy3)
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


        self.gridLayout_4.addWidget(self.groupBox_11, 0, 1, 1, 1)


        self.verticalLayout_37.addLayout(self.gridLayout_4)

        self.verticalSpacer_6 = QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.verticalLayout_37.addItem(self.verticalSpacer_6)


        self.verticalLayout_36.addLayout(self.verticalLayout_37)

        self.tabControls.addTab(self.tabSettings, "")
        self.tabCalibration = QWidget()
        self.tabCalibration.setObjectName(u"tabCalibration")
        self.verticalLayout_4 = QVBoxLayout(self.tabCalibration)
        self.verticalLayout_4.setObjectName(u"verticalLayout_4")
        self.gridLayout = QGridLayout()
        self.gridLayout.setObjectName(u"gridLayout")
        self.groupBox_2 = QGroupBox(self.tabCalibration)
        self.groupBox_2.setObjectName(u"groupBox_2")
        self.verticalLayout_5 = QVBoxLayout(self.groupBox_2)
        self.verticalLayout_5.setObjectName(u"verticalLayout_5")
        self.formLayout_2 = QFormLayout()
        self.formLayout_2.setObjectName(u"formLayout_2")
        self.label_28 = QLabel(self.groupBox_2)
        self.label_28.setObjectName(u"label_28")
        sizePolicy4.setHeightForWidth(self.label_28.sizePolicy().hasHeightForWidth())
        self.label_28.setSizePolicy(sizePolicy4)

        self.formLayout_2.setWidget(0, QFormLayout.ItemRole.LabelRole, self.label_28)

        self.doubleSpinBox_calNumberOfPlanes = QDoubleSpinBox(self.groupBox_2)
        self.doubleSpinBox_calNumberOfPlanes.setObjectName(u"doubleSpinBox_calNumberOfPlanes")
        sizePolicy3.setHeightForWidth(self.doubleSpinBox_calNumberOfPlanes.sizePolicy().hasHeightForWidth())
        self.doubleSpinBox_calNumberOfPlanes.setSizePolicy(sizePolicy3)
        self.doubleSpinBox_calNumberOfPlanes.setDecimals(0)
        self.doubleSpinBox_calNumberOfPlanes.setMinimum(3.000000000000000)
        self.doubleSpinBox_calNumberOfPlanes.setMaximum(1000.000000000000000)
        self.doubleSpinBox_calNumberOfPlanes.setValue(10.000000000000000)

        self.formLayout_2.setWidget(0, QFormLayout.ItemRole.FieldRole, self.doubleSpinBox_calNumberOfPlanes)

        self.label_43 = QLabel(self.groupBox_2)
        self.label_43.setObjectName(u"label_43")
        sizePolicy4.setHeightForWidth(self.label_43.sizePolicy().hasHeightForWidth())
        self.label_43.setSizePolicy(sizePolicy4)

        self.formLayout_2.setWidget(1, QFormLayout.ItemRole.LabelRole, self.label_43)

        self.doubleSpinBox_calNumberOfCameraPositions = QDoubleSpinBox(self.groupBox_2)
        self.doubleSpinBox_calNumberOfCameraPositions.setObjectName(u"doubleSpinBox_calNumberOfCameraPositions")
        sizePolicy3.setHeightForWidth(self.doubleSpinBox_calNumberOfCameraPositions.sizePolicy().hasHeightForWidth())
        self.doubleSpinBox_calNumberOfCameraPositions.setSizePolicy(sizePolicy3)
        self.doubleSpinBox_calNumberOfCameraPositions.setDecimals(0)
        self.doubleSpinBox_calNumberOfCameraPositions.setMinimum(1.000000000000000)
        self.doubleSpinBox_calNumberOfCameraPositions.setMaximum(1000.000000000000000)
        self.doubleSpinBox_calNumberOfCameraPositions.setValue(15.000000000000000)

        self.formLayout_2.setWidget(1, QFormLayout.ItemRole.FieldRole, self.doubleSpinBox_calNumberOfCameraPositions)


        self.verticalLayout_5.addLayout(self.formLayout_2)

        self.verticalSpacer_3 = QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.verticalLayout_5.addItem(self.verticalSpacer_3)

        self.pushButton_calCameraStartCalibration = QPushButton(self.groupBox_2)
        self.pushButton_calCameraStartCalibration.setObjectName(u"pushButton_calCameraStartCalibration")
        sizePolicy3.setHeightForWidth(self.pushButton_calCameraStartCalibration.sizePolicy().hasHeightForWidth())
        self.pushButton_calCameraStartCalibration.setSizePolicy(sizePolicy3)

        self.verticalLayout_5.addWidget(self.pushButton_calCameraStartCalibration)

        self.pushButton_calCameraShowInterpolation = QPushButton(self.groupBox_2)
        self.pushButton_calCameraShowInterpolation.setObjectName(u"pushButton_calCameraShowInterpolation")
        sizePolicy3.setHeightForWidth(self.pushButton_calCameraShowInterpolation.sizePolicy().hasHeightForWidth())
        self.pushButton_calCameraShowInterpolation.setSizePolicy(sizePolicy3)

        self.verticalLayout_5.addWidget(self.pushButton_calCameraShowInterpolation)

        self.pushButton_calCameraComputeFocus = QPushButton(self.groupBox_2)
        self.pushButton_calCameraComputeFocus.setObjectName(u"pushButton_calCameraComputeFocus")
        sizePolicy3.setHeightForWidth(self.pushButton_calCameraComputeFocus.sizePolicy().hasHeightForWidth())
        self.pushButton_calCameraComputeFocus.setSizePolicy(sizePolicy3)

        self.verticalLayout_5.addWidget(self.pushButton_calCameraComputeFocus)


        self.gridLayout.addWidget(self.groupBox_2, 0, 1, 1, 1)

        self.groupBox_3 = QGroupBox(self.tabCalibration)
        self.groupBox_3.setObjectName(u"groupBox_3")
        self.verticalLayout_6 = QVBoxLayout(self.groupBox_3)
        self.verticalLayout_6.setObjectName(u"verticalLayout_6")
        self.formLayout_3 = QFormLayout()
        self.formLayout_3.setObjectName(u"formLayout_3")
        self.label_47 = QLabel(self.groupBox_3)
        self.label_47.setObjectName(u"label_47")
        sizePolicy4.setHeightForWidth(self.label_47.sizePolicy().hasHeightForWidth())
        self.label_47.setSizePolicy(sizePolicy4)

        self.formLayout_3.setWidget(0, QFormLayout.ItemRole.LabelRole, self.label_47)

        self.doubleSpinBox_calNumberOfEtlVoltages = QDoubleSpinBox(self.groupBox_3)
        self.doubleSpinBox_calNumberOfEtlVoltages.setObjectName(u"doubleSpinBox_calNumberOfEtlVoltages")
        sizePolicy3.setHeightForWidth(self.doubleSpinBox_calNumberOfEtlVoltages.sizePolicy().hasHeightForWidth())
        self.doubleSpinBox_calNumberOfEtlVoltages.setSizePolicy(sizePolicy3)
        self.doubleSpinBox_calNumberOfEtlVoltages.setDecimals(0)
        self.doubleSpinBox_calNumberOfEtlVoltages.setMinimum(1.000000000000000)
        self.doubleSpinBox_calNumberOfEtlVoltages.setMaximum(1000.000000000000000)
        self.doubleSpinBox_calNumberOfEtlVoltages.setValue(10.000000000000000)

        self.formLayout_3.setWidget(0, QFormLayout.ItemRole.FieldRole, self.doubleSpinBox_calNumberOfEtlVoltages)


        self.verticalLayout_6.addLayout(self.formLayout_3)

        self.verticalSpacer_5 = QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.verticalLayout_6.addItem(self.verticalSpacer_5)

        self.pushButton_calEtlStartCalibration = QPushButton(self.groupBox_3)
        self.pushButton_calEtlStartCalibration.setObjectName(u"pushButton_calEtlStartCalibration")
        sizePolicy3.setHeightForWidth(self.pushButton_calEtlStartCalibration.sizePolicy().hasHeightForWidth())
        self.pushButton_calEtlStartCalibration.setSizePolicy(sizePolicy3)

        self.verticalLayout_6.addWidget(self.pushButton_calEtlStartCalibration)

        self.pushButton_calEtlShowInterpolation = QPushButton(self.groupBox_3)
        self.pushButton_calEtlShowInterpolation.setObjectName(u"pushButton_calEtlShowInterpolation")
        sizePolicy3.setHeightForWidth(self.pushButton_calEtlShowInterpolation.sizePolicy().hasHeightForWidth())
        self.pushButton_calEtlShowInterpolation.setSizePolicy(sizePolicy3)

        self.verticalLayout_6.addWidget(self.pushButton_calEtlShowInterpolation)


        self.gridLayout.addWidget(self.groupBox_3, 0, 2, 1, 1)

        self.groupBox = QGroupBox(self.tabCalibration)
        self.groupBox.setObjectName(u"groupBox")
        self.verticalLayout_12 = QVBoxLayout(self.groupBox)
        self.verticalLayout_12.setObjectName(u"verticalLayout_12")
        self.pushButton_calHorizontalStartRangeSelection = QPushButton(self.groupBox)
        self.pushButton_calHorizontalStartRangeSelection.setObjectName(u"pushButton_calHorizontalStartRangeSelection")
        sizePolicy3.setHeightForWidth(self.pushButton_calHorizontalStartRangeSelection.sizePolicy().hasHeightForWidth())
        self.pushButton_calHorizontalStartRangeSelection.setSizePolicy(sizePolicy3)

        self.verticalLayout_12.addWidget(self.pushButton_calHorizontalStartRangeSelection)

        self.label_calibrateRange = QLabel(self.groupBox)
        self.label_calibrateRange.setObjectName(u"label_calibrateRange")

        self.verticalLayout_12.addWidget(self.label_calibrateRange)

        self.pushButton_calHorizontalSetForwardLimit = QPushButton(self.groupBox)
        self.pushButton_calHorizontalSetForwardLimit.setObjectName(u"pushButton_calHorizontalSetForwardLimit")
        sizePolicy3.setHeightForWidth(self.pushButton_calHorizontalSetForwardLimit.sizePolicy().hasHeightForWidth())
        self.pushButton_calHorizontalSetForwardLimit.setSizePolicy(sizePolicy3)

        self.verticalLayout_12.addWidget(self.pushButton_calHorizontalSetForwardLimit)

        self.pushButton_calHorizontalSetBackwardLimit = QPushButton(self.groupBox)
        self.pushButton_calHorizontalSetBackwardLimit.setObjectName(u"pushButton_calHorizontalSetBackwardLimit")
        sizePolicy3.setHeightForWidth(self.pushButton_calHorizontalSetBackwardLimit.sizePolicy().hasHeightForWidth())
        self.pushButton_calHorizontalSetBackwardLimit.setSizePolicy(sizePolicy3)

        self.verticalLayout_12.addWidget(self.pushButton_calHorizontalSetBackwardLimit)


        self.gridLayout.addWidget(self.groupBox, 1, 1, 1, 1)


        self.verticalLayout_4.addLayout(self.gridLayout)

        self.verticalSpacer = QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.verticalLayout_4.addItem(self.verticalSpacer)

        self.tabControls.addTab(self.tabCalibration, "")
        self.tabFileManager = QWidget()
        self.tabFileManager.setObjectName(u"tabFileManager")
        self.verticalLayout_48 = QVBoxLayout(self.tabFileManager)
        self.verticalLayout_48.setObjectName(u"verticalLayout_48")
        self.groupBox_16 = QGroupBox(self.tabFileManager)
        self.groupBox_16.setObjectName(u"groupBox_16")
        self.verticalLayout_10 = QVBoxLayout(self.groupBox_16)
        self.verticalLayout_10.setObjectName(u"verticalLayout_10")
        self.horizontalLayout_74 = QHBoxLayout()
        self.horizontalLayout_74.setObjectName(u"horizontalLayout_74")
        self.pushButton_selectFile = QPushButton(self.groupBox_16)
        self.pushButton_selectFile.setObjectName(u"pushButton_selectFile")
        sizePolicy2.setHeightForWidth(self.pushButton_selectFile.sizePolicy().hasHeightForWidth())
        self.pushButton_selectFile.setSizePolicy(sizePolicy2)

        self.horizontalLayout_74.addWidget(self.pushButton_selectFile)

        self.label_37 = QLabel(self.groupBox_16)
        self.label_37.setObjectName(u"label_37")
        sizePolicy2.setHeightForWidth(self.label_37.sizePolicy().hasHeightForWidth())
        self.label_37.setSizePolicy(sizePolicy2)

        self.horizontalLayout_74.addWidget(self.label_37)

        self.label_currentFileDirectory = QLabel(self.groupBox_16)
        self.label_currentFileDirectory.setObjectName(u"label_currentFileDirectory")
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
        sizePolicy.setHeightForWidth(self.listWidget_fileDatasets.sizePolicy().hasHeightForWidth())
        self.listWidget_fileDatasets.setSizePolicy(sizePolicy)
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
        sizePolicy2.setHeightForWidth(self.label_40.sizePolicy().hasHeightForWidth())
        self.label_40.setSizePolicy(sizePolicy2)

        self.horizontalLayout_76.addWidget(self.label_40)

        self.label_currentDataset = QLabel(self.layoutWidget1)
        self.label_currentDataset.setObjectName(u"label_currentDataset")
        sizePolicy3.setHeightForWidth(self.label_currentDataset.sizePolicy().hasHeightForWidth())
        self.label_currentDataset.setSizePolicy(sizePolicy3)

        self.horizontalLayout_76.addWidget(self.label_currentDataset)


        self.verticalLayout_51.addLayout(self.horizontalLayout_76)

        self.tableWidget_fileAttributes = QTableWidget(self.layoutWidget1)
        self.tableWidget_fileAttributes.setObjectName(u"tableWidget_fileAttributes")
        sizePolicy.setHeightForWidth(self.tableWidget_fileAttributes.sizePolicy().hasHeightForWidth())
        self.tableWidget_fileAttributes.setSizePolicy(sizePolicy)

        self.verticalLayout_51.addWidget(self.tableWidget_fileAttributes)

        self.splitter_3.addWidget(self.layoutWidget1)

        self.verticalLayout_10.addWidget(self.splitter_3)


        self.verticalLayout_48.addWidget(self.groupBox_16)

        self.tabControls.addTab(self.tabFileManager, "")
        self.tabStatus = QWidget()
        self.tabStatus.setObjectName(u"tabStatus")
        self.verticalLayout_16 = QVBoxLayout(self.tabStatus)
        self.verticalLayout_16.setObjectName(u"verticalLayout_16")
        self.gridLayout_19 = QGridLayout()
        self.gridLayout_19.setObjectName(u"gridLayout_19")

        self.verticalLayout_16.addLayout(self.gridLayout_19)

        self.tabControls.addTab(self.tabStatus, "")

        self.verticalLayout_3.addWidget(self.tabControls)

        self.horizontalLayout_5 = QHBoxLayout()
        self.horizontalLayout_5.setObjectName(u"horizontalLayout_5")
        self.verticalLayout_52 = QVBoxLayout()
        self.verticalLayout_52.setObjectName(u"verticalLayout_52")
        self.verticalLayout_52.setSizeConstraint(QLayout.SetDefaultConstraint)
        self.groupBox_17 = QGroupBox(self.controlsPane)
        self.groupBox_17.setObjectName(u"groupBox_17")
        sizePolicy3.setHeightForWidth(self.groupBox_17.sizePolicy().hasHeightForWidth())
        self.groupBox_17.setSizePolicy(sizePolicy3)
        self.groupBox_17.setMinimumSize(QSize(0, 126))
        self.verticalLayout_53 = QVBoxLayout(self.groupBox_17)
        self.verticalLayout_53.setObjectName(u"verticalLayout_53")
        self.verticalLayout_15 = QVBoxLayout()
        self.verticalLayout_15.setObjectName(u"verticalLayout_15")
        self.pushButton_acqGetSingleImage = QPushButton(self.groupBox_17)
        self.pushButton_acqGetSingleImage.setObjectName(u"pushButton_acqGetSingleImage")
        sizePolicy7 = QSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        sizePolicy7.setHorizontalStretch(0)
        sizePolicy7.setVerticalStretch(0)
        sizePolicy7.setHeightForWidth(self.pushButton_acqGetSingleImage.sizePolicy().hasHeightForWidth())
        self.pushButton_acqGetSingleImage.setSizePolicy(sizePolicy7)

        self.verticalLayout_15.addWidget(self.pushButton_acqGetSingleImage)

        self.pushButton_acqStartLiveMode = QPushButton(self.groupBox_17)
        self.pushButton_acqStartLiveMode.setObjectName(u"pushButton_acqStartLiveMode")
        sizePolicy3.setHeightForWidth(self.pushButton_acqStartLiveMode.sizePolicy().hasHeightForWidth())
        self.pushButton_acqStartLiveMode.setSizePolicy(sizePolicy3)

        self.verticalLayout_15.addWidget(self.pushButton_acqStartLiveMode)

        self.verticalSpacer_13 = QSpacerItem(20, 1, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.verticalLayout_15.addItem(self.verticalSpacer_13)

        self.line_7 = QFrame(self.groupBox_17)
        self.line_7.setObjectName(u"line_7")
        self.line_7.setFrameShape(QFrame.Shape.HLine)
        self.line_7.setFrameShadow(QFrame.Shadow.Sunken)

        self.verticalLayout_15.addWidget(self.line_7)

        self.pushButton_acqStartPreviewMode = QPushButton(self.groupBox_17)
        self.pushButton_acqStartPreviewMode.setObjectName(u"pushButton_acqStartPreviewMode")
        sizePolicy3.setHeightForWidth(self.pushButton_acqStartPreviewMode.sizePolicy().hasHeightForWidth())
        self.pushButton_acqStartPreviewMode.setSizePolicy(sizePolicy3)

        self.verticalLayout_15.addWidget(self.pushButton_acqStartPreviewMode)


        self.verticalLayout_53.addLayout(self.verticalLayout_15)


        self.verticalLayout_52.addWidget(self.groupBox_17)

        self.verticalSpacer_10 = QSpacerItem(20, 1, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)

        self.verticalLayout_52.addItem(self.verticalSpacer_10)


        self.horizontalLayout_5.addLayout(self.verticalLayout_52)

        self.verticalLayout_57 = QVBoxLayout()
        self.verticalLayout_57.setObjectName(u"verticalLayout_57")
        self.verticalLayout_57.setSizeConstraint(QLayout.SetDefaultConstraint)
        self.groupBox_18 = QGroupBox(self.controlsPane)
        self.groupBox_18.setObjectName(u"groupBox_18")
        sizePolicy3.setHeightForWidth(self.groupBox_18.sizePolicy().hasHeightForWidth())
        self.groupBox_18.setSizePolicy(sizePolicy3)
        self.groupBox_18.setMinimumSize(QSize(0, 126))
        self.horizontalLayout_9 = QHBoxLayout(self.groupBox_18)
        self.horizontalLayout_9.setObjectName(u"horizontalLayout_9")
        self.verticalLayout_13 = QVBoxLayout()
        self.verticalLayout_13.setObjectName(u"verticalLayout_13")
        self.pushButton_acqStartStackMode = QPushButton(self.groupBox_18)
        self.pushButton_acqStartStackMode.setObjectName(u"pushButton_acqStartStackMode")
        sizePolicy7.setHeightForWidth(self.pushButton_acqStartStackMode.sizePolicy().hasHeightForWidth())
        self.pushButton_acqStartStackMode.setSizePolicy(sizePolicy7)

        self.verticalLayout_13.addWidget(self.pushButton_acqStartStackMode)

        self.horizontalLayout_89 = QHBoxLayout()
        self.horizontalLayout_89.setObjectName(u"horizontalLayout_89")
        self.horizontalLayout_89.setContentsMargins(0, -1, 0, -1)
        self.label_41 = QLabel(self.groupBox_18)
        self.label_41.setObjectName(u"label_41")
        sizePolicy8 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        sizePolicy8.setHorizontalStretch(0)
        sizePolicy8.setVerticalStretch(0)
        sizePolicy8.setHeightForWidth(self.label_41.sizePolicy().hasHeightForWidth())
        self.label_41.setSizePolicy(sizePolicy8)

        self.horizontalLayout_89.addWidget(self.label_41)

        self.label_acqNumberOfPlanes = QLabel(self.groupBox_18)
        self.label_acqNumberOfPlanes.setObjectName(u"label_acqNumberOfPlanes")
        sizePolicy9 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        sizePolicy9.setHorizontalStretch(0)
        sizePolicy9.setVerticalStretch(0)
        sizePolicy9.setHeightForWidth(self.label_acqNumberOfPlanes.sizePolicy().hasHeightForWidth())
        self.label_acqNumberOfPlanes.setSizePolicy(sizePolicy9)

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
        sizePolicy8.setHeightForWidth(self.label_84.sizePolicy().hasHeightForWidth())
        self.label_84.setSizePolicy(sizePolicy8)

        self.horizontalLayout_88.addWidget(self.label_84)

        self.doubleSpinBox_acqPlaneStepSize = QDoubleSpinBox(self.groupBox_18)
        self.doubleSpinBox_acqPlaneStepSize.setObjectName(u"doubleSpinBox_acqPlaneStepSize")
        sizePolicy9.setHeightForWidth(self.doubleSpinBox_acqPlaneStepSize.sizePolicy().hasHeightForWidth())
        self.doubleSpinBox_acqPlaneStepSize.setSizePolicy(sizePolicy9)
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
        sizePolicy9.setHeightForWidth(self.pushButton_acqSetFirstPlane.sizePolicy().hasHeightForWidth())
        self.pushButton_acqSetFirstPlane.setSizePolicy(sizePolicy9)

        self.horizontalLayout_90.addWidget(self.pushButton_acqSetFirstPlane)

        self.checkBox_acqFirstPlaneSet = QCheckBox(self.groupBox_18)
        self.checkBox_acqFirstPlaneSet.setObjectName(u"checkBox_acqFirstPlaneSet")
        sizePolicy2.setHeightForWidth(self.checkBox_acqFirstPlaneSet.sizePolicy().hasHeightForWidth())
        self.checkBox_acqFirstPlaneSet.setSizePolicy(sizePolicy2)

        self.horizontalLayout_90.addWidget(self.checkBox_acqFirstPlaneSet)


        self.verticalLayout_14.addLayout(self.horizontalLayout_90)

        self.horizontalLayout_91 = QHBoxLayout()
        self.horizontalLayout_91.setSpacing(6)
        self.horizontalLayout_91.setObjectName(u"horizontalLayout_91")
        self.pushButton_acqSetLastPlane = QPushButton(self.groupBox_18)
        self.pushButton_acqSetLastPlane.setObjectName(u"pushButton_acqSetLastPlane")
        sizePolicy9.setHeightForWidth(self.pushButton_acqSetLastPlane.sizePolicy().hasHeightForWidth())
        self.pushButton_acqSetLastPlane.setSizePolicy(sizePolicy9)

        self.horizontalLayout_91.addWidget(self.pushButton_acqSetLastPlane)

        self.checkBox_acqLastPlaneSet = QCheckBox(self.groupBox_18)
        self.checkBox_acqLastPlaneSet.setObjectName(u"checkBox_acqLastPlaneSet")
        sizePolicy2.setHeightForWidth(self.checkBox_acqLastPlaneSet.sizePolicy().hasHeightForWidth())
        self.checkBox_acqLastPlaneSet.setSizePolicy(sizePolicy2)

        self.horizontalLayout_91.addWidget(self.checkBox_acqLastPlaneSet)


        self.verticalLayout_14.addLayout(self.horizontalLayout_91)

        self.verticalSpacer_9 = QSpacerItem(20, 1, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.verticalLayout_14.addItem(self.verticalSpacer_9)


        self.horizontalLayout_9.addLayout(self.verticalLayout_14)


        self.verticalLayout_57.addWidget(self.groupBox_18)

        self.verticalSpacer_14 = QSpacerItem(20, 1, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)

        self.verticalLayout_57.addItem(self.verticalSpacer_14)


        self.horizontalLayout_5.addLayout(self.verticalLayout_57)

        self.verticalLayout_9 = QVBoxLayout()
        self.verticalLayout_9.setObjectName(u"verticalLayout_9")
        self.groupBox_4 = QGroupBox(self.controlsPane)
        self.groupBox_4.setObjectName(u"groupBox_4")
        sizePolicy3.setHeightForWidth(self.groupBox_4.sizePolicy().hasHeightForWidth())
        self.groupBox_4.setSizePolicy(sizePolicy3)
        self.groupBox_4.setMinimumSize(QSize(140, 126))
        self.verticalLayout_7 = QVBoxLayout(self.groupBox_4)
        self.verticalLayout_7.setObjectName(u"verticalLayout_7")
        self.verticalLayout_17 = QVBoxLayout()
        self.verticalLayout_17.setObjectName(u"verticalLayout_17")
        self.pushButton_laserOneToggle = QPushButton(self.groupBox_4)
        self.pushButton_laserOneToggle.setObjectName(u"pushButton_laserOneToggle")
        sizePolicy3.setHeightForWidth(self.pushButton_laserOneToggle.sizePolicy().hasHeightForWidth())
        self.pushButton_laserOneToggle.setSizePolicy(sizePolicy3)

        self.verticalLayout_17.addWidget(self.pushButton_laserOneToggle)

        self.pushButton_laserTwoToggle = QPushButton(self.groupBox_4)
        self.pushButton_laserTwoToggle.setObjectName(u"pushButton_laserTwoToggle")
        sizePolicy3.setHeightForWidth(self.pushButton_laserTwoToggle.sizePolicy().hasHeightForWidth())
        self.pushButton_laserTwoToggle.setSizePolicy(sizePolicy3)

        self.verticalLayout_17.addWidget(self.pushButton_laserTwoToggle)

        self.verticalSpacer_12 = QSpacerItem(20, 1, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.verticalLayout_17.addItem(self.verticalSpacer_12)


        self.verticalLayout_7.addLayout(self.verticalLayout_17)


        self.verticalLayout_9.addWidget(self.groupBox_4)

        self.verticalSpacer_11 = QSpacerItem(20, 1, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)

        self.verticalLayout_9.addItem(self.verticalSpacer_11)


        self.horizontalLayout_5.addLayout(self.verticalLayout_9)

        self.horizontalLayout_5.setStretch(0, 2)
        self.horizontalLayout_5.setStretch(1, 4)
        self.horizontalLayout_5.setStretch(2, 1)

        self.verticalLayout_3.addLayout(self.horizontalLayout_5)

        self.horizontalLayout_7 = QHBoxLayout()
        self.horizontalLayout_7.setObjectName(u"horizontalLayout_7")
        self.groupBox_5 = QGroupBox(self.controlsPane)
        self.groupBox_5.setObjectName(u"groupBox_5")
        self.horizontalLayout_8 = QHBoxLayout(self.groupBox_5)
        self.horizontalLayout_8.setObjectName(u"horizontalLayout_8")
        self.verticalLayout_8 = QVBoxLayout()
        self.verticalLayout_8.setObjectName(u"verticalLayout_8")
        self.horizontalLayout_92 = QHBoxLayout()
        self.horizontalLayout_92.setObjectName(u"horizontalLayout_92")
        self.pushButton_saveSelectDirectory = QPushButton(self.groupBox_5)
        self.pushButton_saveSelectDirectory.setObjectName(u"pushButton_saveSelectDirectory")
        sizePolicy2.setHeightForWidth(self.pushButton_saveSelectDirectory.sizePolicy().hasHeightForWidth())
        self.pushButton_saveSelectDirectory.setSizePolicy(sizePolicy2)

        self.horizontalLayout_92.addWidget(self.pushButton_saveSelectDirectory)

        self.horizontalSpacer_2 = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayout_92.addItem(self.horizontalSpacer_2)

        self.pushButton_saveCurrentImage = QPushButton(self.groupBox_5)
        self.pushButton_saveCurrentImage.setObjectName(u"pushButton_saveCurrentImage")
        sizePolicy7.setHeightForWidth(self.pushButton_saveCurrentImage.sizePolicy().hasHeightForWidth())
        self.pushButton_saveCurrentImage.setSizePolicy(sizePolicy7)

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
        self.label_7 = QLabel(self.groupBox_5)
        self.label_7.setObjectName(u"label_7")

        self.verticalLayout_11.addWidget(self.label_7)

        self.checkBox_saveStitch = QCheckBox(self.groupBox_5)
        self.checkBox_saveStitch.setObjectName(u"checkBox_saveStitch")
        sizePolicy8.setHeightForWidth(self.checkBox_saveStitch.sizePolicy().hasHeightForWidth())
        self.checkBox_saveStitch.setSizePolicy(sizePolicy8)
        self.checkBox_saveStitch.setChecked(True)

        self.verticalLayout_11.addWidget(self.checkBox_saveStitch)

        self.checkBox_saveStitchBlend = QCheckBox(self.groupBox_5)
        self.checkBox_saveStitchBlend.setObjectName(u"checkBox_saveStitchBlend")
        sizePolicy8.setHeightForWidth(self.checkBox_saveStitchBlend.sizePolicy().hasHeightForWidth())
        self.checkBox_saveStitchBlend.setSizePolicy(sizePolicy8)

        self.verticalLayout_11.addWidget(self.checkBox_saveStitchBlend)

        self.checkBox_saveAllCrop = QCheckBox(self.groupBox_5)
        self.checkBox_saveAllCrop.setObjectName(u"checkBox_saveAllCrop")
        sizePolicy8.setHeightForWidth(self.checkBox_saveAllCrop.sizePolicy().hasHeightForWidth())
        self.checkBox_saveAllCrop.setSizePolicy(sizePolicy8)

        self.verticalLayout_11.addWidget(self.checkBox_saveAllCrop)

        self.checkBox_saveAllFull = QCheckBox(self.groupBox_5)
        self.checkBox_saveAllFull.setObjectName(u"checkBox_saveAllFull")
        sizePolicy8.setHeightForWidth(self.checkBox_saveAllFull.sizePolicy().hasHeightForWidth())
        self.checkBox_saveAllFull.setSizePolicy(sizePolicy8)

        self.verticalLayout_11.addWidget(self.checkBox_saveAllFull)


        self.horizontalLayout_8.addLayout(self.verticalLayout_11)

        self.horizontalLayout_8.setStretch(0, 1)

        self.horizontalLayout_7.addWidget(self.groupBox_5)


        self.verticalLayout_3.addLayout(self.horizontalLayout_7)

        self.verticalSpacer_4 = QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.verticalLayout_3.addItem(self.verticalSpacer_4)

        self.horizontalLayout_10 = QHBoxLayout()
        self.horizontalLayout_10.setObjectName(u"horizontalLayout_10")
        self.plainTextEdit_messageLog = QPlainTextEdit(self.controlsPane)
        self.plainTextEdit_messageLog.setObjectName(u"plainTextEdit_messageLog")
        sizePolicy1.setHeightForWidth(self.plainTextEdit_messageLog.sizePolicy().hasHeightForWidth())
        self.plainTextEdit_messageLog.setSizePolicy(sizePolicy1)
        self.plainTextEdit_messageLog.setMinimumSize(QSize(0, 80))
        self.plainTextEdit_messageLog.setMaximumSize(QSize(16777215, 80))
        self.plainTextEdit_messageLog.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.plainTextEdit_messageLog.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.plainTextEdit_messageLog.setReadOnly(True)
        self.plainTextEdit_messageLog.setTextInteractionFlags(Qt.NoTextInteraction)

        self.horizontalLayout_10.addWidget(self.plainTextEdit_messageLog)


        self.verticalLayout_3.addLayout(self.horizontalLayout_10)

        self.splitter.addWidget(self.controlsPane)

        self.horizontalLayout_3.addWidget(self.splitter)

        Controller.setCentralWidget(self.centralwidget)
        self.menubar = QMenuBar(Controller)
        self.menubar.setObjectName(u"menubar")
        self.menubar.setGeometry(QRect(0, 0, 1479, 21))
        self.menuDisplay = QMenu(self.menubar)
        self.menuDisplay.setObjectName(u"menuDisplay")
        self.menu_Select_Theme = QMenu(self.menuDisplay)
        self.menu_Select_Theme.setObjectName(u"menu_Select_Theme")
        self.menuHelp = QMenu(self.menubar)
        self.menuHelp.setObjectName(u"menuHelp")
        self.menuFile = QMenu(self.menubar)
        self.menuFile.setObjectName(u"menuFile")
        Controller.setMenuBar(self.menubar)
        self.statusbar = QStatusBar(Controller)
        self.statusbar.setObjectName(u"statusbar")
        Controller.setStatusBar(self.statusbar)

        self.menubar.addAction(self.menuFile.menuAction())
        self.menubar.addAction(self.menuDisplay.menuAction())
        self.menubar.addAction(self.menuHelp.menuAction())
        self.menuDisplay.addAction(self.menu_Select_Theme.menuAction())
        self.menuDisplay.addAction(self.action_ShowHideImagesPane)
        self.menuDisplay.addAction(self.action_ShowHideControlsPane)
        self.menuDisplay.addAction(self.action_ShowHideMessageLog)
        self.menu_Select_Theme.addAction(self.action_lightTheme)
        self.menu_Select_Theme.addAction(self.action_darkTheme)
        self.menuHelp.addAction(self.action_openDocumentation)
        self.menuHelp.addAction(self.action_showSystemProperties)
        self.menuFile.addAction(self.action_OpenFile)
        self.menuFile.addSeparator()
        self.menuFile.addAction(self.action_Exit)

        self.retranslateUi(Controller)

        self.tabControls.setCurrentIndex(1)


        QMetaObject.connectSlotsByName(Controller)
    # setupUi

    def retranslateUi(self, Controller):
        Controller.setWindowTitle(QCoreApplication.translate("Controller", u"MesoSPIM Controller", None))
        self.action_openDocumentation.setText(QCoreApplication.translate("Controller", u"Open Documentation", None))
#if QT_CONFIG(statustip)
        self.action_openDocumentation.setStatusTip(QCoreApplication.translate("Controller", u"Open PDF Documentation", None))
#endif // QT_CONFIG(statustip)
#if QT_CONFIG(shortcut)
        self.action_openDocumentation.setShortcut(QCoreApplication.translate("Controller", u"Ctrl+H", None))
#endif // QT_CONFIG(shortcut)
        self.action_ShowHideMessageLog.setText(QCoreApplication.translate("Controller", u"Show Message Log", None))
        self.action_showSystemProperties.setText(QCoreApplication.translate("Controller", u"Show System Properties", None))
        self.action_lightTheme.setText(QCoreApplication.translate("Controller", u"Light Theme", None))
        self.action_darkTheme.setText(QCoreApplication.translate("Controller", u"Dark Theme", None))
        self.action_ShowHideImagesPane.setText(QCoreApplication.translate("Controller", u"Show Images Pane", None))
        self.action_ShowHideControlsPane.setText(QCoreApplication.translate("Controller", u"Show Controls Pane", None))
        self.action_OpenFile.setText(QCoreApplication.translate("Controller", u"Open File...", None))
        self.action_Exit.setText(QCoreApplication.translate("Controller", u"Exit", None))
        self.label_1.setText(QCoreApplication.translate("Controller", u"Units:", None))
        self.groupBox_SampleMovement.setTitle(QCoreApplication.translate("Controller", u"Sample Movement", None))
        self.label_sampleCurrentHPosition.setText(QCoreApplication.translate("Controller", u"0", None))
        self.label_21.setText(QCoreApplication.translate("Controller", u"Current Horizontal Position:", None))
        self.label_22.setText(QCoreApplication.translate("Controller", u"Current Vertical Position:", None))
        self.label_sampleCurrentVPosition.setText(QCoreApplication.translate("Controller", u"0", None))
#if QT_CONFIG(tooltip)
        self.pushButton_sampleSetOrigin.setToolTip(QCoreApplication.translate("Controller", u"Set the current sample position as the origin", None))
#endif // QT_CONFIG(tooltip)
        self.pushButton_sampleSetOrigin.setText(QCoreApplication.translate("Controller", u"Set Origin", None))
#if QT_CONFIG(tooltip)
        self.pushButton_sampleStepForward.setToolTip(QCoreApplication.translate("Controller", u"Move the sample forward", None))
#endif // QT_CONFIG(tooltip)
        self.pushButton_sampleStepForward.setText(QCoreApplication.translate("Controller", u"Forward", None))
#if QT_CONFIG(shortcut)
        self.pushButton_sampleStepForward.setShortcut(QCoreApplication.translate("Controller", u"Ctrl+Right", None))
#endif // QT_CONFIG(shortcut)
#if QT_CONFIG(tooltip)
        self.pushButton_sampleGotoOrigin.setToolTip(QCoreApplication.translate("Controller", u"Move the sample to origin", None))
#endif // QT_CONFIG(tooltip)
        self.pushButton_sampleGotoOrigin.setText(QCoreApplication.translate("Controller", u"Origin", None))
#if QT_CONFIG(tooltip)
        self.pushButton_sampleStepUp.setToolTip(QCoreApplication.translate("Controller", u"Move the sample up", None))
#endif // QT_CONFIG(tooltip)
        self.pushButton_sampleStepUp.setText(QCoreApplication.translate("Controller", u"Up", None))
#if QT_CONFIG(shortcut)
        self.pushButton_sampleStepUp.setShortcut(QCoreApplication.translate("Controller", u"Ctrl+Up", None))
#endif // QT_CONFIG(shortcut)
#if QT_CONFIG(tooltip)
        self.pushButton_sampleStepBackward.setToolTip(QCoreApplication.translate("Controller", u"Move the sample backward", None))
#endif // QT_CONFIG(tooltip)
        self.pushButton_sampleStepBackward.setText(QCoreApplication.translate("Controller", u"Backward", None))
#if QT_CONFIG(shortcut)
        self.pushButton_sampleStepBackward.setShortcut(QCoreApplication.translate("Controller", u"Ctrl+Left", None))
#endif // QT_CONFIG(shortcut)
#if QT_CONFIG(tooltip)
        self.pushButton_sampleStepDown.setToolTip(QCoreApplication.translate("Controller", u"Move the sample down", None))
#endif // QT_CONFIG(tooltip)
        self.pushButton_sampleStepDown.setText(QCoreApplication.translate("Controller", u"Down", None))
        self.label_25.setText(QCoreApplication.translate("Controller", u"Horizontal Step:", None))
        self.doubleSpinBox_sampleHStepSize.setSuffix("")
        self.label_26.setText(QCoreApplication.translate("Controller", u"Vertical Step:", None))
        self.label_23.setText(QCoreApplication.translate("Controller", u"Horizontal Position:", None))
#if QT_CONFIG(tooltip)
        self.pushButton_sampleGotoHPosition.setToolTip(QCoreApplication.translate("Controller", u"Move the sample to the specified horizontal position", None))
#endif // QT_CONFIG(tooltip)
        self.pushButton_sampleGotoHPosition.setText(QCoreApplication.translate("Controller", u"Move Horizontal", None))
        self.label_24.setText(QCoreApplication.translate("Controller", u"Vertical Position:", None))
#if QT_CONFIG(tooltip)
        self.pushButton_sampleGotoVPosition.setToolTip(QCoreApplication.translate("Controller", u"Move the sample to the specified vertical position", None))
#endif // QT_CONFIG(tooltip)
        self.pushButton_sampleGotoVPosition.setText(QCoreApplication.translate("Controller", u"Move Vertical", None))
        self.groupBox_CameraMovement.setTitle(QCoreApplication.translate("Controller", u"Camera Movement", None))
        self.label_31.setText(QCoreApplication.translate("Controller", u"Current Camera Position:", None))
        self.label_cameraCurrentPosition.setText(QCoreApplication.translate("Controller", u"0", None))
        self.label.setText("")
        self.label_2.setText("")
#if QT_CONFIG(tooltip)
        self.pushButton_cameraSetFocus.setToolTip(QCoreApplication.translate("Controller", u"Set the current camera position as focus position", None))
#endif // QT_CONFIG(tooltip)
        self.pushButton_cameraSetFocus.setText(QCoreApplication.translate("Controller", u"Set Focus", None))
        self.pushButton_cameraStepForward.setText(QCoreApplication.translate("Controller", u"Forward", None))
        self.label_3.setText("")
        self.pushButton_cameraGotoFocus.setText(QCoreApplication.translate("Controller", u"Focus", None))
        self.pushButton_cameraStepBackward.setText(QCoreApplication.translate("Controller", u"Backward", None))
        self.label_4.setText("")
        self.label_33.setText(QCoreApplication.translate("Controller", u"Camera Step:", None))
        self.label_32.setText(QCoreApplication.translate("Controller", u"Camera Position:", None))
#if QT_CONFIG(tooltip)
        self.pushButton_cameraGotoPosition.setToolTip(QCoreApplication.translate("Controller", u"Move the camera to the specified position", None))
#endif // QT_CONFIG(tooltip)
        self.pushButton_cameraGotoPosition.setText(QCoreApplication.translate("Controller", u"Move Camera", None))
        self.label_5.setText("")
        self.tabControls.setTabText(self.tabControls.indexOf(self.tabMotion), QCoreApplication.translate("Controller", u"Motion Control", None))
#if QT_CONFIG(tooltip)
        self.pushButton_resetSettings.setToolTip(QCoreApplication.translate("Controller", u"Return all parameters to their default value", None))
#endif // QT_CONFIG(tooltip)
        self.pushButton_resetSettings.setText(QCoreApplication.translate("Controller", u"Reset Settings", None))
        self.groupBox_13.setTitle(QCoreApplication.translate("Controller", u"ETLs Settings", None))
        self.label_76.setText(QCoreApplication.translate("Controller", u"<html><head/><body><p><span style=\" font-weight:600;\">Left ETL</span></p></body></html>", None))
        self.label_78.setText(QCoreApplication.translate("Controller", u"Amplitude:", None))
        self.doubleSpinBox_etlLeftAmplitude.setSuffix(QCoreApplication.translate("Controller", u" V", None))
        self.label_79.setText(QCoreApplication.translate("Controller", u"Offset:", None))
        self.doubleSpinBox_etlLeftOffset.setSuffix(QCoreApplication.translate("Controller", u" V", None))
        self.label_80.setText(QCoreApplication.translate("Controller", u"<html><head/><body><p><span style=\" font-weight:600;\">Right ETL</span></p></body></html>", None))
        self.label_81.setText(QCoreApplication.translate("Controller", u"Amplitude:", None))
        self.doubleSpinBox_etlRightAmplitude.setSuffix(QCoreApplication.translate("Controller", u" V", None))
        self.label_82.setText(QCoreApplication.translate("Controller", u"Offset:", None))
        self.doubleSpinBox_etlRightOffset.setSuffix(QCoreApplication.translate("Controller", u" V", None))
        self.checkBox_etlSync.setText(QCoreApplication.translate("Controller", u"Sync Left/Right", None))
        self.checkBox_etlActivate.setText(QCoreApplication.translate("Controller", u"Activate ETLs", None))
        self.label_35.setText(QCoreApplication.translate("Controller", u"ETL Steps:", None))
        self.groupBox_12.setTitle(QCoreApplication.translate("Controller", u"Camera Settings", None))
        self.label_9.setText(QCoreApplication.translate("Controller", u"Shutter Mode:", None))
        self.label_doubleSpinBox_cameraExposureTime.setText(QCoreApplication.translate("Controller", u"Exposure Time:", None))
        self.doubleSpinBox_cameraExposureTime.setPrefix("")
        self.doubleSpinBox_cameraExposureTime.setSuffix(QCoreApplication.translate("Controller", u" ms", None))
        self.label_doubleSpinBox_cameraLineTime.setText(QCoreApplication.translate("Controller", u"Line Time:", None))
        self.doubleSpinBox_cameraLineTime.setSuffix(QCoreApplication.translate("Controller", u" \u03bcs", None))
        self.label_doubleSpinBox_cameraExposedLines.setText(QCoreApplication.translate("Controller", u"Exposed Lines:", None))
        self.label_doubleSpinBox_cameraDelayLines.setText(QCoreApplication.translate("Controller", u"Delay Lines:", None))
        self.groupBox_15.setTitle(QCoreApplication.translate("Controller", u"Lasers Settings", None))
        self.label_72.setText(QCoreApplication.translate("Controller", u"<html><head/><body><p><span style=\" font-weight:600;\">Laser1</span></p></body></html>", None))
        self.label_50.setText(QCoreApplication.translate("Controller", u"Power:", None))
        self.doubleSpinBox_laserOneAmplitude.setSuffix(QCoreApplication.translate("Controller", u" %", None))
        self.checkBox_laserOneAutomatic.setText(QCoreApplication.translate("Controller", u"Auto On/Off", None))
        self.label_73.setText(QCoreApplication.translate("Controller", u"<html><head/><body><p><span style=\" font-weight:600;\">Laser2</span></p></body></html>", None))
        self.label_74.setText(QCoreApplication.translate("Controller", u"Power:", None))
        self.doubleSpinBox_laserTwoAmplitude.setSuffix(QCoreApplication.translate("Controller", u" %", None))
        self.checkBox_laserTwoAutomatic.setText(QCoreApplication.translate("Controller", u"Auto On/Off", None))
        self.groupBox_11.setTitle(QCoreApplication.translate("Controller", u"Galvanometers Settings", None))
        self.label_69.setText(QCoreApplication.translate("Controller", u"<html><head/><body><p><span style=\" font-weight:600;\">Left Galvo</span></p></body></html>", None))
        self.label_61.setText(QCoreApplication.translate("Controller", u"Amplitude:", None))
        self.doubleSpinBox_galvoLeftAmplitude.setSuffix(QCoreApplication.translate("Controller", u" V", None))
        self.label_62.setText(QCoreApplication.translate("Controller", u"Offset:", None))
        self.doubleSpinBox_galvoLeftOffset.setSuffix(QCoreApplication.translate("Controller", u" V", None))
        self.label_70.setText(QCoreApplication.translate("Controller", u"<html><head/><body><p><span style=\" font-weight:600;\">Right Galvo</span></p></body></html>", None))
        self.label_65.setText(QCoreApplication.translate("Controller", u"Amplitude:", None))
        self.doubleSpinBox_galvoRightAmplitude.setSuffix(QCoreApplication.translate("Controller", u" V", None))
        self.label_66.setText(QCoreApplication.translate("Controller", u"Offset:", None))
        self.doubleSpinBox_galvoRightOffset.setSuffix(QCoreApplication.translate("Controller", u" V", None))
        self.checkBox_galvoSync.setText(QCoreApplication.translate("Controller", u"Sync Left/Right", None))
        self.checkBox_galvoActivate.setText(QCoreApplication.translate("Controller", u"Activate Galvanometers", None))
        self.checkBox_galvoInvert.setText(QCoreApplication.translate("Controller", u"Invert scan", None))
        self.tabControls.setTabText(self.tabControls.indexOf(self.tabSettings), QCoreApplication.translate("Controller", u"Scan Settings", None))
        self.groupBox_2.setTitle(QCoreApplication.translate("Controller", u"Camera Focus Calibration", None))
        self.label_28.setText(QCoreApplication.translate("Controller", u"Number of planes for calibration:", None))
        self.doubleSpinBox_calNumberOfPlanes.setSuffix(QCoreApplication.translate("Controller", u" planes", None))
        self.label_43.setText(QCoreApplication.translate("Controller", u"Number of camera positions:", None))
        self.doubleSpinBox_calNumberOfCameraPositions.setSuffix(QCoreApplication.translate("Controller", u" planes", None))
#if QT_CONFIG(tooltip)
        self.pushButton_calCameraStartCalibration.setToolTip(QCoreApplication.translate("Controller", u"Start camera calibration", None))
#endif // QT_CONFIG(tooltip)
        self.pushButton_calCameraStartCalibration.setText(QCoreApplication.translate("Controller", u"Start Camera Calibration", None))
#if QT_CONFIG(tooltip)
        self.pushButton_calCameraShowInterpolation.setToolTip(QCoreApplication.translate("Controller", u"Show the results of the last camera calibration", None))
#endif // QT_CONFIG(tooltip)
        self.pushButton_calCameraShowInterpolation.setText(QCoreApplication.translate("Controller", u"Show Camera Focus Interpolation", None))
#if QT_CONFIG(tooltip)
        self.pushButton_calCameraComputeFocus.setToolTip(QCoreApplication.translate("Controller", u"Calculate the camera position of focus", None))
#endif // QT_CONFIG(tooltip)
        self.pushButton_calCameraComputeFocus.setText(QCoreApplication.translate("Controller", u"Compute Camera Focus", None))
        self.groupBox_3.setTitle(QCoreApplication.translate("Controller", u"ETL Focus Calibration", None))
        self.label_47.setText(QCoreApplication.translate("Controller", u"Number of ETL voltages:", None))
        self.doubleSpinBox_calNumberOfEtlVoltages.setSuffix(QCoreApplication.translate("Controller", u" points", None))
#if QT_CONFIG(tooltip)
        self.pushButton_calEtlStartCalibration.setToolTip(QCoreApplication.translate("Controller", u"Start ETLs calibration", None))
#endif // QT_CONFIG(tooltip)
        self.pushButton_calEtlStartCalibration.setText(QCoreApplication.translate("Controller", u"Start ETL Calibration", None))
#if QT_CONFIG(tooltip)
        self.pushButton_calEtlShowInterpolation.setToolTip(QCoreApplication.translate("Controller", u"Show the results of the last ETLs calibration", None))
#endif // QT_CONFIG(tooltip)
        self.pushButton_calEtlShowInterpolation.setText(QCoreApplication.translate("Controller", u"Show ETL Focus Interpolation", None))
        self.groupBox.setTitle(QCoreApplication.translate("Controller", u"Horizontal Movement Calibration", None))
#if QT_CONFIG(tooltip)
        self.pushButton_calHorizontalStartRangeSelection.setToolTip(QCoreApplication.translate("Controller", u"Reset the horizontal boundaries of sample motion", None))
#endif // QT_CONFIG(tooltip)
        self.pushButton_calHorizontalStartRangeSelection.setText(QCoreApplication.translate("Controller", u"Start Horizontal Range Selection", None))
        self.label_calibrateRange.setText(QCoreApplication.translate("Controller", u"Press Calibrate Horizontal Range", None))
#if QT_CONFIG(tooltip)
        self.pushButton_calHorizontalSetForwardLimit.setToolTip(QCoreApplication.translate("Controller", u"Set the current horizontal position as the forward boundary", None))
#endif // QT_CONFIG(tooltip)
        self.pushButton_calHorizontalSetForwardLimit.setText(QCoreApplication.translate("Controller", u"Set Forward Limit", None))
#if QT_CONFIG(tooltip)
        self.pushButton_calHorizontalSetBackwardLimit.setToolTip(QCoreApplication.translate("Controller", u"Set the current horizontal position as the backward boundary", None))
#endif // QT_CONFIG(tooltip)
        self.pushButton_calHorizontalSetBackwardLimit.setText(QCoreApplication.translate("Controller", u"Set Backward Limit", None))
        self.tabControls.setTabText(self.tabControls.indexOf(self.tabCalibration), QCoreApplication.translate("Controller", u"Calibration", None))
        self.groupBox_16.setTitle(QCoreApplication.translate("Controller", u"Open File", None))
#if QT_CONFIG(tooltip)
        self.pushButton_selectFile.setToolTip(QCoreApplication.translate("Controller", u"Select a HDF5 file to open", None))
#endif // QT_CONFIG(tooltip)
        self.pushButton_selectFile.setText(QCoreApplication.translate("Controller", u"Select File", None))
        self.label_37.setText(QCoreApplication.translate("Controller", u"Current File:", None))
        self.label_currentFileDirectory.setText(QCoreApplication.translate("Controller", u"None Specified", None))
        self.label_38.setText(QCoreApplication.translate("Controller", u"File Datasets:", None))
#if QT_CONFIG(tooltip)
        self.pushButton_selectDataset.setToolTip(QCoreApplication.translate("Controller", u"Select and show the dataset(s) of the opened file", None))
#endif // QT_CONFIG(tooltip)
        self.pushButton_selectDataset.setText(QCoreApplication.translate("Controller", u"Select and Show Dataset(s)", None))
        self.label_39.setText(QCoreApplication.translate("Controller", u"Dataset Attributes:", None))
        self.label_40.setText(QCoreApplication.translate("Controller", u"Current Dataset:", None))
        self.label_currentDataset.setText(QCoreApplication.translate("Controller", u"None Specified", None))
        self.tabControls.setTabText(self.tabControls.indexOf(self.tabFileManager), QCoreApplication.translate("Controller", u"File Manager", None))
        self.tabControls.setTabText(self.tabControls.indexOf(self.tabStatus), QCoreApplication.translate("Controller", u"Status", None))
        self.groupBox_17.setTitle(QCoreApplication.translate("Controller", u"Manual Acquisition", None))
#if QT_CONFIG(tooltip)
        self.pushButton_acqGetSingleImage.setToolTip(QCoreApplication.translate("Controller", u"Start single image acquisition", None))
#endif // QT_CONFIG(tooltip)
        self.pushButton_acqGetSingleImage.setText(QCoreApplication.translate("Controller", u"Get Single Image", None))
#if QT_CONFIG(shortcut)
        self.pushButton_acqGetSingleImage.setShortcut(QCoreApplication.translate("Controller", u"Ctrl+I", None))
#endif // QT_CONFIG(shortcut)
#if QT_CONFIG(tooltip)
        self.pushButton_acqStartLiveMode.setToolTip(QCoreApplication.translate("Controller", u"Start live mode", None))
#endif // QT_CONFIG(tooltip)
        self.pushButton_acqStartLiveMode.setText(QCoreApplication.translate("Controller", u"Start Live Mode", None))
#if QT_CONFIG(shortcut)
        self.pushButton_acqStartLiveMode.setShortcut(QCoreApplication.translate("Controller", u"Ctrl+L", None))
#endif // QT_CONFIG(shortcut)
#if QT_CONFIG(tooltip)
        self.pushButton_acqStartPreviewMode.setToolTip(QCoreApplication.translate("Controller", u"Start preview mode", None))
#endif // QT_CONFIG(tooltip)
        self.pushButton_acqStartPreviewMode.setText(QCoreApplication.translate("Controller", u"Camera Preview Mode", None))
#if QT_CONFIG(shortcut)
        self.pushButton_acqStartPreviewMode.setShortcut(QCoreApplication.translate("Controller", u"Ctrl+P", None))
#endif // QT_CONFIG(shortcut)
        self.groupBox_18.setTitle(QCoreApplication.translate("Controller", u"Automatic Acquisition", None))
#if QT_CONFIG(tooltip)
        self.pushButton_acqStartStackMode.setToolTip(QCoreApplication.translate("Controller", u"Start multiple images acquisition", None))
#endif // QT_CONFIG(tooltip)
        self.pushButton_acqStartStackMode.setText(QCoreApplication.translate("Controller", u"Start Stack Mode", None))
#if QT_CONFIG(shortcut)
        self.pushButton_acqStartStackMode.setShortcut(QCoreApplication.translate("Controller", u"Ctrl+K", None))
#endif // QT_CONFIG(shortcut)
#if QT_CONFIG(tooltip)
        self.label_41.setToolTip(QCoreApplication.translate("Controller", u"Number of planes of stack acquisition", None))
#endif // QT_CONFIG(tooltip)
        self.label_41.setText(QCoreApplication.translate("Controller", u"Number Of Planes:", None))
        self.label_acqNumberOfPlanes.setText(QCoreApplication.translate("Controller", u"N/A", None))
#if QT_CONFIG(tooltip)
        self.label_84.setToolTip(QCoreApplication.translate("Controller", u"The plane step for stack acquisition", None))
#endif // QT_CONFIG(tooltip)
        self.label_84.setText(QCoreApplication.translate("Controller", u"Plane Step:", None))
        self.doubleSpinBox_acqPlaneStepSize.setSuffix(QCoreApplication.translate("Controller", u" \u03bcm", None))
#if QT_CONFIG(tooltip)
        self.pushButton_acqSetFirstPlane.setToolTip(QCoreApplication.translate("Controller", u"Set the current horizontal position as starting point for stack acquisition", None))
#endif // QT_CONFIG(tooltip)
        self.pushButton_acqSetFirstPlane.setText(QCoreApplication.translate("Controller", u"Set Starting Plane", None))
        self.checkBox_acqFirstPlaneSet.setText("")
#if QT_CONFIG(tooltip)
        self.pushButton_acqSetLastPlane.setToolTip(QCoreApplication.translate("Controller", u"Set the current horizontal position as ending point for stack acquisition", None))
#endif // QT_CONFIG(tooltip)
        self.pushButton_acqSetLastPlane.setText(QCoreApplication.translate("Controller", u"Set Ending Plane", None))
        self.checkBox_acqLastPlaneSet.setText("")
        self.groupBox_4.setTitle(QCoreApplication.translate("Controller", u"Lasers", None))
#if QT_CONFIG(tooltip)
        self.pushButton_laserOneToggle.setToolTip(QCoreApplication.translate("Controller", u"Activate left laser", None))
#endif // QT_CONFIG(tooltip)
        self.pushButton_laserOneToggle.setText(QCoreApplication.translate("Controller", u"Toggle Laser1", None))
#if QT_CONFIG(tooltip)
        self.pushButton_laserTwoToggle.setToolTip(QCoreApplication.translate("Controller", u"Activate right laser", None))
#endif // QT_CONFIG(tooltip)
        self.pushButton_laserTwoToggle.setText(QCoreApplication.translate("Controller", u"Toggle Laser2", None))
        self.groupBox_5.setTitle(QCoreApplication.translate("Controller", u"Save Settings", None))
#if QT_CONFIG(tooltip)
        self.pushButton_saveSelectDirectory.setToolTip(QCoreApplication.translate("Controller", u"Select a file directory for image saving", None))
#endif // QT_CONFIG(tooltip)
        self.pushButton_saveSelectDirectory.setText(QCoreApplication.translate("Controller", u"Select Save Directory", None))
#if QT_CONFIG(tooltip)
        self.pushButton_saveCurrentImage.setToolTip(QCoreApplication.translate("Controller", u"Save single image", None))
#endif // QT_CONFIG(tooltip)
        self.pushButton_saveCurrentImage.setText(QCoreApplication.translate("Controller", u"Save Current Image", None))
        self.lineEdit_saveDescription.setText("")
        self.lineEdit_saveFilename.setText("")
        self.label_45.setText(QCoreApplication.translate("Controller", u"Filename:", None))
        self.lineEdit_saveDirectory.setText("")
        self.label_8.setText(QCoreApplication.translate("Controller", u"Save Directory:", None))
        self.label_46.setText(QCoreApplication.translate("Controller", u"Description:", None))
        self.label_7.setText(QCoreApplication.translate("Controller", u"Save option (select one):", None))
        self.checkBox_saveStitch.setText(QCoreApplication.translate("Controller", u"Stitched - No blend", None))
        self.checkBox_saveStitchBlend.setText(QCoreApplication.translate("Controller", u"Stitched - Linear blend (20%)", None))
        self.checkBox_saveAllCrop.setText(QCoreApplication.translate("Controller", u"All frames - Cropped (20%)", None))
        self.checkBox_saveAllFull.setText(QCoreApplication.translate("Controller", u"All frames - Full", None))
        self.menuDisplay.setTitle(QCoreApplication.translate("Controller", u"View", None))
        self.menu_Select_Theme.setTitle(QCoreApplication.translate("Controller", u"Select Color Theme", None))
        self.menuHelp.setTitle(QCoreApplication.translate("Controller", u"Help", None))
        self.menuFile.setTitle(QCoreApplication.translate("Controller", u"File", None))
    # retranslateUi


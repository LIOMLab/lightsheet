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
from PySide6.QtWidgets import (QApplication, QDoubleSpinBox, QFrame, QGroupBox,
    QHBoxLayout, QLabel, QPushButton, QSizePolicy,
    QSpacerItem, QVBoxLayout, QWidget)

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
        sizePolicy2.setHeightForWidth(self.label_84.sizePolicy().hasHeightForWidth())
        self.label_84.setSizePolicy(sizePolicy2)

        self.horizontalLayout_88.addWidget(self.label_84)

        self.doubleSpinBox_acqPlaneStepSize = QDoubleSpinBox(self.groupBox_18)
        self.doubleSpinBox_acqPlaneStepSize.setObjectName(u"doubleSpinBox_acqPlaneStepSize")
        sizePolicy3.setHeightForWidth(self.doubleSpinBox_acqPlaneStepSize.sizePolicy().hasHeightForWidth())
        self.doubleSpinBox_acqPlaneStepSize.setSizePolicy(sizePolicy3)
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
        sizePolicy3.setHeightForWidth(self.pushButton_acqSetFirstPlane.sizePolicy().hasHeightForWidth())
        self.pushButton_acqSetFirstPlane.setSizePolicy(sizePolicy3)

        self.horizontalLayout_90.addWidget(self.pushButton_acqSetFirstPlane)

        self.doubleSpinBox_acqFirstPlane = QDoubleSpinBox(self.groupBox_18)
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

        self.horizontalLayout_91.addWidget(self.pushButton_acqSetLastPlane)

        self.doubleSpinBox_acqLastPlane = QDoubleSpinBox(self.groupBox_18)
        self.doubleSpinBox_acqLastPlane.setObjectName(u"doubleSpinBox_acqLastPlane")
        sizePolicy1.setHeightForWidth(self.doubleSpinBox_acqLastPlane.sizePolicy().hasHeightForWidth())
        self.doubleSpinBox_acqLastPlane.setSizePolicy(sizePolicy1)
        self.doubleSpinBox_acqLastPlane.setMinimumSize(QSize(120, 0))
        self.doubleSpinBox_acqLastPlane.setDecimals(2)
        self.doubleSpinBox_acqLastPlane.setMinimum(-100000.000000000000000)
        self.doubleSpinBox_acqLastPlane.setMaximum(100000.000000000000000)

        self.horizontalLayout_91.addWidget(self.doubleSpinBox_acqLastPlane)


        self.verticalLayout_14.addLayout(self.horizontalLayout_91)

        self.verticalSpacer_9 = QSpacerItem(20, 1, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.verticalLayout_14.addItem(self.verticalSpacer_9)


        self.horizontalLayout_9.addLayout(self.verticalLayout_14)


        self.verticalLayout_panel.addWidget(self.groupBox_18)


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
        self.doubleSpinBox_acqPlaneStepSize.setSuffix(QCoreApplication.translate("StackPanel", u" \u03bcm", None))
#if QT_CONFIG(tooltip)
        self.pushButton_acqSetFirstPlane.setToolTip(QCoreApplication.translate("StackPanel", u"Set the current horizontal position as starting point for stack acquisition", None))
#endif // QT_CONFIG(tooltip)
        self.pushButton_acqSetFirstPlane.setText(QCoreApplication.translate("StackPanel", u"Set Starting Plane", None))
        self.doubleSpinBox_acqFirstPlane.setSuffix(QCoreApplication.translate("StackPanel", u" \u03bcm", None))
#if QT_CONFIG(tooltip)
        self.pushButton_acqSetLastPlane.setToolTip(QCoreApplication.translate("StackPanel", u"Set the current horizontal position as ending point for stack acquisition", None))
#endif // QT_CONFIG(tooltip)
        self.pushButton_acqSetLastPlane.setText(QCoreApplication.translate("StackPanel", u"Set Ending Plane", None))
        self.doubleSpinBox_acqLastPlane.setSuffix(QCoreApplication.translate("StackPanel", u" \u03bcm", None))
        pass
    # retranslateUi


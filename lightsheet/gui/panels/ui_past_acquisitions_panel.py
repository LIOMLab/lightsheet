# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'ui_past_acquisitions_panel.ui'
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
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QHBoxLayout, QHeaderView,
    QLabel, QPushButton, QRadioButton, QSizePolicy,
    QSpacerItem, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget)
from lightsheet.gui.styles import spacing as _s

class Ui_PastAcquisitionsPanel(object):
    def setupUi(self, pastAcquisitionsPanel):
        if not pastAcquisitionsPanel.objectName():
            pastAcquisitionsPanel.setObjectName(u"pastAcquisitionsPanel")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(pastAcquisitionsPanel.sizePolicy().hasHeightForWidth())
        pastAcquisitionsPanel.setSizePolicy(sizePolicy)
        self.verticalLayout_pastPanel = QVBoxLayout(pastAcquisitionsPanel)
        self.verticalLayout_pastPanel.setObjectName(u"verticalLayout_pastPanel")
        self.horizontalLayout_pastViewRow = QHBoxLayout()
        self.horizontalLayout_pastViewRow.setObjectName(u"horizontalLayout_pastViewRow")
        self.label_pastView = QLabel(pastAcquisitionsPanel)
        self.label_pastView.setObjectName(u"label_pastView")

        self.horizontalLayout_pastViewRow.addWidget(self.label_pastView)

        self.radioButton_viewPlanned = QRadioButton(pastAcquisitionsPanel)
        self.radioButton_viewPlanned.setObjectName(u"radioButton_viewPlanned")

        self.horizontalLayout_pastViewRow.addWidget(self.radioButton_viewPlanned)

        self.radioButton_viewPast = QRadioButton(pastAcquisitionsPanel)
        self.radioButton_viewPast.setObjectName(u"radioButton_viewPast")
        self.radioButton_viewPast.setChecked(True)

        self.horizontalLayout_pastViewRow.addWidget(self.radioButton_viewPast)

        self.pushButton_refreshPast = QPushButton(pastAcquisitionsPanel)
        self.pushButton_refreshPast.setObjectName(u"pushButton_refreshPast")

        self.horizontalLayout_pastViewRow.addWidget(self.pushButton_refreshPast)

        self.horizontalSpacer_pastView = QSpacerItem(_s.XXL + _s.SM, _s.LG + _s.XS, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayout_pastViewRow.addItem(self.horizontalSpacer_pastView)


        self.verticalLayout_pastPanel.addLayout(self.horizontalLayout_pastViewRow)

        self.label_pastStatus = QLabel(pastAcquisitionsPanel)
        self.label_pastStatus.setObjectName(u"label_pastStatus")
        self.label_pastStatus.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_pastStatus.setWordWrap(True)

        self.verticalLayout_pastPanel.addWidget(self.label_pastStatus)

        self.tableWidget_pastAcquisitions = QTableWidget(pastAcquisitionsPanel)
        if (self.tableWidget_pastAcquisitions.columnCount() < 6):
            self.tableWidget_pastAcquisitions.setColumnCount(6)
        __qtablewidgetitem = QTableWidgetItem()
        self.tableWidget_pastAcquisitions.setHorizontalHeaderItem(0, __qtablewidgetitem)
        __qtablewidgetitem1 = QTableWidgetItem()
        self.tableWidget_pastAcquisitions.setHorizontalHeaderItem(1, __qtablewidgetitem1)
        __qtablewidgetitem2 = QTableWidgetItem()
        self.tableWidget_pastAcquisitions.setHorizontalHeaderItem(2, __qtablewidgetitem2)
        __qtablewidgetitem3 = QTableWidgetItem()
        self.tableWidget_pastAcquisitions.setHorizontalHeaderItem(3, __qtablewidgetitem3)
        __qtablewidgetitem4 = QTableWidgetItem()
        self.tableWidget_pastAcquisitions.setHorizontalHeaderItem(4, __qtablewidgetitem4)
        __qtablewidgetitem5 = QTableWidgetItem()
        self.tableWidget_pastAcquisitions.setHorizontalHeaderItem(5, __qtablewidgetitem5)
        self.tableWidget_pastAcquisitions.setObjectName(u"tableWidget_pastAcquisitions")
        self.tableWidget_pastAcquisitions.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tableWidget_pastAcquisitions.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tableWidget_pastAcquisitions.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tableWidget_pastAcquisitions.setWordWrap(False)
        self.tableWidget_pastAcquisitions.horizontalHeader().setStretchLastSection(True)

        self.verticalLayout_pastPanel.addWidget(self.tableWidget_pastAcquisitions)


        self.retranslateUi(pastAcquisitionsPanel)

        QMetaObject.connectSlotsByName(pastAcquisitionsPanel)
    # setupUi

    def retranslateUi(self, pastAcquisitionsPanel):
        self.label_pastView.setText(QCoreApplication.translate("PastAcquisitionsPanel", u"View:", None))
        self.radioButton_viewPlanned.setText(QCoreApplication.translate("PastAcquisitionsPanel", u"Planned", None))
#if QT_CONFIG(tooltip)
        self.radioButton_viewPlanned.setToolTip(QCoreApplication.translate("PastAcquisitionsPanel", u"Show the planned acquisition queue (switches to the Stack page).", None))
#endif // QT_CONFIG(tooltip)
        self.radioButton_viewPast.setText(QCoreApplication.translate("PastAcquisitionsPanel", u"Past", None))
#if QT_CONFIG(tooltip)
        self.radioButton_viewPast.setToolTip(QCoreApplication.translate("PastAcquisitionsPanel", u"Show past acquisitions saved in the save directory (read-only).", None))
#endif // QT_CONFIG(tooltip)
        self.pushButton_refreshPast.setText(QCoreApplication.translate("PastAcquisitionsPanel", u"Refresh", None))
#if QT_CONFIG(tooltip)
        self.pushButton_refreshPast.setToolTip(QCoreApplication.translate("PastAcquisitionsPanel", u"Re-scan the save directory for past acquisitions.", None))
#endif // QT_CONFIG(tooltip)
        self.label_pastStatus.setText("")
        ___qtablewidgetitem = self.tableWidget_pastAcquisitions.horizontalHeaderItem(0)
        ___qtablewidgetitem.setText(QCoreApplication.translate("PastAcquisitionsPanel", u"Sample", None))
        ___qtablewidgetitem1 = self.tableWidget_pastAcquisitions.horizontalHeaderItem(1)
        ___qtablewidgetitem1.setText(QCoreApplication.translate("PastAcquisitionsPanel", u"Channel", None))
        ___qtablewidgetitem2 = self.tableWidget_pastAcquisitions.horizontalHeaderItem(2)
        ___qtablewidgetitem2.setText(QCoreApplication.translate("PastAcquisitionsPanel", u"#Planes", None))
        ___qtablewidgetitem3 = self.tableWidget_pastAcquisitions.horizontalHeaderItem(3)
        ___qtablewidgetitem3.setText(QCoreApplication.translate("PastAcquisitionsPanel", u"Size", None))
        ___qtablewidgetitem4 = self.tableWidget_pastAcquisitions.horizontalHeaderItem(4)
        ___qtablewidgetitem4.setText(QCoreApplication.translate("PastAcquisitionsPanel", u"Date", None))
        ___qtablewidgetitem5 = self.tableWidget_pastAcquisitions.horizontalHeaderItem(5)
        ___qtablewidgetitem5.setText(QCoreApplication.translate("PastAcquisitionsPanel", u"Format", None))
        pass
    # retranslateUi


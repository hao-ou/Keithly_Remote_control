import sys
import pyvisa
import random
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QLabel, QMessageBox, QProgressBar, \
    QFileDialog
from PyQt5.QtCore import QTimer
from PyQt5.uic import loadUi
from PyQt5 import QtWidgets, QtCore
import pyqtgraph as pg
import numpy as np
import time, os
from PyQt5.QtCore import QTimer
#from Output_parameta import *
#from InputVoltage import *
import time

rm = pyvisa.ResourceManager()

# A2612BデバイスのVISAアドレスを指定
source_address = "GPIB0::20::INSTR"  # ソース2614Bのアドレス
#gate_address = "GPIB0::23::INSTR"  # ゲートA2612Bのアドレス


# A2612Bデバイスを開く
Source = rm.open_resource(source_address)
#Gate = rm.open_resource(gate_address)
#Drain = rm.open_resource(source_address)

# Limit max current
Source.write("smua.source.limiti = 1e-4")
Source.write("smub.source.limiti = 1e-4")

def set_vd(voltage):
    Source.write("smua.source.levelv=%.2f"%voltage)

def set_vg(voltage):
    Source.write("smub.source.levelv=%.2f"%voltage)

def read_id():
    current = float(Source.query("print(smua.measure.i())"))
    return(current)

def read_ig():
    current = float(Source.query("print(smub.measure.i())"))
    return(current)

def read_vd():
    voltage = float(Source.query("print(smua.measure.v())"))
    return(voltage)

def read_vg():
    voltage = float(Source.query("print(smub.measure.v())"))
    return(voltage)

class MyApp(QMainWindow):
    def __init__(self):
        super(MyApp, self).__init__()
        loadUi('EL-TEST.ui', self)

        # Find the container widget in your UI (replace 'containerWidget' with the actual name)
        self.container_CurrentTime = self.findChild(QWidget, 'CurrentTime')
        self.container_CurrentVD = self.findChild(QWidget, 'CurrentVD')
        self.container_CurrentVG = self.findChild(QWidget, 'CurrentVG')
        self.container_LogCurrentVD = self.findChild(QWidget, 'LogCurrentVD')
        self.container_LogCurrentVG = self.findChild(QWidget, 'LogCurrentVG')
        self.start = self.findChild(QWidget, 'Start')
        self.stop = self.findChild(QWidget, 'Stop')
        self.setvd = self.findChild(QWidget, 'setVD')
        self.setvg = self.findChild(QWidget, 'setVG')
        self.sweep = self.findChild(QWidget, 'Sweep')
        self.changeVD = self.findChild(QWidget, 'InputSetVD')
        self.changeVG = self.findChild(QWidget, 'InputSetVG')
        self.FirstVD = self.findChild(QWidget, 'InputFirstVD')
        self.SecondVD = self.findChild(QWidget, 'InputSecondVD')
        self.Step = self.findChild(QWidget, 'Step')
        self.Wait = self.findChild(QWidget, 'WaitTime')
        self.display_VD = self.findChild(QLabel, 'Display_VDsweep')
        self.progress = self.findChild(QProgressBar, 'Progress')
        self.progress.reset()

        self.OpenFolder = self.findChild(QWidget, 'OpenFolder')
        self.FolderName = self.findChild(QWidget, 'InputFolderName')

        self.SaveFile = self.findChild(QWidget, 'Save')
        self.FileName = self.findChild(QWidget, 'InputFileName')

        # Initialize PyQtGraph PlotWidget
        self.plot_CurrentTime = pg.PlotWidget(self.container_CurrentTime)
        self.plot_CurrentVD = pg.PlotWidget(self.container_CurrentVD)
        self.plot_CurrentVG = pg.PlotWidget(self.container_CurrentVG)
        self.plot_LogCurrentVD = pg.PlotWidget(self.container_LogCurrentVD)
        self.plot_LogCurrentVG = pg.PlotWidget(self.container_LogCurrentVG)
        if not self.container_CurrentTime.layout():
            self.container_CurrentTime.setLayout(QVBoxLayout())
        if not self.container_CurrentVD.layout():
            self.container_CurrentVD.setLayout(QVBoxLayout())
        if not self.container_CurrentVG.layout():
            self.container_CurrentVG.setLayout(QVBoxLayout())
        if not self.container_LogCurrentVD.layout():
            self.container_LogCurrentVD.setLayout(QVBoxLayout())
        if not self.container_LogCurrentVG.layout():
            self.container_LogCurrentVG.setLayout(QVBoxLayout())
        # Add the PlotWidget to the layout of the container widget
        self.container_CurrentTime.layout().addWidget(self.plot_CurrentTime)
        self.container_CurrentVD.layout().addWidget(self.plot_CurrentVD)
        self.container_CurrentVG.layout().addWidget(self.plot_CurrentVG)
        self.container_LogCurrentVD.layout().addWidget(self.plot_LogCurrentVD)
        self.container_LogCurrentVG.layout().addWidget(self.plot_LogCurrentVG)
        self.plot_CurrentTime.addLegend()
        self.plot_CurrentVD.addLegend()
        self.plot_CurrentVG.addLegend()
        self.plot_LogCurrentVD.addLegend()
        self.plot_LogCurrentVG.addLegend()

        # Set up pushbuttons
        # start
        self.isStart = 0
        self.start.setCheckable(True)
        self.start.clicked.connect(self.clickStart)
        # stop
        self.stop.clicked.connect(self.clickStop)
        # change VD, vG
        self.setvd.clicked.connect(self.Set_VD)
        self.setvg.clicked.connect(self.Set_VG)
        # Sweep
        self.isSweeping = 0
        self.Sweep.clicked.connect(self.StartSweep)

        self.OpenFolder.clicked.connect(self.SelectFolder)
        self.SaveFile.clicked.connect(self.SaveTxt)
        self.timetick = 0

        ############################
        ## DEFINE PARAMETERS HERE ##
        ############################

        self.current_vd = read_vd()
        self.current_vg = read_vg()
        self.current_vg = 0
        self.current_vd = 0

        #inputVG(self.current_vg, Gate)
        set_vd(self.current_vd)
        set_vg(self.current_vg)

        self.timeint = 10
        self.x_data = [0]

        self.id_data = [read_id()]
        self.logid_data = [np.log10(np.abs(self.id_data[0]))]

        self.ig_data = [read_ig()]
        self.logig_data = [np.log10(np.abs(self.ig_data[0]))]

        #self.ig_data = [Output_GateCurrent(Gate)]
        #self.logig_data = [np.log10(np.abs(self.ig_data[0]))]

        self.vd_record = [self.current_vd]
        self.vg_record = [self.current_vg]

        ##############
        self.real_vd_data = [read_vd()]
        #self.real_vg_data = [Output_GateVoltage(Gate)]
        self.real_vg_data = [read_vg()]
        ##############

    def update_plot(self):

        # Generate random data
        x = self.x_data[-1] + 1
        this_id = read_id()
        this_logid = np.log10(np.abs(this_id))

        this_ig = read_ig()
        this_logig = np.log10(np.abs(this_ig))

        #this_ig = Output_GateCurrent(Gate)
        #this_logig = np.log10(np.abs(this_ig))
        ###
        #real_vg = Output_GateVoltage(Gate)
        real_vd = read_vd()
        ###
        real_vg = read_vg()
        # Append the data to the lists
        self.x_data.append(x)
        self.id_data.append(this_id)
        self.logid_data.append(this_logid)
        #self.is_data.append(this_is)
        #self.logis_data.append(this_logis)
        self.ig_data.append(this_ig)
        self.logig_data.append(this_logig)

        ####
        self.real_vd_data.append(real_vd)
        self.real_vg_data.append(real_vg)
        #self.real_vs_data.append(real_vs)
        ###

        # Plotting the data
        self.plot_CurrentTime.plot(np.array(self.x_data)*self.timeint/1000, self.id_data, pen='r', clear=True, name ="ID")
        #self.plot_CurrentTime.plot(np.array(self.x_data)*self.timeint/1000, self.is_data, pen='b',  name="IS")
        self.plot_CurrentTime.plot(np.array(self.x_data)*self.timeint/1000, self.ig_data, pen='w',  name="IG")

        
        time.sleep(0.3)
        #Source.timeout(1000)
        ########
        # File writing

        with open(self.fpath, "a+") as f:
            f.write(str(self.x_data[-2] / 10))
            f.write(",")
            f.write(str(self.current_vd))
            f.write(",")
            f.write(str(self.current_vg))
            f.write(",")
            ####
            f.write(str(self.real_vd_data[-1]))
            f.write(",")
            #f.write(str(self.real_vs_data[-1]))
            #f.write(",")
            f.write(str(self.real_vg_data[-1]))
            f.write(",")
            ####
            f.write(str(self.id_data[-1]))
            f.write(",")
            #f.write(str(self.is_data[-1]))
            #f.write(",")
            f.write(str(self.ig_data[-1]))
            f.write(",")
            f.write(str(self.current_vd/(self.id_data[-1]+1e-14)))

            f.write("\n")

    def voltagevessel(self):

        ## Write vd, vg
        vd = self.current_vd
        vg = self.current_vg

        self.vd_record.append(vd)
        self.vg_record.append(vg)
        # print(len(self.vd_record), len(self.y2_data))
        self.Display_VDsweep.setText(str(round(self.current_vd, 4)))
        # self.Display_VDsweep.setText(str(self.y_data[-1]))

        self.plot_CurrentVD.plot(self.vd_record, self.id_data, pen='r', clear=True, name ="ID")
        #self.plot_CurrentVD.plot(self.vd_record, self.is_data, pen='b',  name ="IS")
        self.plot_CurrentVD.plot(self.vd_record, self.ig_data, pen='w',  name ="IG")

        self.plot_CurrentVG.plot(self.vg_record, self.id_data, pen='r', clear=True, name ="ID")
        #self.plot_CurrentVG.plot(self.vg_record, self.is_data, pen='b',  name ="IS")
        self.plot_CurrentVG.plot(self.vg_record, self.ig_data, pen='w', name ="IG")

        #self.plot_LogCurrentVD.plot(self.vd_record, self.logid_data, pen='r', clear=True, name ="logID")
        #self.plot_LogCurrentVD.plot(self.vd_record, self.logis_data, pen='b',  name ="logIS")
        #self.plot_LogCurrentVD.plot(self.vd_record, self.logig_data, pen='w',  name ="logIG")

        #self.plot_LogCurrentVG.plot(self.vg_record, self.logid_data, pen='r', clear=True, name ="logID")
        #self.plot_LogCurrentVG.plot(self.vg_record, self.logis_data, pen='b',  name ="logIS")
        #self.plot_LogCurrentVG.plot(self.vg_record, self.logig_data, pen='w',  name ="logIG")

    def clickStart(self):
        sender = self.sender()
        Source.write("*CLS")

        if self.isStart == 0:
            self.start.setText("Measuring")
            self.isStart = self.start.isChecked()
            self.timer = QTimer(self)
            self.timer.timeout.connect(self.update_plot)
            self.timer.timeout.connect(self.voltagevessel)
            self.timer.start(self.timeint)  # Time is in milliseconds
            self.plot_CurrentTime.showGrid(True, True)

        if self.isStart == 0.5:
            self.isStart = self.start.isChecked()
            if os.path.exists(self.fpath):
                choice = self.show_file_warning_popup("Warning", "This file already exists \n Do you want to save it?")
                if choice == QMessageBox.Yes:
                    os.remove(self.fpath)
                    open(self.fpath, "a+").close()
                    self.timer = QTimer(self)
                    self.timer.timeout.connect(self.update_plot)
                    self.timer.timeout.connect(self.voltagevessel)
                    self.timer.start(self.timeint)  # Time is in milliseconds
                    self.plot_CurrentTime.showGrid(True, True)
                    # print(self.isStart)
                    self.x_data = [0]
                    self.id_data = [read_id()]
                    self.logid_data = [np.log10(np.abs(self.id_data[0]))]
                    self.ig_data = [read_ig()]
                    self.logig_data = [np.log10(np.abs(self.ig_data[0]))]
                    #self.ig_data = [Output_DrainCurrent(Gate)]
                    #self.logig_data = [np.log10(np.abs(self.ig_data[0]))]

                    self.vd_record = [0]
                    self.vg_record = [0]
                    self.start.setText("Measuring")
                if choice == QMessageBox.No:
                    self.isStart == 0

    def clickStop(self):
        sender = self.sender()
        if self.isStart == 1:
            if self.current_vd == 0 and self.current_vg == 0:
                self.start.setText("Start")
                self.start.setChecked(False)
                self.timer.stop()
                self.isStart = 0.5
                self.progress.reset()
                self.Sweep.setText("Go!")
                Source.close()
                rm.close()
            else:
                self.show_warning_popup("Warning", "Set VD to zero!")

    def Set_VD(self):
        sender = self.sender()
        if self.isStart == 1 and self.isSweeping == 0:
            text = self.changeVD.toPlainText()
            num = float(text)
            self.current_vd = num
            set_vd(self.current_vd)

            # print(num)
        if self.isStart == 0.5 and self.isSweeping == 0:
            text = self.changeVD.toPlainText()
            num = float(text)
            self.current_vd = num
            set_vd(self.current_vd)
    
    def Set_VG(self):
        sender = self.sender()
        if self.isStart == 1 and self.isSweeping == 0:
            text = self.changeVG.toPlainText()
            num = float(text)
            self.current_vg = num
            set_vg(self.current_vg)

            # print(num)
        if self.isStart == 0.5 and self.isSweeping == 0:
            text = self.changeVG.toPlainText()
            num = float(text)
            self.current_vg = num
            set_vg(self.current_vg)
    
    def StartSweep(self):
        sender = self.sender()

        self.firstVD, self.secondVD, self.step, self.wait = float(self.FirstVD.toPlainText()), float(
            self.SecondVD.toPlainText()), float(self.Step.toPlainText()), float(self.WaitTime.toPlainText())
        if self.isStart == 1 or self.isStart == 0.5:
            if self.current_vd == 0 and self.firstVD * self.secondVD < 0:
                self.isSweeping = 1
                self.Sweep.setText("Working")
                self.path1 = np.arange(0, self.firstVD + self.step, self.step)
                self.path2 = np.arange(self.firstVD, self.secondVD - self.step, -self.step)
                self.path3 = np.arange(self.secondVD, 0 + self.step, self.step)
                self.path = np.hstack((self.path1, self.path2))
                self.path = np.hstack((self.path, self.path3))
                self.progress.reset()
                self.progress.setRange(0, self.path.shape[0])
                self.timer2 = QTimer(self)
                self.timer2.timeout.connect(self.SweepVD)
                self.timer2.start(1000 * int(self.wait))

    def SweepVD(self):
        self.progress.setValue(self.timetick + 1)
        self.current_vd = self.path[self.timetick]
        set_vd(self.current_vd)
        self.timetick = self.timetick + 1
        # print(self.current_vd)
        if self.timetick == self.path.shape[0]:
            self.timer2.stop()
            self.current_vd = 0
            self.isSweeping = 0
            self.Sweep.setText("Sweep")


    def SelectFolder(self):
        self.filefolder = QFileDialog.getExistingDirectory(self, "Select Directory", './')
        self.FolderName.setText(self.filefolder)

    def SaveTxt(self):
        if self.isStart == 0 or self.isStart == 0.5:
            self.fname = self.FileName.toPlainText()
            self.fpath = str(self.filefolder) + '/' + str(self.fname) + '.txt'
            if os.path.exists(self.fpath):
                choice = self.show_file_warning_popup("Warning", "This file already exists \n Do you want to save it?")
                if choice == QMessageBox.Yes:
                    os.remove(self.fpath)
                    with open(self.fpath, "a+") as f:
                        f.write("Time[s],VD,VG,RealVD,RealVG,ID,IG,R2pp\n")
                if choice == QMessageBox.No:
                    self.fpath = None
            else:
                with open(self.fpath, "a+") as f:
                    f.write("Time[s],VD,VG,RealVD,RealVG,ID,IG,R2pp\n")

    def show_warning_popup(self, title, text):
        # Display a warning pop-up
        msg_box = QMessageBox()
        msg_box.setIcon(QMessageBox.Warning)
        msg_box.setWindowTitle(title)
        msg_box.setText(text)
        msg_box.exec_()

    def show_file_warning_popup(self, title, text):
        # Display a choice pop-up
        msg_box = QMessageBox()
        msg_box.setIcon(QMessageBox.Question)
        msg_box.setWindowTitle(title)
        msg_box.setText(text)
        msg_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        return msg_box.exec_()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MyApp()
    window.show()
    sys.exit(app.exec_())
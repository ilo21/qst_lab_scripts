"""
 Copyright (c) 2023 CSAN_LiU

 This program is free software: you can redistribute it and/or modify
 it under the terms of the GNU General Public License as published by
 the Free Software Foundation, either version 3 of the License, or
 (at your option) any later version.

 This program is distributed in the hope that it will be useful,
 but WITHOUT ANY WARRANTY; without even the implied warranty of
 MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 GNU General Public License for more details.

 You should have received a copy of the GNU General Public License
 along with this program.  If not, see <https://www.gnu.org/licenses/>.
 """

from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
import pandas as pd
import numpy as np
import random
import serial
import os
import sys
import time
import pygame
from datetime import datetime
import TcsControl_python3 as TCS

'''
    The program will apply thermal stimulus multiple times during the session. 
    The current duration of each stimulus is 1 second.
    Current design is that each time, the target temperature will appear on different area on the thermode.
    Graphical user interface allows to set the correct COM port of the device, 
    session information, target temperature and the baseline temperature.
    During the session, a marker will be send to the serial port of X device.
    The value of the marker will match the current area on the thermode, where the target temperature is applied.
'''

#########################################################
# CONSTANT PARAMETERS

COM_ACQKNOLEDGE = 'COM8'
COM_QST = 'COM5'
BAUDRATE = 9600

# Stimulus duration
TIME2APPLY_SEC = 1
# Wait time before next stimulus
MIN_INTERVAL = 8
MAX_INTERVAL = 12
INTERVAL_SEC = np.arange(MIN_INTERVAL,MAX_INTERVAL,0.5)
# Baseline temperature
BASELINE_TEMP = 32.0
# Temp to apply in C
TARGET_TEMP = 51.0
# For how long to keep applying stimulus
TOTAL_DURATION_SEC = 300


LOG_FOLDER = "_HEAT_LOGS"
SUBJECT_ID = "00"
SESSION = "00"
DURATIONS       = [TIME2APPLY_SEC]*5     # stimulation durations in s for the 5 zones
RAMP_SPEED      = [300.0]*5              # ramp up speed in °C/s for the 5 zones
RETURN_SPEED    = [300.0]*5              # ramp down speed in °C/s for the 5 zones
AREAS = [1,4,2,5,3]
BEGIN_MARKER = 11
END_MARKER = 22


########################################
# SETTINGS CLASS
######################################
class MySettingsWidget(QMainWindow):

    def __init__(self):
        super(MySettingsWidget, self).__init__()
        self.name = "Session Settings"
        self.app_width = 400
        self.app_height = 30
        self.setWindowTitle(self.name)
        # self.setWindowIcon(QtGui.QIcon(ICO))
        self.resize(self.app_width,self.app_height)

        # serial connections
        self.acq = None
        self.acq_connected = False
        self.qst = None
        self.qst_connected = False

        self.task_on = False

        # logging
        self.current_path = os.path.dirname(os.path.abspath(__file__))
        self.dump_path = os.path.join(self.current_path,LOG_FOLDER)

        # start index of available areas
        self.current_area_idx = 0

        # user input
        self.task_params_dict = {
                                    "subjectID":SUBJECT_ID,
                                    "session": SESSION,
                                    "target_temp":TARGET_TEMP,
                                    "baseline_temp":BASELINE_TEMP,
                                    "duration":TOTAL_DURATION_SEC,
                                    "com_acqknoledge":COM_ACQKNOLEDGE,
                                    "com_qst":COM_QST
                                }

        self.main_widget = QWidget()
        self.main_layout = QFormLayout()
        self.setCentralWidget(self.main_widget)       
        self.main_widget.setLayout(self.main_layout)
        self.participant_id_label = QLabel("Subject ID:")
        self.participant_id_text = QLineEdit(self.task_params_dict["subjectID"])
        self.main_layout.addRow(self.participant_id_label,self.participant_id_text)
        self.session_id_label = QLabel("Session")
        self.session_id_text = QLineEdit(self.task_params_dict["session"])
        self.main_layout.addRow(self.session_id_label,self.session_id_text)
        self.temperature_label = QLabel("Target temperature:")
        self.temperature_text = QLineEdit(str(self.task_params_dict["target_temp"]))
        self.main_layout.addRow(self.temperature_label,self.temperature_text)
        self.temperature_base_label = QLabel("Baseline temperature:")
        self.temperature_base_text = QLineEdit(str(self.task_params_dict["baseline_temp"]))
        self.main_layout.addRow(self.temperature_base_label,self.temperature_base_text)
        self.duration_label = QLabel("Total duartion (sec):")
        self.duration_text = QLineEdit(str(self.task_params_dict["duration"]))
        self.duration_text.setValidator(QIntValidator())
        self.main_layout.addRow(self.duration_label,self.duration_text)
        self.com_qst_label = QLabel("Qst COM Port:")
        self.com_qst_text = QLineEdit(self.task_params_dict["com_qst"])
        self.main_layout.addRow(self.com_qst_label,self.com_qst_text)
        self.com_acqk_label = QLabel("Acqknowledge COM Port:")
        self.com_acqk_text = QLineEdit(self.task_params_dict["com_acqknoledge"])
        self.main_layout.addRow(self.com_acqk_label,self.com_acqk_text)

        self.start_btn = QPushButton("Start")
        self.main_layout.addRow("",self.start_btn)
        self.stop_btn = QPushButton("Stop")
        self.main_layout.addRow("",self.stop_btn)

        self.start_btn.clicked.connect(self.read_user_input)
        self.stop_btn.clicked.connect(self.close_all)


    # define keypress events
    def keyPressEvent(self,event):
        # if enter is pressed start button clicked
        if event.key() == Qt.Key_Return:
            if self.start_btn.isEnabled():
                self.read_user_input()
            else:
                if self.stop_btn.isEnabled():
                    self.close_all()

    def read_user_input(self):
        if self.task_on == False:
            self.task_params_dict["subjectID"] = self.participant_id_text.text()
            self.task_params_dict["session"] = self.session_id_text.text()
            try:
                self.task_params_dict["target_temp"] = float(self.temperature_text.text())
            except:
                self.show_info_dialog("Wrong temperature")
                return
            try:
                self.task_params_dict["baseline_temp"] = float(self.temperature_base_text.text())
            except:
                self.show_info_dialog("Wrong temperature")
                return
            try:
                duration = int(self.duration_text.text())
                if duration <= (TIME2APPLY_SEC+MAX_INTERVAL+1):
                    msg = "Total duration has to be at least "+ str(TIME2APPLY_SEC+MAX_INTERVAL+1)+" sec."
                    self.show_info_dialog(msg)
                    return
                else:
                    self.task_params_dict["duration"] = duration
            except:
                self.show_info_dialog("Total duration has to be an integer.")
                return
            self.task_params_dict["com_qst"] = self.com_qst_text.text()
            self.task_params_dict["com_acqknoledge"] = self.com_acqk_text.text()
            self.task_on = True
            # reset area intex
            self.current_area_idx = 0
            self.start_task()

    def start_task(self):
        print(f"Your parameters: {self.task_params_dict}")
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        # create serial connections
        ###################################################################
        self.connect2acqknowledge()
        self.connect2qst()
        # if self.qst_connected == True:
        if self.qst_connected == True and self.acq_connected == True:
            print("Begin")
            self.configure_logging()
            pygame.init()
            self.begin_time = pygame.time.get_ticks()
            # log
            f = open(self.log_path, "a")
            f.write(str(self.begin_time)+","+datetime.now().strftime("%Y_%m_%d_%H_%M_%S")+","+str(BEGIN_MARKER)+"\n")
            f.close()
            # send begin marker to acqknowledge
            self.send_marker(BEGIN_MARKER)
            time.sleep(1)
            self.stimulate()
        else:
            self.show_info_dialog("One or both devices are not connected.")
        ###################################################################
        # pygame.init()
        # self.begin_time = pygame.time.get_ticks()
        # self.configure_logging()
        # f = open(self.log_path, "a")
        # f.write(str(self.begin_time)+","+datetime.now().strftime("%Y_%m_%d_%H_%M_%S")+","+str(BEGIN_MARKER)+"\n")
        # f.close()
        # self.stimulate()
        ###################################################################

    def stimulate(self):
        if self.task_on == True:
            # set temperatures
            # check if the time is right
            curr_dur = (pygame.time.get_ticks() - self.begin_time) / 1000
            if curr_dur < self.task_params_dict["duration"]: # if total duration is not over yet
                if self.current_area_idx >= len(AREAS):
                    self.current_area_idx = 0
                temps = [self.task_params_dict["baseline_temp"] for el in AREAS]
                current_area = AREAS[self.current_area_idx]
                temps[current_area-1] = self.task_params_dict["target_temp"] # current_area-1 (-1 because area index starts at 0)
                marker = current_area
                self.current_area_idx+=1
                curr_temp = self.task_params_dict["target_temp"]
                print(f"Current area: {marker}, Temperature: {curr_temp}")
                # log
                f = open(self.log_path, "a")
                f.write(str(pygame.time.get_ticks())+","+datetime.now().strftime("%Y_%m_%d_%H_%M_%S")+","+str(marker)+"\n")
                f.close()
                ###########################################
                # time.sleep(TIME2APPLY_SEC+0.25) # wait when not "really" applying stimulus
                #################################################################
                # send marker and begin stimulation
                self.send_marker(marker)
                self.qst.set_temperatures(temps)
                self.qst.stimulate()
                # log temperatures
                recordDuration =TIME2APPLY_SEC+0.25
                cpt = 0
                start_time = time.time()
                column_names = ["temp_1", "temp_2", "temp_3", "temp_4", "temp_5"]
                df = pd.DataFrame(columns = column_names)
                while True:
                    current_temperatures = self.qst.get_temperatures()
                    data = pd.DataFrame([current_temperatures], columns=column_names)
                    df = df.append(data)
                    current_time = time.time()
                    cpt = cpt + 1
                    elapsed_time = current_time - start_time
                    if elapsed_time > recordDuration:
                        break
                # save results to csv
                curr_time = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
                file_name = curr_time+".csv"
                temp_log_path = os.path.join(self.dump_path_subject_temp,file_name)
                df.to_csv(temp_log_path,index=False)
                #####################################################################
                # wait interval
                interval = random.choice(INTERVAL_SEC)
                # show current duration
                duration = (pygame.time.get_ticks() - self.begin_time)/1000
                print(f"Sec from session start: {duration}")
                print(f"Current interval: {interval}\n")
                QTimer.singleShot((interval-0.25)*1000, self.stimulate)

            else: # close connections
                self.close_all()
            
    def send_marker(self,marker):
        print(f"Sending marker: {marker}\n")
        #######################################
        arg = bytes(chr(marker), 'utf8','ignore')
        self.acq.write(arg)

    def configure_logging(self):
        try: 
            os.mkdir(self.dump_path)
        except:
            pass
        if not os.path.exists(self.dump_path):
            self.show_info_dialog("Your data could not be logged under default path.")
            sys.exit()
        try:
            # create subject sub folrder
            self.start_time = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
            subfolder_name = self.task_params_dict["subjectID"]+"_"+self.task_params_dict["session"]+"_"+self.start_time 
            self.dump_path_subject = os.path.join(self.dump_path,subfolder_name)
            os.mkdir(self.dump_path_subject)
        except:
            pass
        if not os.path.exists(self.dump_path_subject):
            self.show_info_dialog("Your data could not be logged under default subject path.")
            sys.exit()
        self.log_file_name = self.task_params_dict["subjectID"]+"_"+self.task_params_dict["session"]+"_"+self.start_time +".txt"
        self.log_path = os.path.join(self.dump_path_subject,self.log_file_name)
        f = open(self.log_path, "a")
        # write headers
        f.write("ms,year_month_day_hour_min_sec,marker"+"\n")
        f.close()
        try:
            # create subject temperature sub folrder
            subfolder_temp_name = self.task_params_dict["subjectID"]+"_"+self.task_params_dict["session"]+"_"+self.start_time+"_temperatures_"+str(self.task_params_dict["target_temp"])
            self.dump_path_subject_temp = os.path.join(self.dump_path_subject,subfolder_temp_name)
            os.mkdir(self.dump_path_subject_temp)
        except:
            pass
        if not os.path.exists(self.dump_path_subject_temp):
            self.show_info_dialog("Your data could not be logged under default subject temperatures path.")
            sys.exit()


    def connect2acqknowledge(self):
        try:
            self.acq = serial.Serial(self.task_params_dict["com_acqknoledge"] , baudrate= BAUDRATE, timeout = 2)
            self.acq_connected = True
        except:
            self.acq = None
            self.show_info_dialog("Could not connect to acqknowledge")

    def connect2qst(self):
        try:
            self.qst = TCS.TcsDevice(port=self.task_params_dict["com_qst"])
            # Quiet mode
            self.qst.set_quiet()
            self.qst_connected = True
            # send constant settings for the stimuli
            self.qst.set_baseline(self.task_params_dict["baseline_temp"])
            self.qst.set_durations(DURATIONS)
            self.qst.set_ramp_speed(RAMP_SPEED)
            self.qst.set_return_speed(RETURN_SPEED)
        except:
            self.acq = None
            self.show_info_dialog("Could not connect to Qst")

    def close_connections(self):
        try:
            self.acq.close()
            self.acq = None
        except:
            print("Acq already closed")
        try:
            self.qst.close()
            self.qst = None
        except:
            print("Qst already closed")

    def close_all(self):
        if self.task_on == True:
            # total time
            end_time = (pygame.time.get_ticks() - self.begin_time)/1000
            print(f"Total duration: {end_time} sec\n")
            # send end marker to acqknowledge
            try:
                self.send_marker(END_MARKER)
            except:
                print("End marker could not be sent")
            # log
            f = open(self.log_path, "a")
            f.write(str(pygame.time.get_ticks())+","+datetime.now().strftime("%Y_%m_%d_%H_%M_%S")+","+str(END_MARKER)+"\n")
            f.close()
            self.close_connections()
            print("The end")
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self.task_on = False
        
    # show info that only ins are streamed
    def show_info_dialog(self, text):
        msgBox = QMessageBox()
        msgBox.setText(text)
        msgBox.setWindowTitle("Info!")
        # msgBox.setWindowIcon(QtGui.QIcon(ICO))
        msgBox.setStandardButtons(QMessageBox.Ok)
        msgBox.exec()

    def closeEvent(self, event):  
        if self.acq != None or self.qst != None:
            self.close_connections() 
################### end MySettingsWidget class

################################################################
#                                                              #
# EXECUTE GUI FROM MAIN                                        #
#                                                              #
################################################################
if __name__ == "__main__":
    # Always start by initializing Qt (only once per application)
    app = QApplication([])
    main_widget = MySettingsWidget()
    main_widget.show()
    app.exec_()
   

    print('Done')
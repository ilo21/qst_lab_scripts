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
import random
import os
import sys
import time
from time import strftime
from datetime import datetime
import TcsControl_python3 as TCS

'''
    The program will apply thermal stimulus. 
    The temperature will be gradually increased by 1 degree C, 
    until the user responds that it is painful.
    Graphical user interface allows to set the correct COM port of the device, 
    session information, start temperature and the duration of stimulus.
    During the session, the user will be prompted to press Space Bar to start stimulation.
    After each stimulus, the user will have to respond y or n to the displayed question.
    Current design is that each time, the program will randomly choose one of the 5 areas on the thermode.
'''

#########################################################
# CONSTANT PARAMETERS

COM = 'COM5'

TIME2APPLY_SEC = 1
# First temp to apply in C
START_TEMP = 46
BASELINE_TEMP = 32
# How many degrees C to go up
STEP_UP = 1
MAX_TEMP = 60
LOG_FOLDER = "_HEAT_SIMPLE_THRESHOLD_LOGS"
INFO_LABEL = "Press Space Bar when ready"
WAIT_TEXT = "+"
QUESTION = "1 = low pain; 10 = unbearable pain\n\nWas this 4-6?\n\n\nPress Y for yes\nor N for no"

SUBJECT_ID = "00"
SESSION = "00"

# possible start values
ALL_TEMPS = [32,33,34,35,36,37,38,39,40,41,42,43,44,45,46,47,48,49,50,51,52,53,54,55,56,57,58,59,60]

RAMP_SPEED      = [300.0]*5              # ramp up speed in °C/s for the 5 zones
RETURN_SPEED    = [300.0]*5              # ramp down speed in °C/s for the 5 zones



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

        self.task_params_dict = {
                                    "subjectID":SUBJECT_ID,
                                    "session": SESSION,
                                    "start_temp":START_TEMP,
                                    "hold_time":TIME2APPLY_SEC,
                                    "com":COM
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

        self.start_label = QLabel("Start temperature")
        self.start_text = QLineEdit(str(self.task_params_dict["start_temp"]))
        self.main_layout.addRow(self.start_label,self.start_text)
        self.hold_label = QLabel("Hold time (sec)")
        self.hold_text = QLineEdit(str(self.task_params_dict["hold_time"]))
        self.main_layout.addRow(self.hold_label,self.hold_text)
        self.com_label = QLabel("Device COM Port")
        self.com_text = QLineEdit(self.task_params_dict["com"])
        self.main_layout.addRow(self.com_label,self.com_text)

        self.start_btn = QPushButton("Start")
        self.main_layout.addRow("",self.start_btn)

        self.start_btn.clicked.connect(self.read_user_input)


    # define keypress events
    def keyPressEvent(self,event):
        # if enter is pressed start button clicked
        if event.key() == Qt.Key_Return:
            self.read_user_input()

    def read_user_input(self):
        self.task_params_dict["subjectID"] = self.participant_id_text.text()
        self.task_params_dict["session"] = self.session_id_text.text()
        self.task_params_dict["com"] = self.com_text.text()
        self.hold_ok = False
        try:
            self.task_params_dict["hold_time"] = int(self.hold_text.text())
            self.task_params_dict["start_temp"] = int(self.start_text.text())
            if self.task_params_dict["start_temp"] not in ALL_TEMPS:
                self.show_info_dialog("Temperature not allowed. Unknown speed.\nTry intigers between "+str(ALL_TEMPS[0])+" degrees and "+str(ALL_TEMPS[-1])+" degrees.")
            else:
                self.hold_ok = True
        except:
            self.show_info_dialog("Only full seconds holding time.")
        if self.hold_ok == True:
            self.start_task()

    @pyqtSlot()
    def start_task(self):
        self.close()
        
        self.task_presentation = PresentationWidget(self.task_params_dict)
        self.task_presentation.showMaximized()
        # self.task_presentation.show()

    # show info that only ins are streamed
    def show_info_dialog(self, text):
        msgBox = QMessageBox()
        msgBox.setText(text)
        msgBox.setWindowTitle("Info!")
        # msgBox.setWindowIcon(QtGui.QIcon(ICO))
        msgBox.setStandardButtons(QMessageBox.Ok)
        msgBox.exec()
        
################### end MySettingsWidget class


########################################
# PRESENTATION CLASS
######################################

class PresentationWidget(QMainWindow):
  
    def __init__(self,params):
        super(PresentationWidget, self).__init__()
        self.name = "Task"
        self.app_width = 800
        self.app_height = 800
        self.setWindowTitle(self.name)
        self.resize(self.app_width,self.app_height)
        # changing the background color to black 
        self.setStyleSheet("background-color: black;") 

        # don't allow to answer right away
        self.ask_on = False
        # wait for space bar to start
        self.wait2start = True
        
        # set current temp Value to default 
        self.current_temp = params["start_temp"]

        self.subject_id = params["subjectID"]
        self.session = params["session"]
        self.com = params["com"]
        self.duration = params["hold_time"]
        self.time_stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # check if the com connection was possible or quit app
        # create thermode object
        try:
            self.thermode = TCS.TcsDevice(port=self.com)
        except:
            self.show_info_dialog("Could not connect to the device.\nCheck your device COM port")
            sys.exit()


        # configure logging
        self.current_path = os.path.dirname(os.path.abspath(__file__))
        self.dump_path = os.path.join(self.current_path,LOG_FOLDER)
        try: 
            os.mkdir(self.dump_path)
        except:
            pass
        if not os.path.exists(self.dump_path):
            self.show_info_dialog("Your data could not be logged under default path.")
            sys.exit()
        self.log_file_name = self.subject_id+"_"+self.session+"_"+datetime.now().strftime("%Y_%m_%d_%H_%M_%S")+".txt"
        self.log_path = os.path.join(self.dump_path,self.log_file_name)

        # log task settings
        f = open(self.log_path, "a")
        f.write("Subject ID: "+self.subject_id+"\n")
        f.write("Session: "+self.session+"\n")
        f.write("Date: "+self.time_stamp+"\n\n")
        f.close()

        # make big label
        self.big_label_stylesheet = "QLabel {margin: 30px;font-size: 50pt;color:white}"

        self.main_widget = QWidget()
        self.main_layout = QVBoxLayout()
        self.setCentralWidget(self.main_widget)
        self.main_widget.setLayout(self.main_layout)
        self.init_widget = QWidget()
        self.init_layout = QVBoxLayout()
        self.question_label = QLabel(INFO_LABEL)
        self.question_label.setAlignment(Qt.AlignCenter)
        self.init_layout.addWidget(self.question_label)
        self.init_widget.setLayout(self.init_layout)
        self.main_layout.addWidget(self.init_widget)
        self.init_widget.setStyleSheet(self.big_label_stylesheet)



    # define keypress events
    def keyPressEvent(self,event):
        if event.key() == Qt.Key_Space and self.wait2start == True:
            self.wait2start = False
            self.ask_on = True
            self.question_label.setText(WAIT_TEXT)
            QApplication.processEvents()
            self.apply_temp()
        elif event.key() == Qt.Key_N and self.ask_on == True:
            print("N")
            self.ask_on = False
            # log 
            f = open(self.log_path, "a")
            f.write("Temperature: " + str(self.current_temp)+"\n")
            f.write("Response: N\n")
            f.close()
            self.current_temp += STEP_UP
            if self.current_temp <= MAX_TEMP:
                self.question_label.setText(WAIT_TEXT)
                QApplication.processEvents()
                self.apply_temp()
            else:
                # log 
                f = open(self.log_path, "a")
                f.write("\nMax temp exceeded: " + str(self.current_temp)+"\n")
                f.close()
                self.question_label.setText("Thank you")
                QApplication.processEvents()
        elif event.key() == Qt.Key_Y and self.ask_on == True:
            print("Y")
            # log 
            f = open(self.log_path, "a")
            f.write("Temperature: " + str(self.current_temp)+"\n")
            f.write("Response: Y\n")
            f.close()
            # log 
            f = open(self.log_path, "a")
            f.write("\nThreshold: " + str(self.current_temp)+"\n")
            f.close()
            self.question_label.setText("Thank you")
            QApplication.processEvents()
            self.thermode.close()
            print("Closing QST connection")
        super(PresentationWidget, self).keyPressEvent(event)

    def apply_temp(self):
        # set temp
        temperatures = [BASELINE_TEMP,BASELINE_TEMP,BASELINE_TEMP,BASELINE_TEMP,BASELINE_TEMP]
        current_area_idx = random.choice([0,1,2,3,4])
        temperatures[current_area_idx] = self.current_temp
        durations    = [self.duration]*5     # stimulation durations in s for the 5 zones
        # send all settings for the stimuli
        self.thermode.set_baseline(BASELINE_TEMP)
        self.thermode.set_durations(durations)
        self.thermode.set_ramp_speed(RAMP_SPEED)
        self.thermode.set_return_speed(RETURN_SPEED)
        self.thermode.set_temperatures(temperatures)

        print("heating")
        print("current temp: ", self.current_temp)
        self.thermode.stimulate()  

        # record stimulation temperatures
        recordDuration = max(durations)+0.5
        start_time = time.time()
       
        while True:
            # current_temperatures = self.thermode.get_temperatures()
            current_time = time.time()
            elapsed_time = current_time - start_time
            if elapsed_time > recordDuration:
                self.ask_on = True
                break
        self.question_label.setText(QUESTION)
        QApplication.processEvents()

    # show info that only ins are streamed
    def show_info_dialog(self, text):
        msgBox = QMessageBox()
        msgBox.setText(text)
        msgBox.setWindowTitle("Info!")
        # msgBox.setWindowIcon(QtGui.QIcon(ICO))
        msgBox.setStandardButtons(QMessageBox.Ok)
        msgBox.exec()

    def closeEvent(self, event):  
        try:
            self.thermode.close()
            print("Closing QST connection")
        except:
            print("QST connection closed")
            



################### end PresentationWidget

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
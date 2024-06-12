"""
   Copyright 2022 InfAI (CC SES)

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.
"""

__all__ = ("Operator", )

from operator_lib.util import OperatorBase, logger, InitPhase, todatetime, timestamp_to_str
import os
import pandas as pd
from load import Load
from battery import Battery

from operator_lib.util import Config
class CustomConfig(Config):
    data_path = "/opt/data"
    init_phase_length: float = 2
    init_phase_level: str = "d"

    def __init__(self, d, **kwargs):
        super().__init__(d, **kwargs)

        if self.init_phase_length != '':
            self.init_phase_length = float(self.init_phase_length)
        else:
            self.init_phase_length = 2
        
        if self.init_phase_level == '':
            self.init_phase_level = 'd'

class Operator(OperatorBase):
    configType = CustomConfig

    def init(self,  *args, **kwargs):
        super().init(*args, **kwargs)
        self.data_path = self.config.data_path
        
        if not os.path.exists(self.data_path):
            os.mkdir(self.data_path)

        self.historic_data_available = None
        self.training_done = None

        self.load = Load()
        self.battery = Battery()

        self.init_phase_duration = pd.Timedelta(self.config.init_phase_length, self.config.init_phase_level)        
        self.init_phase_handler = InitPhase(self.data_path, self.init_phase_duration, self.first_data_time, self.produce)
        value = {
            "battery_power": 0,
            "timestamp": timestamp_to_str(pd.Timestamp.now())
        }
        self.init_phase_handler.send_first_init_msg(value) 

    def run(self, data, selector = None, device_id=None):
        current_timestamp = todatetime(data['Power_Time'])
        if current_timestamp < pd.Timestamp.now():
            self.historic_data_available = True
        if self.historic_data_available and current_timestamp < pd.Timestamp.now() and not self.training_done:
            # TODO: Implement start of clustering training here!
            self.training_done = True
        new_point = data['Power']
        logger.debug('Power: '+str(new_point)+'  '+'Power Time: '+ timestamp_to_str(current_timestamp))

        discharge, dc_power = self.load.discharge_check(self.battery)
        charge, c_power = self.load.charge_check()
    
        if discharge:
            real_dc_power = self.battery.discharge(dc_power)
            battery_power = -real_dc_power
        elif charge:
            real_c_power = self.battery.charge(c_power)
            battery_power = real_c_power
        self.load.track_high_seg()
        self.load.update_corrected_max(battery_power=battery_power)
        self.load.update_max()
        self.load.update_segments()

        init_value = {
            "battery_power": 0,
            "timestamp": timestamp_to_str(current_timestamp)
        }
        operator_is_init = self.init_phase_handler.operator_is_in_init_phase(current_timestamp)
        if operator_is_init:
            return self.init_phase_handler.generate_init_msg(current_timestamp, init_value)

        if self.init_phase_handler.init_phase_needs_to_be_reset():
            return self.init_phase_handler.reset_init_phase(init_value)
        
        return {"battery_power": battery_power, "timestamp": timestamp_to_str(current_timestamp), "initial_phase": ""}
        


    
from operator_lib.operator_lib import OperatorLib
if __name__ == "__main__":
    OperatorLib(Operator(), name="user-profile-operator", git_info_file='git_commit')
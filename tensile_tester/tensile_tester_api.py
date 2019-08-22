import time

import numpy as np
import pandas as pd

from arduino_board_collection.boards.sensor_boards.basic.hx711_board.board import HX711Module
from arduino_board_collection.boards.sensor_boards.force.tesile_test_board.tesile_test_board import (
    TensileTestBoard,
)
from arduino_controller.board_api import BoardApi, api_function, api_run_fuction


class TensileTesterApi(BoardApi):
    required_boards = [TensileTestBoard]
    move_sleep_time = 0.1
    STOP_AT_FORCE_BELOW_MAX = 0.2
    WOBBLE_STEP_DIST=0.2
    DEFAULT_ERROR = 0.01
    DEAULT_DELAY = 0.01
    PAUSE_DELAY = 0.1
    DEFAULT_MAX_SPEED = 0.1
    DEFAULT_WOBBLE_COUNT = 0

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.moving = False
        self.stress_strain=[]

    @api_function(visible=False,run_function=True)
    @api_run_fuction
    def run_test(self, offset, scale, maximum_force, maximum_strain, specimen_length, maximum_speed=DEFAULT_MAX_SPEED, move_back=True,
                 min_force=1, on_finish=None, minimum_find_wobble_count=DEFAULT_WOBBLE_COUNT,pause_positions=None):

        print("PP",pause_positions)
        if maximum_speed is None: maximum_speed = self.DEFAULT_MAX_SPEED
        if move_back is None: move_back = True
        if pause_positions is None: pause_positions = []
        if minimum_find_wobble_count is None: minimum_find_wobble_count = self.DEFAULT_WOBBLE_COUNT
        board: TensileTestBoard = self.linked_boards[0]
        pre = -1
        movement = pre * maximum_strain
        self.data_logger.clear_data()
        # store premeaure values
        pre_max_speed = board.stepper_max_speed
        pre_position = board.stepper_current_position
        pre_data_rate = board.data_rate
        pre_scale = board.scale

        # find start position
        board.scale = scale
        board.offset = offset
        board.data_rate = HX711Module.basic_board_module.data_rate.minimum

        board.stepper_max_speed = maximum_speed
        self.stress_strain=[]
        v = self.read_different_values(number=4, reject_outliers=2)
        minimum_find_wobble = self.WOBBLE_STEP_DIST
        while minimum_find_wobble_count > 0:
            while v > 0:
                self.move(-pre * minimum_find_wobble, blocking=True)
                v = self.read_different_values(number=4, reject_outliers=2)
            while v < 0:
                self.move(pre * minimum_find_wobble, blocking=True)
                v = self.read_different_values(number=4, reject_outliers=2)
            minimum_find_wobble = minimum_find_wobble / 2
            minimum_find_wobble_count -= 1
            if not self.running:
                break

        #self.tare(blocking=True)

        time.sleep(2* board.data_rate/1000)
        # set measure values
        board.stepper_current_position = 0


        # move to max
        self.move_to(movement, blocking=False)

        start_time = time.time()
        # while moving check values
        over_min_force = False
        break_points_over = 0
        force_points_over = 0
        pos_points_over = 0
        overmax = 5
        while self.running:
            pos = pre * board.stepper_current_position
            now = time.time() - start_time
            pos = pre * board.stepper_current_position
            force = board.value

            if self.pause:
                self.move_to(board.stepper_current_position, blocking=False)
            else:
                if len(pause_positions) > 0:
                    if pause_positions[0] < pos:
                        self.pause = True
                        self.move_to(board.stepper_current_position, blocking=False)#
                        try:
                            pause_positions = pause_positions[1:]
                        except:
                            pause_positions = []
                if board.target_position != movement:
                    self.move_to(movement, blocking=False)

            now = time.time() - start_time
            pos = pre * board.stepper_current_position
            force = board.value

            # stop if pos is to high
            print(break_points_over, pos_points_over, force_points_over)
            if abs(board.stepper_current_position - movement) < self.DEFAULT_ERROR:
                pos_points_over += 1
            else:
                pos_points_over = 0
            if pos_points_over > overmax:
                print("pos_points_over")
                break

            # stop if force is to high
            if abs(board.value) > maximum_force:
                force_points_over += 1
            else:
                force_points_over = 0
            if force_points_over > overmax:
                print("force_points_over")
                break
            # stop if specimen breaks
            if force > min_force:
                over_min_force = True
            if over_min_force:
                min_force = max(min_force,force*self.STOP_AT_FORCE_BELOW_MAX)
            if force < min_force and over_min_force:
                break_points_over += 1
            else:
                break_points_over = 0
            if break_points_over > overmax:
                print("break_points_over")
                break

            self.data_logger.add_datapoint(key="position", y=pos, x=now)
            self.data_logger.add_datapoint(key="force", y=force, x=now)
            self.stress_strain.append([pos / specimen_length,board.value])
            time.sleep(self.move_sleep_time)

        for i in range(int(2 / self.move_sleep_time)):
            now = time.time() - start_time
            self.data_logger.add_datapoint(key="position", y=pos, x=now)
            self.data_logger.add_datapoint(key="force", y=force, x=now)
            self.stress_strain.append([pos / specimen_length,board.value])
            time.sleep(self.move_sleep_time)
        # reset premeaure values and move back
        board.stepper_max_speed = pre_max_speed
        board.data_rate = pre_data_rate

        if on_finish is not None:
            on_finish(self.data_logger.get_data(),pd.DataFrame(self.stress_strain,columns=["strain","stress"]))

        if move_back:
            self.move_to(0, blocking=True)

        board.stepper_current_position = pre_position
        self.running = False
        return True

    def get_running_data(self):
        data = super().get_running_data()
        data["stress_strain"] = self.stress_strain
        return data
    @api_function(kwargs={"mm": dict(type="number", step=0.1, default=0)}, datalink='stepper_current_position')
    def set_position(self, mm, allowed_error=DEFAULT_ERROR):
        mm = float(mm)
        board: TensileTestBoard = self.linked_boards[0]
        board.stepper_current_position = mm
        return board.stepper_current_position

    @api_function(kwargs={"mm": dict(type="number", step=0.1, default=0)})
    def move(self, mm, allowed_error=DEFAULT_ERROR):
        self.logger.info("Move {} mm".format(mm))
        mm = float(mm)
        board: TensileTestBoard = self.linked_boards[0]
        # board.target_position = board.stepper_current_position + mm
        # time.sleep(1)
        # while abs(board.stepper_current_position - board.target_position) > allowed_error:
        #    time.sleep(0.1)
        return self.move_to(mm=board.stepper_current_position + mm, allowed_error=allowed_error, blocking=True)

    @api_function(kwargs={"mm": dict(type="number", step=0.1, default=0)})
    def move_to(self, mm, allowed_error=DEFAULT_ERROR):
        self.logger.info("Move to {} mm".format(mm))
        # allow other moves to finish
        if self.moving:
            self.moving = False
            time.sleep(3*self.move_sleep_time)
        self.moving = True
        mm = float(mm)
        board: TensileTestBoard = self.linked_boards[0]
        board.target_position = mm
        n = 0
        while abs(board.stepper_current_position - board.target_position) > allowed_error and self.moving:
            n += 1
            # resend every second in case of missunderstanding
            if n >= 10:
                board.target_position = mm
                n = 0
            time.sleep(self.move_sleep_time)
        self.moving = False
        return board.stepper_current_position

    @api_function(datalink='value')
    def tare(self):
        self.logger.info("Tare")
        board: TensileTestBoard = self.linked_boards[0]
        scale = board.scale
        offset = board.offset
        board.offset = scale * self.read_for_time(5, delay=board.data_rate / 1000, reject_outliers=1) + offset

    @api_function(visible=False)
    def calibrate(self, spring_rate, max_strain, points=10, allowed_error=DEFAULT_ERROR):
        if allowed_error is None: allowed_error = self.DEFAULT_ERROR
        if points is None: points = 10
        board: TensileTestBoard = self.linked_boards[0]

        # stop
        self.move(1, blocking=True)
        self.move(-1, blocking=True)
        time.sleep(1)
        startposition = board.stepper_current_position

        time.sleep(1)
        self.move(-max_strain / (points + 1), blocking=True)
        data = []
        preforce = self.read_for_time(2, delay=board.data_rate / 1000, reject_outliers=1)
        prepos = board.stepper_current_position
        for i in range(points):
            self.move(-max_strain / (points + 1), blocking=True)
            time.sleep(2)
            pos = board.stepper_current_position
            force = self.read_for_time(2, delay=board.data_rate / 1000, reject_outliers=2)
            data.append((board.scale * abs(force - preforce) / abs(pos - prepos)) / spring_rate)
            preforce = force
            prepos = pos

        self.move_to(startposition, blocking=True)
        self.move(1, blocking=True)
        self.move_to(startposition, blocking=True)
        data = np.array(data)
        print(data)
        clean_data = self.reject_outliers(data, recursive=True, m=2)
        print(clean_data)
        board.scale = np.mean(clean_data)

    def reject_outliers(self, data, recursive=True, m=np.inf):
        data = np.array(data)
        mean = np.mean(data)
        next_cleaned = data[abs(data - mean) < m * np.std(data)]
        next_mean = np.mean(next_cleaned)
        while len(next_cleaned) > 0 and next_mean != mean:
            data = next_cleaned
            mean = next_mean
            next_cleaned = data[abs(data - np.mean(data)) < m * np.std(data)]
            next_mean = np.mean(next_cleaned)
        return data

    def read_different_values(self, number=3, delay=DEAULT_DELAY, reject_outliers=np.inf):
        data = []
        board: TensileTestBoard = self.linked_boards[0]
        data.append(board.value)
        while len(data) < number:
            v = board.value
            if v != data[-1]:
                data.append(v)

        if len(data) == 0:
            return np.nan

        return np.mean(self.reject_outliers(data, m=reject_outliers))

    def read_for_time(self, measuring_time, delay=DEAULT_DELAY, reject_outliers=np.inf):
        data = []
        board: TensileTestBoard = self.linked_boards[0]
        t = time.time()
        while time.time() - t < measuring_time:
            data.append(board.value)
            time.sleep(delay)

        if len(data) == 0:
            return np.nan

        return np.mean(self.reject_outliers(data, m=reject_outliers))

#!/usr/bin/env python3


import argparse
from contextlib import contextmanager

import sdl2
import sdl2.ext
import struct
import binascii
import serial
import math
import datetime as dt
import pickle

from tqdm import tqdm
from collections import namedtuple
from enum import IntEnum

from bridge import InputStack, ControllerStateTime, controller_states
import bridge


# NOTE: SCREEN START IN 'GAMES & MORE' then goes to training, and the cursor is on the practice stage.

ser = serial.Serial('/dev/ttyUSB0', 115200, bytesize=serial.EIGHTBITS, parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE, timeout=None)


def message(lx=128, ly=128, rx=128, ry=128, *inputs):
    inputs = set(inputs)

    buttons = sum([(b in inputs) << n for n, b in enumerate(bridge.buttonmapping)])
    buttons |= (32767 if sdl2.SDL_CONTROLLER_AXIS_TRIGGERLEFT in inputs else 0) << 6
    buttons |= (32767 if sdl2.SDL_CONTROLLER_AXIS_TRIGGERRIGHT in inputs else 0) << 7

    hat = bridge.hatcodes[sum([(b in inputs) << n for n, b in enumerate(bridge.hatmapping)])]
    return struct.pack('>BHBBBB', hat, buttons, lx, ly, rx, ry)


class ContinuousAction:
    def __init__(self, title=None):

        self.elapsed_sec = 0
        self.actions = []
        self.actions.append(None)
        if title:
            self.actions.append('---' + '\n' + title.upper() + '\n' + '---')

    def hold(self, msg, secs):
        self.actions.append(ControllerStateTime(msg, self.elapsed_sec))
        self.actions.append(ControllerStateTime(message(), self.elapsed_sec + secs))
        self.elapsed_sec += secs
        return self

    def press(self, msg):
        self.actions.append(ControllerStateTime(msg, self.elapsed_sec))
        self.actions.append(ControllerStateTime(message(), self.elapsed_sec + 0.1))
        self.elapsed_sec += 0.05
        return self

    def wait(self, secs):
        self.elapsed_sec += secs
        return self

    def log(self, string):
        self.actions.append(string)
        return self

    def play(self):
        for m in self.actions:
            if isinstance(m, str):
                print('> ', m)
            else:
                yield m


class StageMode(IntEnum):
    STANDARD = 1
    BATTLEFIELD = 1
    FINAL_DESTINATION = 2


def menu_nav(row, col, stage_mode=StageMode.STANDARD):
    action = ContinuousAction(f"NAVIGATING TO STAGE: [{row}, {col}] in {stage_mode.name}")

    col_time = 0.232
    row_time = 0.21

    action.log("Go back one screen")
    action.hold(message(128, 128, 128, 128, sdl2.SDL_CONTROLLER_BUTTON_A), 3)
    action.wait(2)

    action.log("Forward one screen to reset the cursor to practice-stage")
    action.press(message(128, 128, 128, 128, sdl2.SDL_CONTROLLER_BUTTON_B))
    action.wait(3)

    action.log("navigate stage-select matrix")
    for _ in range(col):
        action.hold(message(255, 128), col_time)
        action.wait(0.1)
    for _ in range(row):
        action.hold(message(128, 255), row_time)
        action.wait(0.1)

    action.log("Choose stage mode")
    for _ in range(stage_mode):
        action.press(message(128, 128, 128, 128, sdl2.SDL_CONTROLLER_BUTTON_Y))
        action.wait(0.1)

    action.log("Done!")
    action.hold(message(128, 128, 128, 128, sdl2.SDL_CONTROLLER_BUTTON_B), 6)
    return action


def character_nav(row, col, reset_cursor=True):
    action = ContinuousAction(f"NAVIGATING TO CHARACTER: [{row}, {col}]")

    row_time = 0.49
    col_time = 0.27

    if reset_cursor:
        action.log("Go back one screen")
        action.hold(message(128, 128, 128, 128, sdl2.SDL_CONTROLLER_BUTTON_A), 3)
        action.wait(2)

        action.log("Forward one screen to reset the cursor to the center of player 1")
        action.press(message(128, 128, 128, 128, sdl2.SDL_CONTROLLER_BUTTON_B))
        action.wait(6)
    else:
        action.wait(1)

    action.log("navigate to Mario")
    action.hold(message(128, 0), 0.675)
    action.wait(0.2)
    action.hold(message(0, 128), col_time)
    action.wait(0.2)
    action.hold(message(0, 128), col_time)
    action.wait(0.2)

    action.log("Navigate character-select matrix")
    for _ in range(row):
        action.hold(message(128, 192), row_time)
        action.wait(0.2)
    if row == 5:
        action.log("Compensate for centered grid. Navigate to Ridley.")
        action.hold(message(255, 128), .32)
        action.wait(0.2)
    for _ in range(col):
        action.hold(message(255, 128), col_time)
        action.wait(0.2)

    action.press(message(128, 128, 128, 128, sdl2.SDL_CONTROLLER_BUTTON_B))
    action.hold(message(128, 128, 128, 128, sdl2.SDL_CONTROLLER_BUTTON_START), 6)
    action.hold(message(128, 128, 128, 128, sdl2.SDL_CONTROLLER_BUTTON_START), 6)

    return action


def play_file(file_path, playback_speed=1):
    yield None
    for timestamp in bridge.replay_states(file_path):
        yield ControllerStateTime(timestamp.message, timestamp.delta / playback_speed)


def play_actions(*args):
    input_stack = InputStack()
    for a in args[::-1]:
        input_stack.push(a)

    start_dttm = dt.datetime.now().timestamp()
    prev_msg_stamp = None
    while True:
        try:
            sdl2.ext.get_events()
            msg_stamp = next(input_stack)
            if msg_stamp is None:
                start_dttm = dt.datetime.now().timestamp()
                continue
            # This this input has aleady been entered, then don't spam the stack
            if prev_msg_stamp and msg_stamp.message == prev_msg_stamp.message:
                continue
            # Wait for the correct amount of time to pass before performing an input
            while True:
                elapsed_delta = dt.datetime.now().timestamp() - start_dttm
                if msg_stamp.delta < elapsed_delta:
                    break
            ser.write(msg_stamp.formatted_message())
            prev_msg_stamp = msg_stamp
        except StopIteration:
            break

        while True:
            # wait for the arduino to request another state.
            response = ser.read(1)
            if response == b'U':
                break
            elif response == b'X':
                print('Arduino reported buffer overrun.')


def reset_practice():
    action = ContinuousAction(f"RESETING")
    action.press(message(
        128, 128, 128, 128,
        sdl2.SDL_CONTROLLER_BUTTON_LEFTSHOULDER,  # L
        sdl2.SDL_CONTROLLER_BUTTON_RIGHTSHOULDER,  # R
        sdl2.SDL_CONTROLLER_BUTTON_B  # A
    ))
    return action


if __name__ == '__main__':
    import os
    macros_dir = '/home/awkii/macros'
    play_actions(
        menu_nav(1, 5, stage_mode=StageMode.FINAL_DESTINATION).play(),
        character_nav(1, 12).play(),
        # reset_practice().play(),
        # play_file(f'{macros_dir}/pit/bair.map'),
        # reset_practice().play(),
        # play_file(f'{macros_dir}/pit/dsmash.map'),
        # reset_practice().play(),

        controller_states('0')
    )

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


def enumerate_controllers():
    print('Controllers connected to this system:')
    for n in range(sdl2.SDL_NumJoysticks()):
        name = sdl2.SDL_JoystickNameForIndex(n)
        if name is not None:
            name = name.decode('utf8')
        print(n, ':', name)
    print('Note: These are numbered by connection order. Numbers will change if you unplug a controller.')


def get_controller(c):
    try:
        n = int(c, 10)
        return sdl2.SDL_GameControllerOpen(n)
    except ValueError:
        for n in range(sdl2.SDL_NumJoysticks()):
            name = sdl2.SDL_JoystickNameForIndex(n)
            if name is not None:
                name = name.decode('utf8')
                if name == c:
                    return sdl2.SDL_GameControllerOpen(n)
        raise Exception('Controller not found: %s'.format(c))


buttonmapping = [
    sdl2.SDL_CONTROLLER_BUTTON_X, # Y
    sdl2.SDL_CONTROLLER_BUTTON_A, # B
    sdl2.SDL_CONTROLLER_BUTTON_B, # A
    sdl2.SDL_CONTROLLER_BUTTON_Y, # X
    sdl2.SDL_CONTROLLER_BUTTON_LEFTSHOULDER, # L
    sdl2.SDL_CONTROLLER_BUTTON_RIGHTSHOULDER, # R
    sdl2.SDL_CONTROLLER_BUTTON_INVALID, # ZL
    sdl2.SDL_CONTROLLER_BUTTON_INVALID, # ZR
    sdl2.SDL_CONTROLLER_BUTTON_BACK, # SELECT
    sdl2.SDL_CONTROLLER_BUTTON_START, # START
    sdl2.SDL_CONTROLLER_BUTTON_LEFTSTICK, # LCLICK
    sdl2.SDL_CONTROLLER_BUTTON_RIGHTSTICK, # RCLICK
    sdl2.SDL_CONTROLLER_BUTTON_GUIDE, # HOME
    sdl2.SDL_CONTROLLER_BUTTON_INVALID, # CAPTURE
]

axismapping = [
    sdl2.SDL_CONTROLLER_AXIS_LEFTX, # LX
    sdl2.SDL_CONTROLLER_AXIS_LEFTY, # LY
    sdl2.SDL_CONTROLLER_AXIS_RIGHTX, # RX
    sdl2.SDL_CONTROLLER_AXIS_RIGHTY, # RY
]

hatmapping = [
    sdl2.SDL_CONTROLLER_BUTTON_DPAD_UP, # UP
    sdl2.SDL_CONTROLLER_BUTTON_DPAD_RIGHT, # RIGHT
    sdl2.SDL_CONTROLLER_BUTTON_DPAD_DOWN, # DOWN
    sdl2.SDL_CONTROLLER_BUTTON_DPAD_LEFT, # LEFT
]

hatcodes = [8, 0, 2, 1, 4, 8, 3, 8, 6, 7, 8, 8, 5, 8, 8]

axis_deadzone = 1000
trigger_deadzone = 0

start_dttm = dt.datetime.now().timestamp()


def controller_states(controller_id):

    sdl2.SDL_Init(sdl2.SDL_INIT_GAMECONTROLLER)

    controller = get_controller(controller_id)

    try:
        print('Using "{:s}" for input.'.format(
            sdl2.SDL_JoystickName(sdl2.SDL_GameControllerGetJoystick(controller)).decode('utf8')))
    except AttributeError:
        print('Using controller {:s} for input.'.format(controller_id))

    while True:
        elaped_time = dt.datetime.now().timestamp() - start_dttm
        buttons = sum([sdl2.SDL_GameControllerGetButton(controller, b) << n for n, b in enumerate(buttonmapping)])
        buttons |= (abs(sdl2.SDL_GameControllerGetAxis(controller, sdl2.SDL_CONTROLLER_AXIS_TRIGGERLEFT)) > trigger_deadzone) << 6
        buttons |= (abs(sdl2.SDL_GameControllerGetAxis(controller, sdl2.SDL_CONTROLLER_AXIS_TRIGGERRIGHT)) > trigger_deadzone) << 7

        hat = hatcodes[sum([sdl2.SDL_GameControllerGetButton(controller, b) << n for n, b in enumerate(hatmapping)])]

        rawaxis = [sdl2.SDL_GameControllerGetAxis(controller, n) for n in axismapping]
        axis = [((0 if abs(x) < axis_deadzone else x) >> 8) + 128 for x in rawaxis]

        rawbytes = struct.pack('>BHBBBB', hat, buttons, *axis)
        message_stamp = ControllerStateTime(rawbytes, elaped_time)
        yield message_stamp


def replay_states(filename):
    with open(filename, 'rb') as replay:
        for line in replay.readlines():
            # remove new-line character at end of line, and feed it into deserializer
            yield ControllerStateTime.deserialize(line[:-1])


def example_macro():
    buttons = 0
    hat = 8
    rx = 128
    ry = 128
    for i in range(240):
        elapsed_time = dt.datetime.now().timestamp() - start_dttm
        lx = int((1.0 + math.sin(2 * math.pi * i / 240)) * 127)
        ly = int((1.0 + math.cos(2 * math.pi * i / 240)) * 127)
        rawbytes = struct.pack('>BHBBBB', hat, buttons, lx, ly, rx, ry)
        message_stamp = ControllerStateTime(rawbytes, elapsed_time)
        yield message_stamp


class InputStack(object):
    def __init__(self):
        self.l = []

    def push(self, it):
        self.l.append(it)

    def pop(self):
        self.l.pop()

    def __iter__(self):
        return self

    def __next__(self):
        while True:
            try:
                return next(self.l[-1])
            except StopIteration:
                self.l.pop()
            except IndexError:
                raise StopIteration


class ControllerStateTime (namedtuple('ControllerStateTime', ('message', 'delta'))):
    """
    Serializable object responsible for recording a particular input at a particular timestamp
    """
    def formatted_message(self):
        return binascii.hexlify(self.message) + b'\n'

    def serialize(self):
        return binascii.hexlify(pickle.dumps(self))

    @staticmethod
    def deserialize(self):
        return pickle.loads(binascii.unhexlify(self))



if __name__ == '__main__':

    parser = argparse.ArgumentParser()
    parser.add_argument('-l', '--list-controllers', action='store_true', help='Display a list of controllers attached to the system.')
    parser.add_argument('-c', '--controller', type=str, default='0', help='Controller to use. Default: 0.')
    parser.add_argument('-b', '--baud-rate', type=int, default=115200, help='Baud rate. Default: 115200.')
    parser.add_argument('-p', '--port', type=str, default='/dev/ttyUSB0', help='Serial port. Default: /dev/ttyUSB0.')
    parser.add_argument('-R', '--record', type=str, default=None, help='Record events to file.')
    parser.add_argument('-P', '--playback', type=str, default=None, help='Play back events from file.')
    parser.add_argument('-d', '--dontexit', action='store_true', help='Switch to live input when playback finishes, instead of exiting. Default: False.')
    parser.add_argument('-q', '--quiet', action='store_true', help='Disable speed meter. Default: False.')

    args = parser.parse_args()

    if args.list_controllers:
        sdl2.SDL_Init(sdl2.SDL_INIT_GAMECONTROLLER)
        enumerate_controllers()
        exit(0)

    ser = serial.Serial(args.port, args.baud_rate, bytesize=serial.EIGHTBITS, parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE, timeout=None)
    print('Using {:s} at {:d} baud for comms.'.format(args.port, args.baud_rate))

    input_stack = InputStack()

    if args.playback is None or args.dontexit:
        live = controller_states(args.controller)
        next(live)  # pull a controller update to make it print the name before starting speed meter
        input_stack.push(live)
    if args.playback is not None:
        input_stack.push(replay_states(args.playback))

    with (open(args.record, 'wb') if args.record is not None else contextmanager(lambda: iter([None]))()) as record:
        with tqdm(unit=' updates', disable=args.quiet) as pbar:
            try:
                prev_msg_stamp = None
                while True:
                    for event in sdl2.ext.get_events():
                        # we have to fetch the events from SDL in order for the controller
                        # state to be updated.

                        # example of running a macro when a joystick button is pressed:
                        # if event.type == sdl2.SDL_CONTROLLERBUTTONDOWN:
                        #    # if event.jbutton.button == 1:
                        #    input_stack.push(example_macro())
                        # or play from file:
                        #        input_stack.push(replay_states(filename))
                        pass

                    try:
                        msg_stamp = next(input_stack)
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
                        if record is not None:
                            record.write(msg_stamp.serialize() + b'\n')
                    except StopIteration:
                        break

                    # update speed meter on console.
                    pbar.set_description('Sent {:s}'.format(msg_stamp.formatted_message()[:-1].decode('utf8')))
                    pbar.update()

                    while True:
                        # wait for the arduino to request another state.
                        response = ser.read(1)
                        if response == b'U':
                            break
                        elif response == b'X':
                            print('Arduino reported buffer overrun.')

            except KeyboardInterrupt:
                print('\nExiting due to keyboard interrupt.')

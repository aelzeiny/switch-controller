import socketio
from socketio.exceptions import ConnectionError
import bridge
import sdl2
import time
import argparse

# standard Python
sio = socketio.Client()
connected = False
host = None


@sio.event
def connect():
    global connected
    connected = True
    print("I'm connected!")


@sio.event
def disconnect():
    global connected
    connected = False
    print("I'm disconnected!")
    import time
    num_tries = 0
    while num_tries < 5:
        try:
            print('attempting to reconnect...')
            sio.connect(host)
        except ConnectionError:
            print('failed...')
            time.sleep(5)


def init_input_loop(joystick_idx):
    inputs = bridge.controller_states(joystick_idx, force_axis=True)
    prev_message = None
    time.sleep(1)
    while connected:
        sdl2.ext.get_events()
        message_stamp = next(inputs)
        message = message_stamp.message
        if message != prev_message:
            print(message)
            sio.emit('controller-input', message)
        prev_message = message


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-H', '--host', type=str, default='http://localhost:5000', help='Websocket Server Host.')
    parser.add_argument('-c', '--controller', type=str, default='0', help='SDL2 Controller Index')
    args = parser.parse_args()
    host = args.host
    sio.connect(host)
    init_input_loop(args.controller)

import socketio
from socketio.exceptions import ConnectionError
import bridge
import sdl2

# standard Python
sio = socketio.Client()
connected = False


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
            sio.connect('http://localhost:5000')
        except ConnectionError:
            print('failed...')
            time.sleep(5)


def init_input_loop(joystick_idx):
    inputs = bridge.controller_states(joystick_idx)
    prev_message = None
    while connected:
        sdl2.ext.get_events()
        message_stamp = next(inputs)
        message = message_stamp.formatted_message()
        if message != prev_message:
            sio.emit('controller-input', message)
        prev_message = message


if __name__ == '__main__':
    sio.connect('http://localhost:5000')
    init_input_loop('0')

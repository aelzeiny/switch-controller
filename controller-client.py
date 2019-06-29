import socketio
from socketio.exceptions import ConnectionError
import bridge
import serial
import argparse

# standard Python
sio = socketio.Client()
connected = False
ser = None


@sio.on('controller-input')
def on_message(data):
    while True:
        # wait for the arduino to request another state.
        response = ser.read(1)
        if response == b'U':
            break
        elif response == b'X':
            print('Arduino reported buffer overrun.')
    message_stamp = bridge.ControllerStateTime(data, 0)
    print(data)
    ser.write(message_stamp.formatted_message())


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


if __name__ == '__main__':

    parser = argparse.ArgumentParser()
    parser.add_argument('-h', '--host', type=str, default='http://localhost:5000', help='Websocket Server Host.')
    parser.add_argument('-c', '--controller', type=str, default='0', help='Controller to use. Default: 0.')
    parser.add_argument('-b', '--baud-rate', type=int, default=115200, help='Baud rate. Default: 115200.')
    parser.add_argument('-p', '--port', type=str, default='/dev/ttyUSB0', help='Serial port. Default: /dev/ttyUSB0.')

    args = parser.parse_args()

    sio.connect(args.host)
    ser = serial.Serial(args.port, args.baud_rate, bytesize=serial.EIGHTBITS,
                        parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE, timeout=None)
    print('Using {:s} at {:d} baud for comms.'.format(args.port, args.baud_rate))


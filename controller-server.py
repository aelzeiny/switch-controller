"""
Purpose: Create a flask websocket server that can take in a controller input & relay it to my PC which relays it to my
switch. Basically, I got tired of having to be home to work on this project.
"""
import os
from flask import Flask, jsonify
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET', 'secret!')
socketio = SocketIO(app)
client_count = 0


@app.route('/')
def index():
    return jsonify({
        'client_count': client_count
    })


@socketio.on('controller-input')
def test_message(message):
    emit('controller-input', message, broadcast=True)


@socketio.on('connect')
def test_connect():
    global client_count
    client_count += 1


@socketio.on('disconnect')
def test_disconnect():
    global client_count
    client_count -= 1


if __name__ == '__main__':
    socketio.run(app)

from flask_socketio import SocketIO

_socketio = None

def init_socket_manager(socketio: SocketIO):
    global _socketio
    _socketio = socketio

def emit_safe(event, data, namespace=None):
    global _socketio
    if _socketio:
        try:
            _socketio.emit(event, data, namespace=namespace)
        except Exception as e:
            print(f"Socket emit error: {e}")
    else:
        print(f"SocketIO not initialized. Event ignored: {event}")

"""Deny Python socket I/O while preserving socket classes for lazy SSL imports."""
import socket


def install_network_block():
    def denied(*args,**kwargs):
        raise RuntimeError('isolated processor network disabled')

    class BlockedSocket(socket.socket):
        def __init__(self,*args,**kwargs):
            denied()

    socket.socket=BlockedSocket
    socket.create_connection=denied
    socket.getaddrinfo=denied

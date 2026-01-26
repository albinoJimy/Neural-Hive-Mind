"""gRPC service.

NOTA: Os imports são feitos de forma lazy para evitar import circular.
Não importe TicketServiceServicer diretamente deste módulo.
Use start_grpc_server() que fará o import interno.
"""

# Imports lazy - não importar TicketServiceServicer diretamente
# para evitar import circular com proto_gen

def start_grpc_server(settings):
    """Wrapper lazy para evitar import circular."""
    from .server import start_grpc_server as _start
    return _start(settings)


def stop_grpc_server(server, health_servicer=None):
    """Wrapper lazy para evitar import circular."""
    from .server import stop_grpc_server as _stop
    return _stop(server, health_servicer)


__all__ = ['start_grpc_server', 'stop_grpc_server']

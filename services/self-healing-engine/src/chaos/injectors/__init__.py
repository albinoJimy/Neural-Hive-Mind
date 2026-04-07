"""
Fault Injectors para Chaos Engineering.

Cada injector é responsável por um tipo específico de falha:
- NetworkFaultInjector: Latência, packet loss, network partition
- PodFaultInjector: Pod kill, container kill, eviction
- ResourceFaultInjector: CPU/Memory stress, disk fill
- ApplicationFaultInjector: HTTP errors, slow responses
"""

from .application_injector import ApplicationFaultInjector
from .base_injector import BaseFaultInjector, InjectionResult
from .network_injector import NetworkFaultInjector
from .pod_injector import PodFaultInjector
from .resource_injector import ResourceFaultInjector

# Aliases para compatibilidade com testes
ApplicationInjector = ApplicationFaultInjector
NetworkInjector = NetworkFaultInjector
PodInjector = PodFaultInjector
ResourceInjector = ResourceFaultInjector

__all__ = [
    "BaseFaultInjector",
    "InjectionResult",
    "NetworkFaultInjector",
    "PodFaultInjector",
    "ResourceFaultInjector",
    "ApplicationFaultInjector",
    # Aliases
    "NetworkInjector",
    "PodInjector",
    "ResourceInjector",
    "ApplicationInjector",
]

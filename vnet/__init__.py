"""
AURA-AIOSCPU Virtual Network Layer
====================================
Provides virtual-device identity and mesh networking so this AURA node
can participate in a Command-Center-managed cluster of repos/devices.

Sub-modules
-----------
node_identity   — persistent UUID, capability declaration, identity serialisation
command_center  — CC registration, heartbeat, remote-command acceptance
peer_registry   — track sibling nodes discovered via CC or mDNS-style announce
mesh            — virtual mesh formation, state sync between peers
"""

from vnet.node_identity import NodeIdentity
from vnet.command_center import CommandCenterClient
from vnet.peer_registry import PeerRegistry
from vnet.mesh import VirtualMesh

__all__ = [
    "NodeIdentity",
    "CommandCenterClient",
    "PeerRegistry",
    "VirtualMesh",
]

"""Generated protobuf bindings for neural_hive_approval_common.

Re-exporta apenas os módulos gerados; não tocar manualmente — os
``approval_pb2.py``/``approval_pb2.pyi`` são gerados a partir de
``../../proto/approval.proto`` via ``python -m grpc_tools.protoc``.

Para regenerar::

    cd libraries/python/neural_hive_approval_common
    python -m grpc_tools.protoc \
        -I proto \
        --python_out=neural_hive_approval_common/proto \
        --pyi_out=neural_hive_approval_common/proto \
        proto/approval.proto
"""

from . import approval_pb2  # noqa: F401

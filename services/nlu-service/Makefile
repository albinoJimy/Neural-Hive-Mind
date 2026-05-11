.PHONY: generate-protos clean-protos help

PROTO_DIR := src/proto
PROTO_FILES := $(wildcard $(PROTO_DIR)/*.proto)

help:
	@echo "nlu-service — proto management"
	@echo ""
	@echo "Targets:"
	@echo "  generate-protos   Regenerate *_pb2.py and *_pb2_grpc.py from .proto files"
	@echo "  clean-protos      Remove generated pb2 files (forces regeneration on next run)"
	@echo ""
	@echo "Generated files live in $(PROTO_DIR)/ and are tracked in git."

generate-protos:
	@echo "Generating protobuf bindings from $(PROTO_FILES)..."
	python -m grpc_tools.protoc \
		-I$(PROTO_DIR) \
		--python_out=$(PROTO_DIR) \
		--grpc_python_out=$(PROTO_DIR) \
		$(PROTO_FILES)
	@echo "Done. Generated files in $(PROTO_DIR)/"

clean-protos:
	@rm -f $(PROTO_DIR)/*_pb2.py $(PROTO_DIR)/*_pb2_grpc.py
	@echo "Removed generated pb2 files."

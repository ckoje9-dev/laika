# ODA converter container build
# Build: docker build -f infra/docker/oda/Dockerfile -t laika/oda-converter:latest .
# Run example (volume mount project root to /data):
#   docker run --rm -v ${PWD}:/data laika/oda-converter:latest /data/tools/oda/ODAFileConverter \
#     /data/storage/original/sample.dwg /data/storage/derived ACAD2018 DXF 1 1

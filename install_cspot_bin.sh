#!/bin/bash

# This downloads the pre-compiled cspot / senspot binaries and puts the bin
# directory on path.

mkdir -p bin/cspot
cd bin/cspot
wget https://raw.githubusercontent.com/MAYHEM-Lab/cspot/refs/heads/caplets/dist/update-cspot-distribution.sh
chmod +x update-cspot-distribution.sh
./update-cspot-distribution.sh
export PATH="${PWD}:${PATH}"
echo "export PATH=\"${PWD}:\$PATH\"" >> ~/.bashrc
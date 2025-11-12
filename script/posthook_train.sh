git clone https://github.com/tdrussell/diffusion-pipe /workspace/diffusion-pipe
cd /workspace/diffusion-pipe
git submodule update --init --recursive
cp /workspace/train/train.sh /workspace/diffusion-pipe

pip install --no-build-isolation flash-attn>=2.8.3
pip install -r requirements.txt

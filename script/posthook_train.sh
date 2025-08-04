git clone https://github.com/tdrussell/diffusion-pipe /workspace/diffusion-pipe
cd /workspace/diffusion-pipe
git submodule update --init --recursive
pip install -r requirements.txt
cp /workspace/train/train.sh /workspace/diffusion-pipe